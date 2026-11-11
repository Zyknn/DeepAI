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
from collections import deque
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
    from bulk_create import (
        run_bulk_harvest, run_bulk_farm, CSV_FILE, OUT_DIR, DB_FILE,
        probe_glm_key, UUID_RE, JSONL_FILE
    )
except ImportError:
    CSV_FILE = BASE_DIR / "out_deepai" / "deepai.csv"
    JSONL_FILE = BASE_DIR / "out_deepai" / "deepai.jsonl"
    OUT_DIR = BASE_DIR / "out_deepai"
    DB_FILE = Path.home() / ".9router/db/data.sqlite"
    UUID_RE = re.compile(r'^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$')
    run_bulk_harvest = None
    run_bulk_farm = None
    def probe_glm_key(k, timeout=7):
        return 0, False, 0, "No bulk_create engine"

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

def strip_ansi(text):
    return re.sub(r"\033\[[0-9;]*[a-zA-Z]", "", text)

def box_row(content, width=59):
    vlen = len(strip_ansi(content))
    pad = max(0, width - vlen)
    return f"{P_LAVENDER}│{C_RESET} {content}{' ' * pad} {P_LAVENDER}│{C_RESET}"

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
def run_progress_box(target, workers, safe_mode=False, verify_glm=False):
    clear_screen()
    mode_label = "GLM-Verified" if verify_glm else ("Safe Cooldown" if safe_mode else "Turbo")
    print(f"{P_LAVENDER}╭─────────────────────────────────────────────────────────────╮{C_RESET}")

    stop_evt = threading.Event()
    last_print = [0.0]
    recent_logs = deque(maxlen=4)
    spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    spin_idx = [0]
    first_render = [True]
    render_lock = threading.Lock()

    def format_log_row(item):
        w_name = item.get("worker", "W-1")
        t_str  = item.get("time", time.strftime("%H:%M:%S"))
        status = item.get("status", "ok")
        email  = item.get("email", "")
        lat    = item.get("latency_ms", 120)
        key    = item.get("key", "")

        if "@" in email:
            user_part, dom = email.split("@", 1)
            masked_user = (user_part[:3] + "***") if len(user_part) > 3 else (user_part + "***")
            masked_email = f"{masked_user}@{dom}"
        else:
            masked_email = email

        if len(masked_email) > 17:
            masked_email = masked_email[:14] + "..."

        if key and len(key) > 11:
            key_short = key[:8] + "..."
        elif key:
            key_short = key
        else:
            key_short = "-"

        if status == "ok":
            st_badge = f"{P_MINT}✓ 201{C_RESET}"
        else:
            st_badge = f"{P_YELLOW}✗ {status[:4]}{C_RESET}"

        return (
            f"{P_SLATE}{t_str}{C_RESET} {P_PEACH}[{w_name:<3}]{C_RESET} "
            f"{st_badge} {P_WHITE}{masked_email:<17}{C_RESET} "
            f"{P_SKY}{key_short:<11}{C_RESET} {P_SLATE}{lat:>3}ms{C_RESET}"
        )

    def on_progress(done, tot, ok, fail, speed, last_item=None):
        if last_item and isinstance(last_item, dict):
            recent_logs.append({
                "worker": last_item.get("worker", "W-1"),
                "time": last_item.get("created_at_wib", time.strftime("%H:%M:%S")),
                "status": last_item.get("status", "ok"),
                "email": last_item.get("email", ""),
                "latency_ms": last_item.get("latency_ms", 120),
                "key": last_item.get("api_key", ""),
            })

        now = time.time()
        if now - last_print[0] < 0.08 and done != tot:
            return
        last_print[0] = now

        pct = (done / tot) * 100 if tot > 0 else 0
        bar_len = 16
        filled = int(bar_len * (done / tot)) if tot > 0 else 0
        bar = f"{P_MINT}{'█' * filled}{P_SLATE}{'░' * (bar_len - filled)}{C_RESET}"

        rem_items = tot - done
        eta_sec = int(rem_items / speed) if speed > 0 else 0
        eta_str = f"{eta_sec}s" if eta_sec < 60 else f"{eta_sec // 60}m {eta_sec % 60}s"

        spin_char = spinner_frames[spin_idx[0] % len(spinner_frames)]
        spin_idx[0] += 1

        succ_rate = (ok / done * 100) if done > 0 else 100.0
        avg_lat = sum(l.get("latency_ms", 150) for l in recent_logs) / len(recent_logs) if recent_logs else 150

        header_line = f"{P_PEACH}{spin_char}{C_RESET} {C_BOLD}{P_SKY}HARVEST ENGINE{C_RESET} {P_SLATE}•{C_RESET} {P_MINT}{workers} Workers Active{C_RESET} {P_SLATE}[{mode_label}]{C_RESET}"

        prog_content = (
            f"[{bar}] {P_SKY}{pct:>5.1f}%{C_RESET} ({P_WHITE}{done:>4}/{tot}{C_RESET}) "
            f"{P_MINT}✓ {ok:<4}{C_RESET} {P_YELLOW}✗ {fail:<3}{C_RESET} "
            f"{P_PEACH}{speed:>4.1f}/s{C_RESET} {P_SLATE}~{eta_str}{C_RESET}"
        )

        title_content = f"{P_PEACH}📡{C_RESET} {C_BOLD}{P_PINK}LIVE WORKER DISPATCHES{C_RESET} {P_SLATE}• Realtime Stream{C_RESET}"

        footer_metrics = f" {P_SLATE}Rate:{C_RESET} {P_MINT}{succ_rate:>5.1f}%{C_RESET}  {P_SLATE}│ Latency:{C_RESET} {P_SKY}{avg_lat:>3.0f}ms{C_RESET}  {P_SLATE}│ Out:{C_RESET} {P_WHITE}deepai.csv{C_RESET}"

        lines = [
            box_row(header_line),
            box_row(prog_content),
            f"{P_LAVENDER}├─────────────────────────────────────────────────────────────┤{C_RESET}",
            box_row(title_content),
        ]

        for log_item in recent_logs:
            lines.append(box_row(format_log_row(log_item)))

        for _ in range(4 - len(recent_logs)):
            lines.append(box_row(f"{P_SLATE}  ... waiting for worker dispatches ...{C_RESET}"))

        lines.append(f"{P_LAVENDER}├─────────────────────────────────────────────────────────────┤{C_RESET}")
        lines.append(box_row(footer_metrics))
        lines.append(f"{P_LAVENDER}╰─────────────────────────────────────────────────────────────╯{C_RESET}")

        with render_lock:
            if not sys.stdout.isatty():
                sys.stdout.write(f"\rProgress: {done}/{tot} ({pct:.1f}%) | OK: {ok} | FAIL: {fail} | Speed: {speed:.1f}/s\n")
                sys.stdout.flush()
                return

            if not first_render[0]:
                sys.stdout.write(f"\033[{len(lines)}A\r")
            first_render[0] = False
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()

    try:
        engine = run_bulk_harvest or run_bulk_farm
        if not engine:
            print(f"\n{P_YELLOW}Engine bulk_create tidak ditemukan.{C_RESET}")
            return
        res = engine(count=target, workers=workers, progress_cb=on_progress, stop_event=stop_evt, verify_glm=verify_glm)
        if first_render[0]:
            print(f"{P_LAVENDER}╰─────────────────────────────────────────────────────────────╯{C_RESET}")
        print(f"\n{P_MINT}✨ SELESAI!{C_RESET} Berhasil panen {P_MINT}{res['ok']}{C_RESET} akun baru ({res['fail']} gagal) dalam {P_SKY}{res['elapsed']:.1f}s{C_RESET}.")
        print(f"{P_SLATE}Data otomatis tersimpan di: {P_WHITE}{CSV_FILE}{C_RESET}")
    except KeyboardInterrupt:
        stop_evt.set()
        print(f"\n\n{P_YELLOW}⚠️  Harvest dihentikan pengguna.{C_RESET} Akun yang sudah didapat tetap aman tersimpan di CSV.")

    print(f"\n{P_PEACH}Tekan Enter atau tombol apa saja untuk kembali ke menu...{C_RESET}", end="", flush=True)
    try:
        read_key()
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

            # Mode Selection: Turbo vs Verified
            sel_mode_idx = 0
            mode_options = [
                ("1", "Mode Turbo (Rekomendasi)", "Kecepatan ~6-10 acc/s. Registrasi cepat + validasi UUID otomatis."),
                ("2", "Mode Verified (GLM Deep Probe)", "Kecepatan ~1 acc/s. Auto-test chat GLM-5.3-Flash per akun baru."),
            ]
            verify_glm = False
            while True:
                clear_screen()
                render_banner(stats)
                print(f" {C_BOLD}{P_PINK}⚡ PILIH MODE HARVEST{C_RESET}")
                print(f"{P_SLATE} Navigasi: {P_PEACH}↑/↓{P_SLATE} lalu {P_PEACH}Enter{P_SLATE}, atau tekan angka [{P_PEACH}1/2{P_SLATE}]:{C_RESET}\n")
                for m_i, (m_num, m_title, m_desc) in enumerate(mode_options):
                    if m_i == sel_mode_idx:
                        print(f" {P_PEACH}❯{C_RESET} {P_BG_SEL}{C_BOLD}{P_PINK}[{m_num}] {m_title:<32}{C_RESET} {P_SLATE}{m_desc}{C_RESET}")
                    else:
                        print(f"   {P_PEACH}[{m_num}]{C_RESET} {P_WHITE}{m_title:<32}{C_RESET} {P_SLATE}{m_desc}{C_RESET}")
                print(f"\n{P_SLATE}───────────────────────────────────────────────────────────────{C_RESET}")
                
                m_key = read_key()
                if m_key == "UP":
                    sel_mode_idx = (sel_mode_idx - 1) % len(mode_options)
                elif m_key == "DOWN":
                    sel_mode_idx = (sel_mode_idx + 1) % len(mode_options)
                elif m_key in ("1", "2"):
                    verify_glm = (m_key == "2")
                    break
                elif m_key == "ENTER":
                    verify_glm = (mode_options[sel_mode_idx][0] == "2")
                    break
                elif m_key in ("0", "q", "Q", "ESC"):
                    sel_mode_idx = -1
                    break

            if sel_mode_idx == -1:
                continue

            if chosen_num == "4":
                # Multi-batch safe cooldown
                batches = 5
                per_batch = 1000
                for b_i in range(1, batches + 1):
                    run_progress_box(per_batch, workers, safe_mode=True, verify_glm=verify_glm)
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
                run_progress_box(target, workers, verify_glm=verify_glm)
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
            self.wfile.write(b"File not found\n")
            return

        client_ip = self.client_address[0]
        sys.stdout.write(f"\n {P_MINT}📥 [{datetime.now().strftime('%H:%M:%S')}] Request download dari {client_ip} diterima! Mengirim CSV...{C_RESET}\n")
        sys.stdout.flush()
        self.send_response(200)
        self.send_header("Content-Type", "text/csv; charset=utf-8")
        self.send_header("Content-Disposition", 'attachment; filename="deepai.csv"')
        self.send_header("Content-Length", str(CSV_FILE.stat().st_size))
        self.end_headers()
        with open(CSV_FILE, "rb") as f:
            shutil.copyfileobj(f, self.wfile)
        sys.stdout.write(f" {P_MINT}✨ File deepai.csv sukses terkirim ke {client_ip}!{C_RESET}\n")
        sys.stdout.flush()

    def log_message(self, format, *args):
        pass  # Supress standard raw log

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
    print(box_row(f" {P_WHITE}File CSV siap disedot langsung dari browser / terminal:{C_RESET}"))
    print(box_row(""))
    print(box_row(f" {P_PEACH}👉 Link Download Langsung:{C_RESET}"))
    print(box_row(f"    {C_BOLD}{P_SKY}{dl_url}{C_RESET}"))
    print(box_row(""))
    print(box_row(f" {P_PEACH}👉 Perintah Sedot di VPS Lain / Laptop:{C_RESET}"))
    print(box_row(f"    {P_MINT}curl -s {dl_url} -o deepai.csv{C_RESET}"))
    print(f"{P_LAVENDER}╰─────────────────────────────────────────────────────────────╯{C_RESET}")

    print(f"\n {P_MINT}🟢 Server aktif mendengarkan di port {port}...{C_RESET}")
    print(f" {P_PEACH}Ketik {C_BOLD}'q'{C_RESET}{P_PEACH} lalu Enter (atau Ctrl+C) untuk STOP server:{C_RESET} ", end="", flush=True)

    try:
        while True:
            cmd = input().strip().lower()
            if cmd in ("q", "quit", "exit", "stop", "kembali", "batal"):
                break
            print(f" {P_SLATE}Server masih aktif di port {port}. Ketik 'q' untuk keluar:{C_RESET} ", end="", flush=True)
    except (KeyboardInterrupt, Exception):
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

# ---------------- MENU 4: TEST & VALIDASI API KEY ----------------
def quick_probe_single_key(stats):
    clear_screen()
    render_banner(stats)
    print(f" {C_BOLD}{P_YELLOW}🧪 QUICK PROBE 1 SAMPLE KEY (GLM-5.3-FLASH){C_RESET}\n")

    if not stats["exists"] or stats["total"] == 0:
        print(f"{P_YELLOW}⚠️  Belum ada data akun untuk ditest.{C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    latest_key = None
    latest_email = None
    with open(CSV_FILE, "r", encoding="utf-8", errors="ignore") as f:
        reader = csv.DictReader(f)
        for r in reader:
            k = (r.get("api_key") or "").strip()
            if r.get("status") == "ok" and UUID_RE.match(k):
                latest_key = k
                latest_email = r.get("email")

    if not latest_key:
        print(f"{P_YELLOW}Tidak ditemukan key UUID valid di CSV.{C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    print(f"{P_WHITE}Akun Sample   :{C_RESET} {P_MINT}{latest_email}{C_RESET}")
    print(f"{P_WHITE}Masked Key    :{C_RESET} {P_SKY}{mask_key(latest_key)}{C_RESET}")
    print(f"{P_WHITE}Model Target  :{C_RESET} {P_PEACH}glm-5.3-flash{C_RESET}")
    print(f"\n{P_SLATE}Mengirim prompt probe ke API DeepAI Code...{C_RESET}")

    sc, is_ok, lat, detail = probe_glm_key(latest_key, timeout=10)

    print(f"\n{P_LAVENDER}╭─────────────────────────────────────────────────────────────╮{C_RESET}")
    st_color = P_MINT if is_ok else P_YELLOW
    status_msg = "OK - Chat Berhasil" if is_ok else "FAILED"
    row1 = f"  HTTP Status : {st_color}{sc} ({status_msg}){C_RESET}"
    row2 = f"  Latency     : {P_SKY}{lat} ms{C_RESET}"
    status_str = "AKTIF & SIAP PAKAI 9ROUTER" if is_ok else "DEAD / PERLU PURGE"
    row3 = f"  Status Key  : {st_color}{status_str}{C_RESET}"

    print(box_row(row1))
    print(box_row(row2))
    print(box_row(row3))
    print(f"{P_LAVENDER}╰─────────────────────────────────────────────────────────────╯{C_RESET}")
    if detail:
        print(f"\n{P_SLATE}Respon snippet: {P_WHITE}{detail[:120]}{C_RESET}")

    input(f"\n{P_PEACH}Tekan Enter untuk kembali...{C_RESET}")


def test_custom_key_manual():
    clear_screen()
    stats = get_csv_stats()
    render_banner(stats)
    print(f" {C_BOLD}{P_YELLOW}🎯 TEST MANUAL CUSTOM KEY{C_RESET}\n")
    key = input(f"{P_PEACH}Masukkan API Key DeepAI: {C_RESET}").strip()
    if not key:
        return

    print(f"\n{P_SLATE}Menguji key ke endpoint DeepAI Code (model glm-5.3-flash)...{C_RESET}")
    sc, is_ok, lat, detail = probe_glm_key(key, timeout=10)
    st_color = P_MINT if is_ok else P_YELLOW
    print(f"\nResult: HTTP {st_color}{sc}{C_RESET} | Latency: {lat}ms | Valid: {is_ok}")
    if detail:
        print(f"Detail: {detail}")
    input(f"\n{P_PEACH}Tekan Enter untuk kembali...{C_RESET}")


def run_batch_validate(workers=5):
    clear_screen()
    stats = get_csv_stats()
    render_banner(stats)
    print(f" {C_BOLD}{P_YELLOW}🧹 GLM-5.3-FLASH BATCH VALIDATOR & AUTO-PURGER{C_RESET}")
    print(f"{P_SLATE} Endpoint: https://api.deepai.org/deepai_code/chat/completions{C_RESET}\n")

    if not CSV_FILE.exists():
        print(f"{P_YELLOW}File CSV tidak ditemukan: {CSV_FILE}{C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    with open(CSV_FILE, "r", encoding="utf-8", errors="ignore") as f:
        all_rows = list(csv.DictReader(f))

    if not all_rows:
        print(f"{P_YELLOW}CSV kosong.{C_RESET}")
        input(f"\n{P_PEACH}Tekan Enter...{C_RESET}")
        return

    print(f"{P_WHITE}Total akun di CSV :{C_RESET} {P_MINT}{len(all_rows)}{C_RESET}")
    print(f"{P_SLATE}Validator akan menguji setiap akun dengan model GLM-5.3-Flash.{C_RESET}")
    print(f"{P_SLATE}Akun yang mati (401/403/invalid/format non-UUID) akan otomatis di-purge.{C_RESET}\n")

    confirm = input(f"{P_PEACH}Mulai validasi dan purge akun mati? [Y/n]: {C_RESET}").strip().lower()
    if confirm == "n":
        return

    w_str = input(f"{P_PEACH}Jumlah threads worker [default: 5 (aman rate limit)]: {C_RESET}").strip()
    workers = int(w_str) if w_str.isdigit() and int(w_str) > 0 else 5

    clear_screen()
    print(f"{P_LAVENDER}╭─────────────────────────────────────────────────────────────╮{C_RESET}")

    valid_rows = []
    purged_rows = []
    recent_logs = deque(maxlen=4)
    spinner_frames = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]
    spin_idx = [0]
    first_render = [True]
    render_lock = threading.Lock()
    done_count = [0]
    start_time = time.time()
    tot = len(all_rows)

    def format_val_log(item):
        w_name = item.get("worker", "V-1")
        t_str  = item.get("time", time.strftime("%H:%M:%S"))
        is_ok  = item.get("is_ok", False)
        sc     = item.get("status_code", 0)
        email  = item.get("email", "")
        lat    = item.get("latency_ms", 0)
        key    = item.get("key", "")

        if "@" in email:
            u, d = email.split("@", 1)
            masked_email = f"{u[:3]}***@{d}"
        else:
            masked_email = email
        if len(masked_email) > 14:
            masked_email = masked_email[:11] + "..."

        key_short = (key[:6] + "...") if len(key) > 9 else (key or "-")

        if is_ok:
            st_badge = f"{P_MINT}✓ {sc:<3}{C_RESET}"
            tag = f"{P_MINT}[KEEP]{C_RESET}"
        else:
            st_badge = f"{P_YELLOW}✗ {sc:<3}{C_RESET}"
            tag = f"{P_YELLOW}[DEL]{C_RESET}"

        return (
            f"{P_SLATE}{t_str}{C_RESET} {P_PEACH}[{w_name:<3}]{C_RESET} "
            f"{st_badge} {P_WHITE}{masked_email:<14}{C_RESET} "
            f"{P_SKY}{key_short:<9}{C_RESET} {P_SLATE}{lat:>3}ms{C_RESET} {tag}"
        )

    def render_val_box():
        done = done_count[0]
        ok = len(valid_rows)
        fail = len(purged_rows)
        elapsed = time.time() - start_time
        speed = done / elapsed if elapsed > 0 else 0
        pct = (done / tot) * 100 if tot > 0 else 0

        bar_len = 16
        filled = int(bar_len * (done / tot)) if tot > 0 else 0
        bar = f"{P_MINT}{'█' * filled}{P_SLATE}{'░' * (bar_len - filled)}{C_RESET}"

        rem_items = tot - done
        eta_sec = int(rem_items / speed) if speed > 0 else 0
        eta_str = f"{eta_sec}s" if eta_sec < 60 else f"{eta_sec // 60}m {eta_sec % 60}s"

        spin_char = spinner_frames[spin_idx[0] % len(spinner_frames)]
        spin_idx[0] += 1

        pass_rate = (ok / done * 100) if done > 0 else 100.0

        header_line = f"{P_PEACH}{spin_char}{C_RESET} {C_BOLD}{P_SKY}GLM VALIDATOR ENGINE{C_RESET} {P_SLATE}•{C_RESET} {P_MINT}{workers} Workers{C_RESET} {P_SLATE}[GLM-5.3-Flash]{C_RESET}"

        prog_content = (
            f"[{bar}] {P_SKY}{pct:>5.1f}%{C_RESET} ({P_WHITE}{done:>4}/{tot}{C_RESET}) "
            f"{P_MINT}✓ {ok:<4}{C_RESET} {P_YELLOW}✗ {fail:<3}{C_RESET} "
            f"{P_PEACH}{speed:>4.1f}/s{C_RESET} {P_SLATE}~{eta_str}{C_RESET}"
        )

        title_content = f"{P_PEACH}📡{C_RESET} {C_BOLD}{P_PINK}LIVE VALIDATION STREAM{C_RESET} {P_SLATE}• GLM Status Log{C_RESET}"

        footer_metrics = f" {P_SLATE}Pass:{C_RESET} {P_MINT}{pass_rate:>5.1f}%{C_RESET}  {P_SLATE}│ Valid:{C_RESET} {P_MINT}{ok}{C_RESET}  {P_SLATE}│ Purged:{C_RESET} {P_YELLOW}{fail}{C_RESET}  {P_SLATE}│ Speed:{C_RESET} {P_PEACH}{speed:.1f}/s{C_RESET}"

        lines = [
            box_row(header_line),
            box_row(prog_content),
            f"{P_LAVENDER}├─────────────────────────────────────────────────────────────┤{C_RESET}",
            box_row(title_content),
        ]

        for log_item in recent_logs:
            lines.append(box_row(format_val_log(log_item)))

        for _ in range(4 - len(recent_logs)):
            lines.append(box_row(f"{P_SLATE}  ... probing keys with GLM ...{C_RESET}"))

        lines.append(f"{P_LAVENDER}├─────────────────────────────────────────────────────────────┤{C_RESET}")
        lines.append(box_row(footer_metrics))
        lines.append(f"{P_LAVENDER}╰─────────────────────────────────────────────────────────────╯{C_RESET}")

        with render_lock:
            if not sys.stdout.isatty():
                sys.stdout.write(f"\rValidate: {done}/{tot} ({pct:.1f}%) | Valid: {ok} | Dead: {fail}\n")
                sys.stdout.flush()
                return

            if not first_render[0]:
                sys.stdout.write(f"\033[{len(lines)}A\r")
            first_render[0] = False
            sys.stdout.write("\n".join(lines) + "\n")
            sys.stdout.flush()

    task_q = queue.Queue()
    for row in all_rows:
        task_q.put(row)

    def val_worker(w_idx):
        while True:
            try:
                row = task_q.get_nowait()
            except queue.Empty:
                break

            key = (row.get("api_key") or "").strip()
            email = row.get("email", "")

            if not key or not UUID_RE.match(key):
                is_ok = False
                sc = 400
                lat = 10
            else:
                sc, is_ok, lat, _ = probe_glm_key(key, timeout=7)

            with render_lock:
                done_count[0] += 1
                log_entry = {
                    "worker": f"V-{w_idx}",
                    "time": time.strftime("%H:%M:%S"),
                    "is_ok": is_ok,
                    "status_code": sc,
                    "email": email,
                    "latency_ms": lat,
                    "key": key,
                }
                recent_logs.append(log_entry)
                if is_ok:
                    valid_rows.append(row)
                else:
                    purged_rows.append(row)

            render_val_box()
            task_q.task_done()

    threads = []
    for i in range(workers):
        t = threading.Thread(target=val_worker, args=(i + 1,))
        t.daemon = True
        t.start()
        threads.append(t)

    try:
        while any(t.is_alive() for t in threads):
            time.sleep(0.08)
    except KeyboardInterrupt:
        print(f"\n\n{P_YELLOW}⚠️  Validasi dihentikan pengguna.{C_RESET}")

    for t in threads:
        t.join(timeout=1.0)

    render_val_box()

    # Backup & Simpan hasil purge
    bak_file = CSV_FILE.with_suffix(".csv.bak")
    shutil.copyfile(CSV_FILE, bak_file)

    fieldnames = ["email", "password", "api_key", "status", "proxy", "created_at_wib", "latency_ms"]
    with open(CSV_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(valid_rows)

    if JSONL_FILE.exists():
        jsonl_bak = JSONL_FILE.with_suffix(".jsonl.bak")
        shutil.copyfile(JSONL_FILE, jsonl_bak)
        with open(JSONL_FILE, "w", encoding="utf-8") as f:
            for vr in valid_rows:
                f.write(json.dumps(vr) + "\n")

    print(f"\n{P_MINT}✨ VALIDASI & PURGE SELESAI!{C_RESET}")
    print(f" {P_WHITE}Total Akun Dicek :{C_RESET} {P_SKY}{tot}{C_RESET}")
    print(f" {P_WHITE}Akun Valid (Kept):{C_RESET} {P_MINT}{len(valid_rows)}{C_RESET} (tersimpan di {CSV_FILE})")
    print(f" {P_WHITE}Akun Mati (Purge):{C_RESET} {P_YELLOW}{len(purged_rows)}{C_RESET}")
    print(f" {P_WHITE}Backup Asli       :{C_RESET} {P_SLATE}{bak_file}{C_RESET}")

    if DB_FILE.exists():
        try:
            sync_choice = input(f"\n{P_PEACH}Sinkronkan akun valid ke 9Router sekarang? [Y/n]: {C_RESET}").strip().lower()
        except Exception:
            sync_choice = "n"
        if sync_choice != "n":
            sync_script = BASE_DIR / "sync_to_9router.py"
            if sync_script.exists():
                os.system(f"python3 {sync_script}")
                os.system("pm2 reload 9router --update-env >/dev/null 2>&1 || true")
                print(f"{P_MINT}✓ Berhasil disinkronkan ke 9Router.{C_RESET}")

    input(f"\n{P_PEACH}Tekan Enter untuk kembali ke menu...{C_RESET}")


def menu_test_key():
    while True:
        clear_screen()
        stats = get_csv_stats()
        render_banner(stats)
        print(f" {C_BOLD}{P_YELLOW}🧪 TEST & VALIDASI API KEY (GLM-5.3-FLASH){C_RESET}\n")
        print(f"   {P_PEACH}[1]{C_RESET} {C_BOLD}{P_WHITE}Quick Probe 1 Sample Key{C_RESET}")
        print(f"       {P_SLATE}Uji 1 akun terakhir dengan model GLM-5.3-Flash secara live.{C_RESET}\n")
        print(f"   {P_PEACH}[2]{C_RESET} {C_BOLD}{P_WHITE}Batch Validate & Auto-Purge CSV (Filter Akun Mati){C_RESET}")
        print(f"       {P_SLATE}Uji SEMUA akun di CSV, hapus akun mati/invalid, sisakan yang 200 OK.{C_RESET}\n")
        print(f"   {P_PEACH}[3]{C_RESET} {C_BOLD}{P_WHITE}Test Custom Key Manual{C_RESET}")
        print(f"       {P_SLATE}Masukkan API key manual untuk dicek langsung.{C_RESET}\n")
        print(f"   {P_PEACH}[0]{C_RESET} {P_WHITE}Kembali ke Menu Utama{C_RESET}\n")
        print(f"{P_SLATE}───────────────────────────────────────────────────────────────{C_RESET}")

        choice = input(f"{P_PEACH}Pilihan [0-3]: {C_RESET}").strip()
        if choice == "0":
            break
        elif choice == "1":
            quick_probe_single_key(stats)
        elif choice == "2":
            run_batch_validate(workers=5)
        elif choice == "3":
            test_custom_key_manual()

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
