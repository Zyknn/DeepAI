#!/usr/bin/env python3
"""
Farming massal akun DeepAI via Direct HTTP (requests).
Multi-threaded queue-based worker dengan progress real-time dan auto-sync ke 9Router.
"""

import csv
import json
import os
import queue
import re
import secrets
import sqlite3
import sys
import threading
import time
import uuid
from datetime import datetime, timedelta, timezone
from itertools import cycle
from pathlib import Path

import requests

BASE_DIR = Path(__file__).parent.resolve()
OUT_DIR = BASE_DIR / "out_deepai"
OUT_DIR.mkdir(parents=True, exist_ok=True)
CSV_FILE = OUT_DIR / "deepai.csv"
JSONL_FILE = OUT_DIR / "deepai.jsonl"
PROXY_FILE = BASE_DIR / "proxies_live.txt"
if not PROXY_FILE.exists():
    PROXY_FILE = BASE_DIR / "proxies.txt"
DB_FILE = Path(os.environ.get("ROUTER_DB_PATH", Path.home() / ".9router/db/data.sqlite"))

API_KEY_RE = re.compile(
    r'id="api-key-input-1"\s+value="([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})"',
    re.I
)
FALLBACK_KEY_RE = re.compile(
    r'([0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12})',
    re.I
)

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

def register_single(proxy=None, max_retries=2):
    user = f"usr_{secrets.token_hex(4)}"
    email = f"{user}@fldubai.com"
    pw = f"Pass!{user}#2026"
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Origin": "https://deepai.org",
        "Referer": "https://deepai.org/",
    }

    current_proxy = proxy
    for attempt in range(max_retries + 1):
        s = requests.Session()
        s.headers.update(headers)
        if current_proxy:
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
            if r.status_code == 201:
                prof = s.get("https://deepai.org/dashboard/profile", timeout=12)
                m = API_KEY_RE.search(prof.text)
                api_key = m.group(1) if m else None
                if not api_key:
                    keys = FALLBACK_KEY_RE.findall(prof.text)
                    if keys:
                        api_key = keys[0]
                
                if api_key:
                    return {
                        "email": email,
                        "password": pw,
                        "api_key": api_key,
                        "status": "ok",
                        "proxy": current_proxy or "direct",
                        "created_at_wib": ts(),
                    }
                else:
                    return {
                        "email": email,
                        "password": pw,
                        "api_key": "",
                        "status": "no_key",
                        "proxy": current_proxy or "direct",
                        "created_at_wib": ts(),
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
                }
            else:
                return {
                    "email": email,
                    "password": pw,
                    "api_key": "",
                    "status": f"http_{r.status_code}",
                    "proxy": current_proxy or "direct",
                    "created_at_wib": ts(),
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
            }

    return {
        "email": email,
        "password": pw,
        "api_key": "",
        "status": "exhausted_429",
        "proxy": current_proxy or "direct",
        "created_at_wib": ts(),
    }

def worker_thread(task_q, proxy_iter, target_total, start_time, batch_sync_size=50, progress_cb=None, stop_event=None):
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
        res = register_single(p)
        if not res or not isinstance(res, dict):
            res = {
                "email": f"unknown_{secrets.token_hex(4)}@fldubai.com",
                "password": "",
                "api_key": "",
                "status": "err_null_response",
                "proxy": p or "direct",
                "created_at_wib": ts(),
            }
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
            progress_cb(cur_done, target_total, cur_ok, cur_fail, speed)
        elif cur_done % 20 == 0 or cur_done == target_total:
            pct = (cur_done / target_total) * 100
            log(f"Progress: {cur_done}/{target_total} ({pct:.1f}%) | OK: {cur_ok} | FAIL: {cur_fail} | Speed: {speed:.1f} acc/s")

        task_q.task_done()

    if local_buffer:
        with file_lock:
            sync_new_keys_to_db(local_buffer)
        local_buffer.clear()

def run_bulk_farm(count=1000, workers=8, progress_cb=None, stop_event=None):
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
    for _ in range(workers):
        t = threading.Thread(
            target=worker_thread,
            args=(task_q, proxy_iter, count, start_time, 50, progress_cb, stop_event)
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

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Bulk create DeepAI accounts fast")
    parser.add_argument("--count", type=int, default=2000, help="Target total accounts")
    parser.add_argument("--workers", type=int, default=10, help="Concurrent worker threads")
    args = parser.parse_args()

    log(f"Memulai bulk creation target={args.count} workers={args.workers}")
    res = run_bulk_farm(args.count, args.workers)
    log(f"SELESAI! Target: {res['count']} | OK: {res['ok']} | FAIL: {res['fail']} | Durasi: {res['elapsed']:.1f}s")

if __name__ == "__main__":
    main()
