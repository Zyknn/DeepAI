#!/usr/bin/env python3
"""
Harvest massal akun DeepAI via Direct HTTP (requests atau Python stdlib fallback).
Multi-threaded queue-based worker dengan progress real-time dan auto-sync ke 9Router.
"""

import csv
import gzip
import http.cookiejar
import json
import os
import queue
import re
import secrets
import socket
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
import zlib
from datetime import datetime, timedelta, timezone
from itertools import cycle
from pathlib import Path

try:
    import requests
except ImportError:
    requests = None

BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR = BASE_DIR / "out_deepai"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = OUT_DIR / "deepai.csv"
JSONL_FILE = OUT_DIR / "deepai.jsonl"
PROXY_FILE = BASE_DIR / "proxies_live.txt"
if not PROXY_FILE.exists():
    PROXY_FILE = BASE_DIR / "proxies.txt"
DB_FILE = Path(os.environ.get("ROUTER_DB_PATH", Path.home() / ".9router/db/data.sqlite"))

UUID_RE = re.compile(
    r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$'
)
API_KEY_RE = re.compile(
    r'(?:id=["\']api-key-input-1["\']\s+value=["\']|name=["\']api-key["\']\s+value=["\'])([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})["\']',
    re.I
)
FALLBACK_KEY_RE = re.compile(
    r'\b([0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b',
    re.I
)


def _normalize_proxy(p):
    if not p:
        return None
    p = str(p).strip()
    if not p:
        return None
    if "://" not in p:
        parts = p.split(":")
        if len(parts) == 4:
            host, port, user, pw = parts
            return f"http://{user}:{pw}@{host}:{port}"
        if len(parts) == 2:
            return f"http://{p}"
        return f"http://{p}"
    return p


def _decode_http_body(raw: bytes, headers) -> str:
    enc = ""
    if headers is not None:
        enc = str(headers.get("Content-Encoding") or "").lower()
    if "gzip" in enc:
        try:
            raw = gzip.decompress(raw)
        except Exception:
            pass
    elif "deflate" in enc:
        try:
            raw = zlib.decompress(raw)
        except Exception:
            try:
                raw = zlib.decompress(raw, -zlib.MAX_WBITS)
            except Exception:
                pass
    return raw.decode("utf-8", errors="replace")


def _is_timeout_exc(exc) -> bool:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return True
    if requests is not None and isinstance(exc, requests.exceptions.Timeout):
        return True
    if isinstance(exc, urllib.error.URLError) and isinstance(getattr(exc, "reason", None), (TimeoutError, socket.timeout)):
        return True
    return "timed out" in str(exc).lower()


class _StdlibResponse:
    def __init__(self, status_code: int, text: str):
        self.status_code = status_code
        self.text = text

    def json(self):
        return json.loads(self.text)


class _StdlibSession:
    def __init__(self):
        self.headers = {}
        self.proxies = {}
        self.cookie_jar = http.cookiejar.CookieJar()

    def _build_opener(self):
        handlers: list[urllib.request.BaseHandler] = [urllib.request.HTTPCookieProcessor(self.cookie_jar)]
        if self.proxies:
            proxy_url = self.proxies.get("https") or self.proxies.get("http")
            if proxy_url and str(proxy_url).lower().startswith("socks"):
                raise RuntimeError("SOCKS proxy requires requests+PySocks")
            handlers.append(urllib.request.ProxyHandler(self.proxies))
        return urllib.request.build_opener(*handlers)

    def request(self, method: str, url: str, data=None, json_body=None, headers=None, timeout=12):
        req_headers = dict(self.headers)
        if headers:
            req_headers.update(headers)
        req_headers.setdefault("Accept-Encoding", "gzip")

        body_bytes = None
        if json_body is not None:
            body_bytes = json.dumps(json_body).encode("utf-8")
            req_headers.setdefault("Content-Type", "application/json")
        elif data is not None:
            if isinstance(data, dict):
                body_bytes = urllib.parse.urlencode(data).encode("utf-8")
                req_headers.setdefault("Content-Type", "application/x-www-form-urlencoded")
            elif isinstance(data, str):
                body_bytes = data.encode("utf-8")
            else:
                body_bytes = data

        req = urllib.request.Request(url, data=body_bytes, headers=req_headers, method=method)
        opener = self._build_opener()
        try:
            with opener.open(req, timeout=timeout) as resp:
                raw = resp.read()
                return _StdlibResponse(resp.status, _decode_http_body(raw, resp.headers))
        except urllib.error.HTTPError as e:
            raw = b""
            try:
                raw = e.read()
            except Exception:
                pass
            return _StdlibResponse(e.code, _decode_http_body(raw, e.headers))

    def get(self, url: str, headers=None, timeout=12):
        return self.request("GET", url, headers=headers, timeout=timeout)

    def post(self, url: str, data=None, json=None, headers=None, timeout=12):
        return self.request("POST", url, data=data, json_body=json, headers=headers, timeout=timeout)


def _new_session():
    return requests.Session() if requests is not None else _StdlibSession()


def probe_glm_key(api_key, timeout=7):
    """
    Test API key with GLM-5.3-Flash on DeepAI Code chat endpoint.
    Returns: (status_code, is_valid, latency_ms, detail_str)
    """
    if not api_key or not UUID_RE.match(str(api_key).strip()):
        return 400, False, 0, "Invalid UUID format"
    t0 = time.time()
    try:
        sess = _new_session()
        r = sess.post(
            "https://api.deepai.org/deepai_code/chat/completions",
            headers={
                "api-key": str(api_key).strip(),
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            },
            json={
                "model": "glm-5.3-flash",
                "messages": [{"role": "user", "content": "ping"}],
                "stream": False,
            },
            timeout=timeout,
        )
        lat = int((time.time() - t0) * 1000)
        is_ok = (r.status_code == 200)
        msg = ""
        if is_ok:
            try:
                data = r.json()
                msg = data.get("choices", [{}])[0].get("message", {}).get("content", "")[:50]
                if not msg:
                    msg = "HTTP 200 OK"
            except Exception:
                msg = "HTTP 200 OK"
        else:
            try:
                err_data = r.json()
                msg = err_data.get("error", {}).get("message", r.text[:50])
            except Exception:
                msg = r.text[:50]
        return r.status_code, is_ok, lat, msg
    except Exception as e:
        lat = int((time.time() - t0) * 1000)
        if _is_timeout_exc(e):
            return 408, False, lat, "Timeout"
        return 0, False, lat, str(e)[:50]

EMAIL_DOMAINS = ["gmail.com", "outlook.com", "icloud.com", "yahoo.com", "proton.me", "fldubai.com"]

file_lock = threading.Lock()
stats_lock = threading.Lock()
print_lock = threading.Lock()

total_ok = 0
total_fail = 0
total_done = 0

def ts():
    wib = timezone(timedelta(hours=7))
    return datetime.now(wib).strftime("%Y-%m-%d %H:%M:%S")

def log(msg, level="INFO"):
    with print_lock:
        print(f"[{ts()}] [{level}] {msg}", flush=True)

def append_records(row):
    with file_lock:
        exists = CSV_FILE.exists()
        header = ["email", "password", "api_key", "status", "proxy", "created_at_wib"]
        with open(CSV_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            if not exists:
                writer.writeheader()
            writer.writerow(row)
        with open(JSONL_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")

def sync_new_keys_to_db(records):
    if not DB_FILE.exists() or not records:
        return 0
    try:
        now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
        conn = sqlite3.connect(DB_FILE, timeout=30)
        cur = conn.cursor()
        inserted = 0
        for r in records:
            email = r.get("email")
            api_key = r.get("api_key")
            if not email or not api_key or r.get("status") != "ok":
                continue
            conn_id = str(uuid.uuid4())
            data_json = json.dumps({
                "apiKey": api_key,
                "testStatus": "active",
                "providerSpecificData": {
                    "prefix": "deepai",
                    "apiType": "chat",
                    "baseUrl": "https://api.deepai.org/deepai_code",
                    "nodeName": "DeepAI",
                    "connectionProxyEnabled": False,
                    "connectionProxyUrl": "",
                    "connectionNoProxy": ""
                },
                "lastError": None,
                "lastErrorAt": None,
                "errorCode": None,
                "rateLimitedUntil": None,
                "backoffLevel": 0
            })
            cur.execute(
                """
                INSERT OR IGNORE INTO providerConnections
                (id, provider, authType, name, email, priority, isActive, data, createdAt, updatedAt)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    conn_id,
                    "openai-compatible-chat-deepai",
                    "apikey",
                    "DeepAI",
                    email,
                    None,
                    1,
                    data_json,
                    now_iso,
                    now_iso
                )
            )
            inserted += 1
        conn.commit()
        conn.close()
        return inserted
    except Exception as e:
        log(f"DB Sync error: {e}", "WARN")
        return 0

def load_proxies():
    if not PROXY_FILE.exists():
        return []
    lines = [l.strip() for l in PROXY_FILE.read_text().splitlines() if l.strip() and not l.startswith("#")]
    return lines

def register_single(proxy=None, max_retries=2, verify_glm=False):
    t0 = time.time()
    user = f"user_{secrets.token_hex(4)}"
    domain = secrets.choice(EMAIL_DOMAINS)
    email = f"{user}@{domain}"
    pw = f"Pass!{user}#2026"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Origin": "https://deepai.org",
        "Referer": "https://deepai.org/",
    }

    current_proxy = _normalize_proxy(proxy)
    for attempt in range(max_retries + 1):
        s = _new_session()
        s.headers.update(headers)
        if current_proxy:
            if requests is None and str(current_proxy).lower().startswith("socks"):
                current_proxy = None
            else:
                s.proxies = {"http": current_proxy, "https": current_proxy}
        
        try:
            r = s.post(
                "https://api.deepai.org/daily-time-sync/registration/",
                data={
                    "username": user,
                    "email": email,
                    "password1": pw,
                    "password2": pw,
                },
                timeout=12,
            )
            lat = int((time.time() - t0) * 1000)
            if r.status_code == 201:
                # Direct JSON key extraction (hanya jika berformat UUID)
                api_key = None
                try:
                    res_json = r.json()
                    k = str(res_json.get("key", "")).strip()
                    if UUID_RE.match(k):
                        api_key = k
                except Exception:
                    api_key = None

                # Scrape profile untuk dapatkan API Key UUID riil DeepAI
                if not api_key:
                    try:
                        prof = s.get("https://deepai.org/dashboard/profile", timeout=12)
                        m = re.search(r'id=["\']header-api-key-value["\']\s+value=["\']([^"\']+)["\']', prof.text)
                        if not m:
                            m = re.search(r'class=["\']api-password["\'][^>]*value=["\']([^"\']+)["\']', prof.text)
                        if not m:
                            m = API_KEY_RE.search(prof.text)
                        if m:
                            k = m.group(1).strip()
                            if UUID_RE.match(k):
                                api_key = k
                        if not api_key:
                            for candidate in FALLBACK_KEY_RE.findall(prof.text):
                                cand_str = (candidate if isinstance(candidate, str) else (candidate[0] or candidate[1])).strip()
                                if UUID_RE.match(cand_str):
                                    api_key = cand_str
                                    break
                    except Exception:
                        pass
                
                if api_key and UUID_RE.match(str(api_key).strip()):
                    clean_key = str(api_key).strip()
                    if verify_glm:
                        sc, is_ok, v_lat, msg = probe_glm_key(clean_key)
                        lat += v_lat
                        if not is_ok:
                            return {
                                "email": email,
                                "password": pw,
                                "api_key": clean_key,
                                "status": f"glm_{sc}",
                                "proxy": current_proxy or "direct",
                                "created_at_wib": ts(),
                                "latency_ms": lat,
                            }
                    return {
                        "email": email,
                        "password": pw,
                        "api_key": clean_key,
                        "status": "ok",
                        "proxy": current_proxy or "direct",
                        "created_at_wib": ts(),
                        "latency_ms": lat,
                    }
                else:
                    return {
                        "email": email,
                        "password": pw,
                        "api_key": "",
                        "status": "invalid_or_no_key",
                        "proxy": current_proxy or "direct",
                        "created_at_wib": ts(),
                        "latency_ms": lat,
                    }
            elif r.status_code == 429:
                if attempt < max_retries:
                    current_proxy = None
                    time.sleep(1.5)
                    continue
                return {
                    "email": email,
                    "password": pw,
                    "api_key": "",
                    "status": "rate_limit_429",
                    "proxy": current_proxy or "direct",
                    "created_at_wib": ts(),
                    "latency_ms": lat,
                }
            else:
                if attempt < max_retries and current_proxy:
                    current_proxy = None
                    time.sleep(0.5)
                    continue
                return {
                    "email": email,
                    "password": pw,
                    "api_key": "",
                    "status": f"http_{r.status_code}",
                    "proxy": current_proxy or "direct",
                    "created_at_wib": ts(),
                    "latency_ms": lat,
                }
        except Exception as e:
            if attempt < max_retries:
                current_proxy = None
                time.sleep(0.5)
                continue
            return {
                "email": email,
                "password": pw,
                "api_key": "",
                "status": f"err_{type(e).__name__}",
                "proxy": current_proxy or "direct",
                "created_at_wib": ts(),
                "latency_ms": int((time.time() - t0) * 1000),
            }

    return {
        "email": email,
        "password": pw,
        "api_key": "",
        "status": "exhausted_429",
        "proxy": current_proxy or "direct",
        "created_at_wib": ts(),
        "latency_ms": int((time.time() - t0) * 1000),
    }

def worker_thread(task_q, proxy_iter, target_total, start_time, batch_sync_size=50, progress_cb=None, stop_event=None, verify_glm=False):
    global total_ok, total_fail, total_done
    local_buffer = []

    while True:
        if stop_event and stop_event.is_set():
            break
        try:
            _ = task_q.get_nowait()
        except queue.Empty:
            break

        p = next(proxy_iter) if proxy_iter else None
        res = register_single(p, verify_glm=verify_glm)
        if not res or not isinstance(res, dict):
            res = {
                "email": f"unknown_{secrets.token_hex(4)}@fldubai.com",
                "password": "",
                "api_key": "",
                "status": "err_null_response",
                "proxy": p or "direct",
                "created_at_wib": ts(),
                "latency_ms": 100,
            }
        res["worker"] = threading.current_thread().name
        append_records(res)

        with stats_lock:
            total_done += 1
            if res.get("status") == "ok":
                total_ok += 1
                local_buffer.append(res)
            else:
                total_fail += 1
            
            cur_done = total_done
            cur_ok = total_ok
            cur_fail = total_fail

        if len(local_buffer) >= batch_sync_size:
            with file_lock:
                sync_new_keys_to_db(local_buffer)
            local_buffer.clear()

        elapsed = time.time() - start_time
        speed = cur_done / elapsed if elapsed > 0 else 0
        if progress_cb:
            try:
                progress_cb(cur_done, target_total, cur_ok, cur_fail, speed, res)
            except TypeError:
                progress_cb(cur_done, target_total, cur_ok, cur_fail, speed)
        elif cur_done % 20 == 0 or cur_done == target_total:
            pct = (cur_done / target_total) * 100
            log(f"Progress: {cur_done}/{target_total} ({pct:.1f}%) | OK: {cur_ok} | FAIL: {cur_fail} | Speed: {speed:.1f} acc/s")

        task_q.task_done()

    if local_buffer:
        with file_lock:
            sync_new_keys_to_db(local_buffer)
        local_buffer.clear()

def run_bulk_harvest(count=1000, workers=8, progress_cb=None, stop_event=None, verify_glm=False):
    global total_ok, total_fail, total_done
    with stats_lock:
        total_ok = 0
        total_fail = 0
        total_done = 0

    proxies = load_proxies()
    proxy_iter = cycle(proxies) if proxies else None

    task_q = queue.Queue()
    for _ in range(count):
        task_q.put(1)

    start_time = time.time()
    threads = []
    for i in range(workers):
        t = threading.Thread(
            target=worker_thread,
            args=(task_q, proxy_iter, count, start_time, 50, progress_cb, stop_event, verify_glm),
            name=f"W-{i+1}"
        )
        t.daemon = True
        t.start()
        threads.append(t)

    while any(t.is_alive() for t in threads):
        if stop_event and stop_event.is_set():
            try:
                while True:
                    task_q.get_nowait()
                    task_q.task_done()
            except queue.Empty:
                pass
            break
        time.sleep(0.1)

    for t in threads:
        t.join(timeout=1.0)

    sync_script = BASE_DIR / "sync_to_9router.py"
    if sync_script.exists() and DB_FILE.exists():
        os.system(f"python3 {sync_script} >/dev/null 2>&1")
        os.system("pm2 reload 9router --update-env >/dev/null 2>&1 || true")

    elapsed = time.time() - start_time
    return {
        "count": count,
        "done": total_done,
        "ok": total_ok,
        "fail": total_fail,
        "elapsed": elapsed,
        "speed": total_done / elapsed if elapsed > 0 else 0
    }


# Backward compatibility alias
run_bulk_farm = run_bulk_harvest

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bulk create DeepAI accounts fast")
    parser.add_argument("--count", type=int, default=2000, help="Target total accounts")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent worker threads")
    args = parser.parse_args()

    log(f"Memulai bulk creation target={args.count} workers={args.workers}")
    res = run_bulk_harvest(args.count, args.workers)
    log(f"SELESAI! Target: {res['count']} | OK: {res['ok']} | FAIL: {res['fail']} | Durasi: {res['elapsed']:.1f}s")

if __name__ == "__main__":
    main()
