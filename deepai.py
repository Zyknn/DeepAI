"""Farming akun DeepAI (deepai.org) — email acak via api.mail.tm (tempmail).

Alur (diverifikasi live 2026-11-11):
  1. Bikin mailbox sekali-pakai via TempmailInbox.provision()  (api.mail.tm, gratis)
  2. Buka deepai.org -> openLogin() -> toggleAuthOption('signup')
  3. Isi email/password/confirm -> submitAuth() -> POST api.deepai.org/daily-time-sync/registration/
     Balas 201 + session cookie (tanpa verifikasi email, tanpa captcha).
  4. Ambil API key asli (UUID) dari input.api-password di /dashboard/profile.

CATATAN PENTING:
  - API key akun free VALID tapi endpoint model balas 402 (butuh Pro).
    /deepai_code/chat/completions pun balas 403 social_login_required utk akun email baru.
    Modul ini tetap menyimpan key utk arsip; gunakan bila akun punya akses Pro/Google.
  - curl/requests diblok CloudFront 403 -> wajib browser nyata (Chromium).

GANTI dari versi asli: pemasok email Temfex (temfex.com, butuh TEMFEX_API_KEY)
diganti jadi tempmail api.mail.tm (gratis, tanpa API key).

GitHub : https://github.com/HihuProject
Dev    : HihuProject
"""
from __future__ import annotations

import re
from pathlib import Path

from .tempmail import TempmailInbox, TempmailError
from .util import log, ts, parse_proxy, human_delay, load_lines

API_KEY_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def gen_password(n: int = 20) -> str:
    import secrets
    import string
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_"
    while True:
        pw = "".join(secrets.choice(alphabet) for _ in range(n))
        if (any(c.islower() for c in pw) and any(c.isupper() for c in pw)
                and any(c.isdigit() for c in pw) and any(c in "!@#$%^&*-_" for c in pw)):
            return pw


class DeepAIError(RuntimeError):
    pass


def signup_one(inbox: TempmailInbox, proxy: dict | None = None,
               headless: bool = True, password: str | None = None) -> dict:
    """Daftar 1 akun DeepAI. Kembalikan {email,password,api_key,status}."""
    from playwright.sync_api import sync_playwright

    email = inbox.provision()          # mailbox sekali-pakai dari api.mail.tm
    password = password or gen_password()
    res: dict = {"email": email, "password": password, "api_key": "", "status": "", "error": ""}

    launch_kw = {"headless": headless}
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
    from .proxylist import ProxyPool
    from .util import append_csv, append_jsonl

    inbox = TempmailInbox()               # pemasok email acak (api.mail.tm)
    proxies = load_lines(a.proxy_file)
    pool = ProxyPool(proxies, validate=not a.no_validate_proxy) if proxies else None

    CSV = ["email", "password", "api_key", "status", "proxy", "created_at_wib"]
    ok = fail = 0
    for i in range(a.count):
        raw_proxy = pool.next() if pool else None
        proxy = parse_proxy(raw_proxy) if raw_proxy else None
        log(f"[{i+1}/{a.count}] daftar akun DeepAI (email mail.tm)...")
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
            log(f"OK {r['email']} key={r['api_key'][:8]}...")
        else:
            fail += 1
            log(f"GAGAL {r.get('email','?')} status={r.get('status')} err={r.get('error','')}", "ERROR")
        if i < a.count - 1:
            human_delay(a.delay_min, a.delay_max)
    log(f"selesai: {ok} ok, {fail} gagal -> {out_dir/'deepai.csv'}")
    return 0


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="relayfarm.deepai", description="Farm akun DeepAI via email tempmail (api.mail.tm)")
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
