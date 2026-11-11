"""Farming akun DeepAI (deepai.org) — email acak via api.mail.tm (tempmail).

Alur:
  1. Ambil domain aktif dari api.mail.tm atau fallback domain.
  2. Buka deepai.org -> openLogin() -> toggleAuthOption('signup')
  3. Isi email/password/confirm -> submitAuth() -> POST api.deepai.org/daily-time-sync/registration/
     Balas 201 + session cookie (tanpa verifikasi email, tanpa captcha).
  4. Ambil API key asli (UUID) dari input.api-password di /dashboard/profile.

CATATAN:
  - API key akun free VALID tapi endpoint model balas 402 (butuh Pro).
    /deepai_code/chat/completions pun balas 403 social_login_required utk akun email baru.
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import secrets
import shutil
import string
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

API_KEY_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


class TempmailError(Exception):
    pass


class DeepAIError(RuntimeError):
    pass


class TempmailInbox:
    """Manajer mailbox sekali-pakai via api.mail.tm dengan auto-fallback domain."""
    def __init__(self, api_base: str = "https://api.mail.tm"):
        self.api_base = api_base.rstrip("/")
        self._cached_domain: str | None = None

    def get_domain(self) -> str:
        if self._cached_domain:
            return self._cached_domain
        try:
            req = urllib.request.Request(f"{self.api_base}/domains", headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.loads(resp.read().decode())
                members = data.get("hydra:member", [])
                if members:
                    self._cached_domain = members[0]["domain"]
                    return self._cached_domain
        except Exception:
            pass
        self._cached_domain = "fldubai.com"
        return self._cached_domain

    def provision(self) -> str:
        domain = self.get_domain()
        username = f"usr_{secrets.token_hex(5)}"
        email = f"{username}@{domain}"
        pw = f"P@{secrets.token_hex(6)}"

        # Usaha registrasi ke mail.tm jika kuota IP mengizinkan
        try:
            payload = json.dumps({"address": email, "password": pw}).encode("utf-8")
            req = urllib.request.Request(
                f"{self.api_base}/accounts",
                data=payload,
                headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
            )
            with urllib.request.urlopen(req, timeout=10) as resp:
                res = json.loads(resp.read().decode())
                addr = res.get("address")
                return str(addr) if addr else email
        except Exception:
            # DeepAI tidak memvalidasi aktivasi email secara live, email domain aktif langsung valid
            return email


def ts() -> str:
    wib = timezone(timedelta(hours=7))
    return datetime.now(wib).strftime("%Y-%m-%d %H:%M:%S")


def log(msg: str, level: str = "INFO"):
    print(f"[{ts()}] [{level}] {msg}")


def parse_proxy(p: str | None) -> dict | None:
    if not p:
        return None
    p = p.strip()
    if "://" not in p:
        parts = p.split(":")
        if len(parts) == 4:
            host, port, user, pw = parts
            return {"server": f"http://{host}:{port}", "username": user, "password": pw}
        elif len(parts) == 2:
            return {"server": f"http://{p}"}
    u = urllib.parse.urlparse(p)
    res = {"server": f"{u.scheme}://{u.hostname}:{u.port}"}
    if u.username:
        res["username"] = u.username
    if u.password:
        res["password"] = u.password
    return res


def human_delay(min_s: float, max_s: float):
    sec = secrets.SystemRandom().uniform(min_s, max_s)
    time.sleep(sec)


def load_lines(path: str | Path | None) -> list[str]:
    if not path:
        return []
    p = Path(path)
    if not p.exists():
        return []
    return [line.strip() for line in p.read_text().splitlines() if line.strip() and not line.strip().startswith("#")]


def append_csv(path: Path, header: list[str], row: dict):
    exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def append_jsonl(path: Path, row: dict):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")


class ProxyPool:
    def __init__(self, proxies: list[str], validate: bool = True):
        self.proxies = proxies
        self.idx = 0

    def next(self) -> str | None:
        if not self.proxies:
            return None
        p = self.proxies[self.idx % len(self.proxies)]
        self.idx += 1
        return p


def gen_password(n: int = 20) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*-_" for c in pw)):
            return pw


def signup_one(inbox: TempmailInbox, proxy: dict | None = None,
               headless: bool = True, password: str | None = None) -> dict:
    """Daftar 1 akun DeepAI. Kembalikan {email,password,api_key,status}."""
    from playwright.sync_api import sync_playwright

    email = inbox.provision()
    password = password or gen_password()
    res: dict = {"email": email, "password": password, "api_key": "", "status": "", "error": ""}

    launch_kw: dict = {"headless": headless}
    chrome_bin = shutil.which("google-chrome") or shutil.which("chromium") or shutil.which("chromium-browser")
    if chrome_bin:
        launch_kw["executable_path"] = chrome_bin

    if proxy:
        launch_kw["proxy"] = {"server": proxy.get("server")}
        if proxy.get("username"):
            launch_kw["proxy"]["username"] = proxy["username"]
            launch_kw["proxy"]["password"] = proxy.get("password", "")

    with sync_playwright() as p:
        browser = p.chromium.launch(**launch_kw)
        ctx = browser.new_context()
        page = ctx.new_page()
        try:
            page.goto("https://deepai.org/", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(1200)
            page.evaluate("openLogin()")
            page.wait_for_timeout(600)
            page.evaluate("toggleAuthOption('signup')")
            page.wait_for_timeout(600)
            page.fill("#user-email", email)
            page.fill("#user-password", password)
            page.fill("#confirm-user-password", password)
            page.evaluate("submitAuth(new Event('submit'))")

            # tunggu modal tutup / error muncul
            for _ in range(30):
                page.wait_for_timeout(500)
                err = page.evaluate(
                    "(()=>{const p=document.getElementById('user-email-error');"
                    "return (p&&p.offsetParent)?p.innerText.trim():''})()")
                if err:
                    res["status"] = "error"
                    res["error"] = err
                    return res
                if not page.evaluate(
                        "!!document.getElementById('user-email') && !!document.getElementById('user-email').offsetParent"):
                    res["status"] = "registered"
                    break
            else:
                res["status"] = "unknown"
                return res

            # ambil API key dari dashboard
            page.goto("https://deepai.org/dashboard/profile",
                      wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(2000)
            key = page.evaluate(
                "(()=>{const i=document.querySelector('input.api-password');"
                "return i?(i.value||'').trim():''})()")
            if key and API_KEY_RE.match(key):
                res["api_key"] = key
                res["status"] = "ok"
            else:
                res["status"] = res["status"] + "+no_key"
        finally:
            browser.close()
    return res


def cmd_register(a) -> int:
    out_dir = Path(a.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    inbox = TempmailInbox()
    proxies = load_lines(a.proxy_file)
    pool = ProxyPool(proxies, validate=not a.no_validate_proxy) if proxies else None

    CSV = ["email", "password", "api_key", "status", "proxy", "created_at_wib"]
    ok = fail = 0
    for i in range(a.count):
        raw_proxy = pool.next() if pool else None
        proxy = parse_proxy(raw_proxy) if raw_proxy else None
        log(f"[{i+1}/{a.count}] daftar akun DeepAI (email {inbox.get_domain()})...")
        try:
            r = signup_one(inbox, proxy=proxy, headless=not a.headed)
        except Exception as e:
            r = {"email": "", "password": "", "api_key": "", "status": "error", "error": str(e)[:200]}
        r["proxy"] = raw_proxy or "direct"
        r["created_at_wib"] = ts()
        append_jsonl(out_dir / "deepai.jsonl", r)
        append_csv(out_dir / "deepai.csv", CSV, r)
        if r.get("api_key"):
            ok += 1
            masked_key = r['api_key'][:8] + "..."
            log(f"OK {r['email']} key={masked_key}")
        else:
            fail += 1
            log(f"GAGAL {r.get('email','?')} status={r.get('status')} err={r.get('error','')}", "ERROR")
        if i < a.count - 1:
            human_delay(a.delay_min, a.delay_max)
    log(f"selesai: {ok} ok, {fail} gagal -> {out_dir/'deepai.csv'}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(prog="deepai", description="Farm akun DeepAI via email tempmail (api.mail.tm)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    reg = sub.add_parser("register", help="daftar N akun")
    reg.add_argument("--count", type=int, default=5)
    reg.add_argument("--proxy-file", default=None)
    reg.add_argument("--no-validate-proxy", action="store_true")
    reg.add_argument("--headed", action="store_true", help="tampilkan browser")
    reg.add_argument("--out-dir", default="out_deepai")
    reg.add_argument("--delay-min", type=float, default=5)
    reg.add_argument("--delay-max", type=float, default=15)
    reg.set_defaults(fn=cmd_register)

    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    raise SystemExit(main())