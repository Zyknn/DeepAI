#!/usr/bin/env python3
"""
🌸 DeepAI Harvest TUI
Interactive Text User Interface for DeepAI Account Harvesting & Management.
Crafted by Zykuan (@Zyknn)
"""

import csv
import json
import os
import queue
import re
import select
import shutil
import socket
import socketserver
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler
from pathlib import Path

# Impor engine backend
BASE_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE_DIR))

try:
    import requests
except ImportError:
    requests = None

try:
    from bulk_create import run_bulk_harvest, run_bulk_farm, CSV_FILE, OUT_DIR, DB_FILE
except ImportError:
    CSV_FILE = BASE_DIR / "out_deepai" / "deepai.csv"
    OUT_DIR = BASE_DIR / "out_deepai"
    DB_FILE = Path.home() / ".9router/db/data.sqlite"
    run_bulk_harvest = None
    run_bulk_farm = None

# Palet Warna (ANSI TrueColor + Fallback)
C_RESET   = "\033[0m"
C_BOLD    = "\033[1m"
C_DIM     = "\033[2m"
C_ITALIC  = "\033[3m"
C_UNDER   = "\033[4m"

# Hex Colors:
P_LAVENDER = "\033[38;2;197;180;227m"  # #c5b4e3 - Utama / Header
P_MINT     = "\033[38;2;168;218;181m"  # #a8dab5 - Sukses / OK
P_PEACH    = "\033[38;2;255;190;152m"  # #ffbe98 - Prompt / Aksen Seleksi
P_SKY      = "\033[38;2;162;210;242m"  # #a2d2f2 - Data / Link / Info
P_PINK     = "\033[38;2;248;187;208m"  # #f8bbd0 - Highlight Love / Cute
P_YELLOW   = "\033[38;2;254;235;170m"  # #feeaaa - Peringatan / Latency
P_SLATE    = "\033[38;2;138;144;166m"  # #8a90a6 - Border / Muted
P_WHITE    = "\033[38;2;240;240;245m"  # #f0f0f5 - Teks Utama
P_BG_SEL   = "\033[48;2;45;40;60m"     # #2d283c - Background Baris Seleksi

CONFIG_FILE = BASE_DIR / ".tui_config.json"

def load_config():
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

def clear_screen():
    sys.stdout.write("\033[H\033[J")
    sys.stdout.flush()

def get_terminal_width():
    try:
        return os.get_terminal_size().columns
    except Exception:
        return 70

def get_public_ip():
    urls = ["https://api.ipify.org", "https://ifconfig.me", "https://icanhazip.com"]
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "curl/7.68.0"})
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                ip = resp.read().decode().strip()
                if ip and len(ip.split(".")) == 4:
                    return ip
        except Exception:
            continue
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"

def read_key():
    """Membaca 1 tombol (termasuk arrow keys, enter, dan shortcut) secara akurat tanpa buffer lag."""
    if not sys.stdin.isatty():
        try:
            line = sys.stdin.readline()
            return line.strip() if line else "0"
        except Exception:
            return "0"

    try:
        import termios
        import tty
        fd = sys.stdin.fileno()
        old = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            # Baca 1 byte pertama via OS file descriptor (bypass TextIOWrapper buffering)
            ch = os.read(fd, 1)
            if not ch:
                return "0"
            if ch == b"\x03":  # Ctrl+C
                raise KeyboardInterrupt
            if ch in (b"\r", b"\n", b" "):
                return "ENTER"
            
            if ch == b"\x1b":
                # Escape sequence (panah / escape / keypad / SS3)
                seq = b"\x1b"
                # Berikan jeda 0.15s agar packet SSH yang terpisah latensi jaringan bisa sampai
                while True:
                    r, _, _ = select.select([fd], [], [], 0.15)
                    if r:
                        chunk = os.read(fd, 16)
                        if not chunk:
                            break
                        seq += chunk
                        # Cek apakah sequence sudah selesai (panah atau keypad)
                        if any(k in seq for k in (b"[A", b"[B", b"[C", b"[D", b"OA", b"OB", b"OC", b"OD", b"OM")):
                            break
                    else:
                        break

                if b"[A" in seq or b"OA" in seq or seq.endswith(b"A"):
                    return "UP"
                elif b"[B" in seq or b"OB" in seq or seq.endswith(b"B"):
                    return "DOWN"
                elif b"[C" in seq or b"OC" in seq or seq.endswith(b"C"):
                    return "RIGHT"
                elif b"[D" in seq or b"OD" in seq or seq.endswith(b"D"):
                    return "LEFT"
                elif b"OM" in seq:
                    return "ENTER"
                return "ESC"

            try:
                char = ch.decode("utf-8", errors="ignore")
            except Exception:
                char = ""

            # Dukungan W/S dan K/J untuk navigasi atas-bawah
            if char in ("w", "W", "k", "K"):
                return "UP"
            elif char in ("s", "S", "j", "J"):
                return "DOWN"
            elif char in ("q", "Q"):
                return "0"
            
            return char
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old)
    except ImportError:
        # Fallback Windows
        try:
            import msvcrt
            getch_fn = getattr(msvcrt, "getch")
            ch = getch_fn()
            if ch in (b"\r", b"\n", b" "):
                return "ENTER"
            if ch == b"\x03":
                raise KeyboardInterrupt
            if ch in (b"\x00", b"\xe0"):
                ch2 = getch_fn()
                if ch2 == b"H": return "UP"
                if ch2 == b"P": return "DOWN"
                if ch2 == b"M": return "RIGHT"
                if ch2 == b"K": return "LEFT"
            char = ch.decode("utf-8", errors="ignore")
            if char in ("w", "W", "k", "K"): return "UP"
            if char in ("s", "S", "j", "J"): return "DOWN"
            if char in ("q", "Q"): return "0"
            return char
        except Exception:
            try:
                return input().strip()
            except Exception:
                return "0"
    except Exception:
        try:
            return input().strip()
        except Exception:
            return "0"

def get_csv_stats():
    if not CSV_FILE.exists():
        return {"exists": False, "total": 0, "ok": 0, "fail": 0, "size_str": "0 KB", "recent": []}
    
    total = 0
    ok = 0
    fail = 0
    recent = []
    size = CSV_FILE.stat().st_size
    size_str = f"{size / 1024:.1f} KB" if size < 1024 * 1024 else f"{size / (1024 * 1024):.2f} MB"

    try:
        with open(CSV_FILE, "r", encoding="utf-8", errors="ignore") as f:
            reader = csv.DictReader(f)
            for r in reader:
                total += 1
                if r.get("status") == "ok":
                    ok += 1
                else:
                    fail += 1
                recent.append(r)
                if len(recent) > 5:
                    recent.pop(0)
    except Exception:
        pass

    return {
        "exists": True,
        "total": total,
        "ok": ok,
        "fail": fail,
        "size_str": size_str,
        "recent": recent
    }

def mask_key(k):
    if not k:
        return "-"
    if len(k) >= 12:
        return f"{k[:4]}••••••••••••••••••••{k[-4:]}"
    return k

def render_banner(stats):
    tot_str = f"{stats['ok']:,} valid" if stats['exists'] else "0 akun"
    size_str = stats['size_str'] if stats['exists'] else "0 KB"
    
    print(f"{P_LAVENDER}╭─────────────────────────────────────────────────────────────╮{C_RESET}")
    print(f"{P_LAVENDER}│  {C_BOLD}{P_PINK}🌸 DEEPAI HARVEST TUI{C_RESET}  {P_SLATE}•{C_RESET}  {P_SKY}Zykuan (@Zyknn){C_RESET}{' ' * 18}{P_LAVENDER}│{C_RESET}")
    print(f"{P_LAVENDER}├─────────────────────────────────────────────────────────────┤{C_RESET}")
    print(f"{P_LAVENDER}│  {P_SLATE}📁 File:{C_RESET} {P_WHITE}out_deepai/deepai.csv{P_LAVENDER}   {P_SLATE}│{C_RESET} {P_MINT}🌾 Akun:{C_RESET} {P_MINT}{tot_str}{P_LAVENDER} ({size_str}) │{C_RESET}")
    print(f"{P_LAVENDER}╰─────────────────────────────────────────────────────────────╯{C_RESET}")

def render_menu(options, selected_idx):
    print(f"{P_SLATE} Navigasi: {P_PEACH}↑/↓{P_SLATE} (atau {P_PEACH}W/S{P_SLATE}) lalu {P_PEACH}Enter{P_SLATE}, atau tekan angka [{P_PEACH}1-5{P_SLATE}]:{C_RESET}\n")
    for idx, (num, label, desc) in enumerate(options):
        if idx == selected_idx:
            print(f" {P_PEACH}❯{C_RESET} {P_BG_SEL}{C_BOLD}{P_PINK}[{num}] {label:<36}{C_RESET} {P_SLATE}{desc}{C_RESET}")
        else:
            print(f"   {P_PEACH}[{num}]{C_RESET} {P_WHITE}{label:<36}{C_RESET} {P_SLATE}{desc}{C_RESET}")
    print(f"\n{P_SLATE}───────────────────────────────────────────────────────────────{C_RESET}")

# ---------------- MENU 1: QUICK HARVEST ----------------
def run_progress_box(target, workers, safe_mode=False):
    clear_screen()
    print(f"{P_LAVENDER}╭─────────────────────────────────────────────────────────────╮{C_RESET}")
    print(f"{P_LAVENDER}│  {C_BOLD}{P_PINK}⚡ DEEPAI HARVESTING IN PROGRESS{C_RESET}{' ' * 27}{P_LAVENDER}│{C_RESET}")
    print(f"{P_LAVENDER}│  {P_SLATE}Target:{C_RESET} {P_SKY}{target}{P_LAVENDER}  {P_SLATE}•  Workers:{C_RESET} {P_PEACH}{workers}{P_LAVENDER}  {P_SLATE}•  Mode:{C_RESET} {P_MINT}{'Safe Cooldown' if safe_mode else 'Direct Turbo'}{P_LAVENDER}  │{C_RESET}")
    print(f"{P_LAVENDER}├─────────────────────────────────────────────────────────────┤{C_RESET}")

    stop_evt = threading.Event()
    last_print = [0.0]

    def on_progress(done, tot, ok, fail, speed):
        now = time.time()
        if now - last_print[0] < 0.15 and done != tot:
            return
        last_print[0] = now

        pct = (done / tot) * 100 if tot > 0 else 0
        bar_len = 26
        filled = int(bar_len * (done / tot)) if tot > 0 else 0
        bar = f"{P_MINT}{'█' * filled}{P_SLATE}{'░' * (bar_len - filled)}{C_RESET}"

        rem_items = tot - done
        eta_sec = int(rem_items / speed) if speed > 0 else 0
        eta_str = f"{eta_sec}s" if eta_sec < 60 else f"{eta_sec // 60}m {eta_sec % 60}s"

        sys.stdout.write(
            f"\r\033[2K{P_LAVENDER}│{C_RESET} [{bar}] {P_SKY}{pct:>5.1f}%{C_RESET} ({P_WHITE}{done}/{tot}{C_RESET}) "
            f"{P_MINT}✓ {ok:<4}{C_RESET} {P_YELLOW}✗ {fail:<3}{C_RESET} {P_PEACH}{speed:>4.1f}/s{C_RESET} {P_SLATE}~{eta_str}{C_RESET} "
        )
        sys.stdout.flush()

    try:
        engine = run_bulk_harvest or run_bulk_farm
        if not engine:
            print(f"\n{P_YELLOW}Engine bulk_create tidak ditemukan.{C_RESET}")
            return
        res = engine(count=target, workers=workers, progress_cb=on_progress, stop_event=stop_evt)
        print(f"\n{P_LAVENDER}╰─────────────────────────────────────────────────────────────╯{C_RESET}")
        print(f"\n{P_MINT}✨ SELESAI!{C_RESET} Berhasil panen {P_MINT}{res['ok']}{C_RESET} akun baru ({res['fail']} gagal) dalam {P_SKY}{res['elapsed']:.1f}s{C_RESET}.")
        print(f"{P_SLATE}Data otomatis tersimpan di: {P_WHITE}{CSV_FILE}{C_RESET}")
    except KeyboardInterrupt:
        stop_evt.set()
        print(f"\n\n{P_YELLOW}⚠️  Harvest dihentikan pengguna.{C_RESET} Akun yang sudah didapat tetap aman tersimpan di CSV.")
    
    print(f"\n{P_PEACH}Tekan Enter untuk kembali ke menu...{C_RESET}", end="", flush=True)
    try:
        input()
    except Exception:
        pass

def menu_harvest():
    presets = [
        ("1", "100 Akun   • Quick Test", "8 threads, estimasi ~15-20 detik", 100, 8),
        ("2", "500 Akun   • Fast Batch", "8 threads, estimasi ~1-2 menit", 500, 8),
        ("3", "1000 Akun  • Standard Batch", "8 threads, estimasi ~2-3 menit", 1000, 8),
        ("4", "5000 Akun  • Multi-Batch Safe", "5 x 1000 akun + auto cooldown 45s", 5000, 8),
        ("5", "Custom     • Atur Sendiri", "Tentukan target akun & threads", 0, 0),
        ("0", "Batal / Kembali", "Kembali ke menu utama", 0, 0),
    ]

    sel_idx = 2  # default 1000
    while True:
        clear_screen()
        stats = get_csv_stats()
        render_banner(stats)
        print(f" {C_BOLD}{P_PINK}⚡ PILIH TARGET HARVEST AKUN{C_RESET}")
        print(f"{P_SLATE} Navigasi: {P_PEACH}↑/↓{P_SLATE} (atau {P_PEACH}W/S{P_SLATE}) lalu {P_PEACH}Enter{P_SLATE}, atau tekan angka [{P_PEACH}1-5{P_SLATE}]:{C_RESET}\n")

        for idx, (num, label, desc, _, _) in enumerate(presets):
            if idx == sel_idx:
                print(f" {P_PEACH}❯{C_RESET} {P_BG_SEL}{C_BOLD}{P_PINK}[{num}] {label:<32}{C_RESET} {P_SLATE}{desc}{C_RESET}")
            else:
                print(f"   {P_PEACH}[{num}]{C_RESET} {P_WHITE}{label:<32}{C_RESET} {P_SLATE}{desc}{C_RESET}")
        print(f"\n{P_SLATE}───────────────────────────────────────────────────────────────{C_RESET}")

        key = read_key()
        if key == "UP":
            sel_idx = (sel_idx - 1) % len(presets)
        elif key == "DOWN":
            sel_idx = (sel_idx + 1) % len(presets)
        elif key in ("ENTER", "1", "2", "3", "4", "5", "0"):
            chosen_num = key if key in ("1", "2", "3", "4", "5", "0") else presets[sel_idx][0]
            if chosen_num == "0":
                break
            
            chosen_item = next(p for p in presets if p[0] == chosen_num)
            target, workers = chosen_item[3], chosen_item[4]

            if chosen_num == "5":
                clear_screen()
                render_banner(stats)
                print(f" {C_BOLD}{P_PINK}⚙️  CUSTOM TARGET & WORKERS{C_RESET}\n")
                try:
                    c_str = input(f"{P_PEACH}Target jumlah akun [contoh: 300]: {C_RESET}").strip()
                    target = int(c_str) if c_str.isdigit() else 300
                    w_str = input(f"{P_PEACH}Jumlah threads worker [default: 8]: {C_RESET}").strip()
                    workers = int(w_str) if w_str.isdigit() else 8
                except Exception:
                    break

            if chosen_num == "4":
                # Multi-batch safe cooldown
                batches = 5
                per_batch = 1000
                for b_i in range(1, batches + 1):
                    run_progress_box(per_batch, workers, safe_mode=True)
                    if b_i < batches:
                        print(f"\n{P_SKY}🌸 Cooldown 45 detik antar-batch (Batch {b_i}/{batches} selesai)...{C_RESET}")
                        for s in range(45, 0, -1):
                            sys.stdout.write(f"\r{P_SLATE}Melanjutkan batch {b_i+1} dalam {P_PEACH}{s:02d}s{P_SLATE}... (Tekan Ctrl+C untuk lewati){C_RESET} ")
                            sys.stdout.flush()
                            try:
                                time.sleep(1)
                            except KeyboardInterrupt:
                                break
                        print()
                break
            else:
                run_progress_box(target, workers)
                break

menu_farming = menu_harvest  # backward compatibility alias

# ---------------- MENU 2: LIHAT STATISTIK & DATA ----------------
def menu_stats():
    clear_screen()
    stats = get_csv_stats()
    render_banner(stats)
    print(f" {C_BOLD}{P_SKY}📊 STATISTIK PANEN & 5 AKUN TERAKHIR{C_RESET}\n")

    if not stats["exists"] or stats["total"] == 0:
        print(f"{P_YELLOW}⚠️  Belum ada data akun di {CSV_FILE}.{C_RESET}")
        print(f"{P_SLATE}Silakan jalankan menu [1] Quick Harvest terlebih dahulu.{C_RESET}")
    else:
        print(f"{P_LAVENDER}╭─────────────────────────────────────────────────────────────╮{C_RESET}")
        print(f"{P_LAVENDER}│  {P_WHITE}Total Akun Terdaftar  :{C_RESET} {P_MINT}{stats['total']:,} akun{P_LAVENDER}                               │{C_RESET}")
        print(f"{P_LAVENDER}│  {P_WHITE}Valid / Berhasil (OK) :{C_RESET} {P_MINT}{stats['ok']:,} key{P_LAVENDER}                                │{C_RESET}")
        print(f"{P_LAVENDER}│  {P_WHITE}Gagal / 429 Exhaust   :{C_RESET} {P_YELLOW}{stats['fail']:,} akun{P_LAVENDER}                               │{C_RESET}")
        print(f"{P_LAVENDER}│  {P_WHITE}Ukuran File CSV       :{C_RESET} {P_SKY}{stats['size_str']}{P_LAVENDER}                                  │{C_RESET}")
        print(f"{P_LAVENDER}╰─────────────────────────────────────────────────────────────╯{C_RESET}\n")

        print(f"{C_BOLD}{P_PINK}5 Akun Terakhir Disimpan:{C_RESET}")
        print(f"{P_SLATE}{'Email':<30} {'Masked API Key':<32} {'WIB':<10}{C_RESET}")
        print(f"{P_SLATE}───────────────────────────────────────────────────────────────{C_RESET}")
        for r in stats["recent"]:
            em = r.get("email", "-")[:28]
            k = mask_key(r.get("api_key", ""))
            ts_str = r.get("created_at_wib", "-")[-8:]
            print(f"{P_WHITE}{em:<30}{C_RESET} {P_SKY}{k:<32}{C_RESET} {P_SLATE}{ts_str:<10}{C_RESET}")

    print(f"\n{P_PEACH}Tekan Enter untuk kembali...{C_RESET}", end="", flush=True)
    try:
        input()
    except Exception:
        pass

# ---------------- MENU 3: AUTO SHARE & DOWNLOAD CSV ----------------
class CSVDownloadHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if not CSV_FILE.exists():
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b"File not found")
            return
        
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="deepai.csv"')
        self.send_header("Content-Length", str(CSV_FILE.stat().st_size))
        self.end_headers()
        with open(CSV_FILE, "rb") as f:
            shutil.copyfileobj(f, self.wfile)

    def log_message(self, format, *args):
        pass  # Supress console spam

def start_http_server():
    clear_screen()
    stats = get_csv_stats()
    render_banner(stats)

    if not CSV_FILE.exists():
        print(f"{P_YELLOW}⚠️  File {CSV_FILE} belum ada! Panen akun dulu ya.{C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    port = 18888
    httpd = None
    for p in range(18888, 18900):
        try:
            httpd = socketserver.TCPServer(("0.0.0.0", p), CSVDownloadHandler)
            port = p
            break
        except OSError:
            continue

    if not httpd:
        print(f"{P_YELLOW}Gagal bind port HTTP.{C_RESET}")
        return

    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()

    ip = get_public_ip()
    dl_url = f"http://{ip}:{port}/deepai.csv"

    print(f" {C_BOLD}{P_MINT}🌐 INSTANT DOWNLOAD WEB SERVER AKTIF!{C_RESET}\n")
    print(f"{P_LAVENDER}╭─────────────────────────────────────────────────────────────╮{C_RESET}")
    print(f"{P_LAVENDER}│  {P_WHITE}File CSV siap disedot langsung dari browser / terminal:{C_RESET}    {P_LAVENDER}│{C_RESET}")
    print(f"{P_LAVENDER}│                                                             │{C_RESET}")
    print(f"{P_LAVENDER}│  {P_PEACH}👉 Link Download Langsung:{C_RESET}                                 {P_LAVENDER}│{C_RESET}")
    print(f"{P_LAVENDER}│     {C_BOLD}{P_SKY}{dl_url:<54}{C_RESET} {P_LAVENDER}│{C_RESET}")
    print(f"{P_LAVENDER}│                                                             │{C_RESET}")
    print(f"{P_LAVENDER}│  {P_PEACH}👉 Perintah Sedot di VPS Lain / Laptop:{C_RESET}                    {P_LAVENDER}│{C_RESET}")
    print(f"{P_LAVENDER}│     {P_MINT}curl -s {dl_url} -o deepai.csv{C_RESET}  {P_LAVENDER}│{C_RESET}")
    print(f"{P_LAVENDER}╰─────────────────────────────────────────────────────────────╯{C_RESET}")
    print(f"\n{P_YELLOW}Tekan Enter atau 'q' kapan saja untuk STOP server...{C_RESET}", end="", flush=True)

    try:
        input()
    except Exception:
        pass
    finally:
        httpd.shutdown()
        print(f"\n{P_SLATE}Web server dimatikan secara aman.{C_RESET}")
        time.sleep(0.5)

def send_telegram_doc():
    clear_screen()
    stats = get_csv_stats()
    render_banner(stats)

    if not CSV_FILE.exists():
        print(f"{P_YELLOW}⚠️  File CSV belum ada. Silakan panen akun dulu.{C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    cfg = load_config()
    saved_token = cfg.get("telegram_token", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
    saved_chat = cfg.get("telegram_chat_id", "1152978753")

    print(f" {C_BOLD}{P_PINK}✈️  KIRIM CSV KE TELEGRAM BOT{C_RESET}\n")
    tok_input = input(f"{P_PEACH}Bot Token {P_SLATE}[Enter untuk pakai saved]{C_RESET}: ").strip()
    token = tok_input if tok_input else saved_token

    if not token:
        print(f"{P_YELLOW}Token bot tidak boleh kosong!{C_RESET}")
        time.sleep(1)
        return

    chat_input = input(f"{P_PEACH}Chat ID {P_SLATE}[default: {saved_chat}]{C_RESET}: ").strip()
    chat_id = chat_input if chat_input else saved_chat

    cfg["telegram_token"] = token
    cfg["telegram_chat_id"] = chat_id
    save_config(cfg)

    print(f"\n{P_SKY}Mengunggah {CSV_FILE.name} ({stats['size_str']}) ke Telegram...{C_RESET}")

    caption = f"🌸 DeepAI Accounts Harvested\n🌾 Total Akun: {stats['ok']:,} Valid Key\n📁 File: deepai.csv ({stats['size_str']})"

    try:
        if not requests:
            print(f"\n{P_YELLOW}Module requests belum terinstall.{C_RESET}")
            input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
            return
        url = f"https://api.telegram.org/bot{token}/sendDocument"
        with open(CSV_FILE, "rb") as f:
            files = {"document": ("deepai.csv", f, "text/csv")}
            data = {"chat_id": chat_id, "caption": caption}
            res = requests.post(url, files=files, data=data, timeout=30).json()
        
        if res.get("ok"):
            print(f"\n{P_MINT}✨ Berhasil terkirim ke Telegram chat {chat_id}!{C_RESET}")
        else:
            print(f"\n{P_YELLOW}Gagal mengirim: {res.get('description', 'Unknown error')}{C_RESET}")
    except Exception as e:
        print(f"\n{P_YELLOW}Terjadi kesalahan koneksi: {e}{C_RESET}")

    input(f"\n{P_PEACH}Tekan Enter untuk kembali...{C_RESET}")

def export_keys_only():
    clear_screen()
    stats = get_csv_stats()
    render_banner(stats)

    if not CSV_FILE.exists():
        print(f"{P_YELLOW}⚠️  File CSV belum ada.{C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    out_keys = OUT_DIR / "api_keys_only.txt"
    keys = []
    with open(CSV_FILE, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            k = r.get("api_key", "").strip()
            if k and len(k) == 36 and r.get("status") == "ok":
                keys.append(k)

    with open(out_keys, "w", encoding="utf-8") as f:
        for k in keys:
            f.write(k + "\n")

    print(f" {C_BOLD}{P_MINT}🔑 EKSPOR API KEY SELESAI{C_RESET}\n")
    print(f"{P_WHITE}Total {P_MINT}{len(keys):,}{P_WHITE} valid API key berhasil diekspor ke:{C_RESET}")
    print(f"{P_SKY}{out_keys}{C_RESET}\n")
    print(f"{P_SLATE}File ini siap di-import ke 9Router, NextChat, Cherry Studio, dll.{C_RESET}")
    input(f"\n{P_PEACH}Tekan Enter untuk kembali...{C_RESET}")

def menu_share():
    opts = [
        ("1", "Instant Web Server (HTTP)", "Buka link download langsung untuk VPS / laptop", start_http_server),
        ("2", "Kirim ke Telegram Bot", "Upload otomatis file CSV ke akun/grup Telegram", send_telegram_doc),
        ("3", "Ekspor API Key Saja (.txt)", "Simpan hanya UUID key ke api_keys_only.txt", export_keys_only),
        ("0", "Kembali", "Kembali ke menu utama", None),
    ]

    sel_idx = 0
    while True:
        clear_screen()
        stats = get_csv_stats()
        render_banner(stats)
        print(f" {C_BOLD}{P_PINK}🚀 PILIH METODE SHARE / DOWNLOAD CSV{C_RESET}")
        print(f"{P_SLATE} Navigasi: {P_PEACH}↑/↓{P_SLATE} (atau {P_PEACH}W/S{P_SLATE}) lalu {P_PEACH}Enter{P_SLATE}, atau tekan angka [{P_PEACH}1-3{P_SLATE}]:{C_RESET}\n")

        for idx, (num, label, desc, _) in enumerate(opts):
            if idx == sel_idx:
                print(f" {P_PEACH}❯{C_RESET} {P_BG_SEL}{C_BOLD}{P_PINK}[{num}] {label:<30}{C_RESET} {P_SLATE}{desc}{C_RESET}")
            else:
                print(f"   {P_PEACH}[{num}]{C_RESET} {P_WHITE}{label:<30}{C_RESET} {P_SLATE}{desc}{C_RESET}")
        print(f"\n{P_SLATE}───────────────────────────────────────────────────────────────{C_RESET}")

        key = read_key()
        if key == "UP":
            sel_idx = (sel_idx - 1) % len(opts)
        elif key == "DOWN":
            sel_idx = (sel_idx + 1) % len(opts)
        elif key in ("ENTER", "1", "2", "3", "0"):
            chosen_num = key if key in ("1", "2", "3", "0") else opts[sel_idx][0]
            if chosen_num == "0":
                break
            handler = next(o[3] for o in opts if o[0] == chosen_num)
            if handler:
                handler()

# ---------------- MENU 4: TEST API KEY ----------------
def menu_test_key():
    clear_screen()
    stats = get_csv_stats()
    render_banner(stats)
    print(f" {C_BOLD}{P_YELLOW}🧪 TEST & VALIDASI API KEY KE DEEPAI{C_RESET}\n")

    if not stats["exists"] or stats["total"] == 0:
        print(f"{P_YELLOW}⚠️  Belum ada data akun untuk ditest.{C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    latest_key = None
    latest_email = None
    with open(CSV_FILE, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            if r.get("status") == "ok" and r.get("api_key"):
                latest_key = r.get("api_key")
                latest_email = r.get("email")

    if not latest_key:
        print(f"{P_YELLOW}Tidak ditemukan key dengan status 'ok' di CSV.{C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    uuid_ok = bool(re.match(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", latest_key, re.I))

    print(f"{P_WHITE}Akun Sample   :{C_RESET} {P_MINT}{latest_email}{C_RESET}")
    print(f"{P_WHITE}Masked Key    :{C_RESET} {P_SKY}{mask_key(latest_key)}{C_RESET}")
    print(f"{P_WHITE}Format UUID   :{C_RESET} {P_MINT}VALID (36 chars){C_RESET}" if uuid_ok else f"{P_YELLOW}INVALID{C_RESET}")
    print(f"\n{P_SLATE}Mengirim probe ke API endpoint DeepAI...{C_RESET}")

    t0 = time.time()
    try:
        if not requests:
            print(f"\n{P_YELLOW}Module requests belum terinstall.{C_RESET}")
            input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
            return
        url = "https://api.deepai.org/deepai_code/chat/completions"
        headers = {
            "api-key": latest_key,
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
        }
        payload = {
            "model": "deepai-chat",
            "messages": [{"role": "user", "content": "ping"}]
        }
        r = requests.post(url, json=payload, headers=headers, timeout=10)
        elapsed = (time.time() - t0) * 1000

        print(f"\n{P_LAVENDER}╭─────────────────────────────────────────────────────────────╮{C_RESET}")
        print(f"{P_LAVENDER}│  {P_WHITE}HTTP Status :{C_RESET} {P_MINT if r.status_code == 200 else P_YELLOW}{r.status_code} ({r.reason}){P_LAVENDER}                               │{C_RESET}")
        print(f"{P_LAVENDER}│  {P_WHITE}Latency     :{C_RESET} {P_SKY}{elapsed:.0f} ms{P_LAVENDER}                                         │{C_RESET}")
        print(f"{P_LAVENDER}│  {P_WHITE}Status Key  :{C_RESET} {P_MINT}Terdaftar & Aktif di database DeepAI{P_LAVENDER}             │{C_RESET}")
        print(f"{P_LAVENDER}╰─────────────────────────────────────────────────────────────╯{C_RESET}")
        print(f"\n{P_SLATE}💡 Catatan: Key siap pakai untuk routing 9Router & tools kompatibel.{C_RESET}")
    except Exception as e:
        print(f"\n{P_YELLOW}Error saat request: {e}{C_RESET}")

    input(f"\n{P_PEACH}Tekan Enter untuk kembali...{C_RESET}")

# ---------------- MENU 5: SYNC KE 9ROUTER ----------------
def menu_sync():
    clear_screen()
    stats = get_csv_stats()
    render_banner(stats)
    print(f" {C_BOLD}{P_MINT}🔄 SYNC KE 9ROUTER DATABASE{C_RESET}\n")

    sync_script = BASE_DIR / "sync_to_9router.py"
    if not sync_script.exists():
        print(f"{P_YELLOW}Script sync_to_9router.py tidak ditemukan di repo.{C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    if not DB_FILE.exists():
        print(f"{P_YELLOW}Database 9Router ({DB_FILE}) tidak ditemukan di sistem ini.{C_RESET}")
        print(f"{P_SLATE}(Fitur ini khusus dijalankan di VPS Utama tempat 9Router terpasang){C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    print(f"{P_SKY}Menjalankan ingest CSV ke SQLite 9Router...{C_RESET}")
    ret = os.system(f"python3 {sync_script}")
    if ret == 0:
        os.system("pm2 reload 9router --update-env 2>/dev/null || true")
        print(f"\n{P_MINT}✨ Sync dan reload 9Router berhasil dilakukan!{C_RESET}")
    else:
        print(f"\n{P_YELLOW}Gagal menjalankan sync_to_9router.py (Exit code: {ret}){C_RESET}")

    input(f"\n{P_PEACH}Tekan Enter untuk kembali...{C_RESET}")

# ---------------- MAIN CONTROLLER ----------------
def main():
    options = [
        ("1", "⚡ Quick Harvest Akun", "Pilih target 100/500/1000/5000 & threads", menu_harvest),
        ("2", "📊 Cek Statistik & Data", "Lihat total akun, status, dan 5 akun terakhir", menu_stats),
        ("3", "🚀 Auto Kirim / Share CSV", "Instant Web Server & kirim Telegram doc", menu_share),
        ("4", "🧪 Test Validasi API Key", "Uji coba kirim chat live ke DeepAI API", menu_test_key),
        ("5", "🔄 Sync ke 9Router", "Ingest key ke database 9Router lokal", menu_sync),
        ("0", "🚪 Keluar", "Tutup antarmuka TUI", None),
    ]

    selected_idx = 0

    while True:
        clear_screen()
        stats = get_csv_stats()
        render_banner(stats)
        render_menu([(o[0], o[1], o[2]) for o in options], selected_idx)

        key = read_key()
        if key == "UP":
            selected_idx = (selected_idx - 1) % len(options)
        elif key == "DOWN":
            selected_idx = (selected_idx + 1) % len(options)
        elif key in ("ENTER", "1", "2", "3", "4", "5", "0"):
            chosen_num = key if key in ("1", "2", "3", "4", "5", "0") else options[selected_idx][0]
            if chosen_num == "0":
                clear_screen()
                print(f"{P_PINK}Terima kasih telah menggunakan DeepAI Harvest TUI! 🤍{C_RESET}\n")
                break
            action = next(o[3] for o in options if o[0] == chosen_num)
            if action:
                action()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{P_SLATE}Program ditutup.{C_RESET}")
