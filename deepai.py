#!/usr/bin/env python3
"""
DeepAI Account Harvest & Management Pipeline
Crafted by Zykuan (@Zyknn) - MIT License

Entrypoint utama:
  - Tanpa argumen     : Menjalankan Interactive TUI Dashboard (menu panen, validasi, share)
  - Dengan argumen    : Menjalankan Headless CLI Harvest (untuk cronjob / bash script)
"""
from __future__ import annotations

import argparse
import sys


def main():
    # Tanpa argumen -> Default buka Interactive TUI Dashboard
    if len(sys.argv) == 1:
        from tui import main as tui_main
        return tui_main()

    # CLI Parser untuk Headless Scripting
    parser = argparse.ArgumentParser(
        prog="deepai",
        description="DeepAI High-Performance Account Harvest & GLM Validator — Crafted by Zykuan (@Zyknn)",
        epilog="Jalankan tanpa argumen ('python3 deepai.py') untuk membuka antarmuka interaktif TUI."
    )
    parser.add_argument("--tui", action="store_true", help="Buka antarmuka interaktif TUI")
    parser.add_argument("--count", "-c", type=int, default=100, help="Target jumlah akun yang dipanen (default: 100)")
    parser.add_argument("--workers", "-w", type=int, default=8, help="Jumlah thread worker paralel (default: 8)")
    parser.add_argument("--verify", "-v", action="store_true", help="Aktifkan verifikasi live GLM-5.3-flash per akun")

    # Subcommands opsional untuk kenyamanan CLI
    sub = parser.add_subparsers(dest="cmd", required=False)
    sub.add_parser("tui", help="Buka antarmuka interaktif TUI")
    
    sub_harvest = sub.add_parser("harvest", help="Panen akun massal secara headless")
    sub_harvest.add_argument("--count", "-c", type=int, default=100, help="Target jumlah akun")
    sub_harvest.add_argument("--workers", "-w", type=int, default=8, help="Jumlah thread worker")
    sub_harvest.add_argument("--verify", "-v", action="store_true", help="Aktifkan verifikasi live GLM")

    sub_reg = sub.add_parser("register", help="Alias untuk harvest")
    sub_reg.add_argument("--count", "-c", type=int, default=100)
    sub_reg.add_argument("--workers", "-w", type=int, default=8)
    sub_reg.add_argument("--verify", "-v", action="store_true")

    args = parser.parse_args()

    if args.tui or args.cmd == "tui":
        from tui import main as tui_main
        return tui_main()

    count = getattr(args, "count", 100)
    workers = getattr(args, "workers", 8)
    verify = getattr(args, "verify", False)

    from bulk_create import run_bulk_harvest, log
    log(f"Memulai headless harvest: target={count} akun, workers={workers}, verify_glm={verify}")
    res = run_bulk_harvest(count=count, workers=workers, verify_glm=verify)
    log(f"Panen selesai! Total: {res['count']} | OK: {res['ok']} | FAIL: {res['fail']} | Waktu: {res['elapsed']:.1f}s | Speed: {res['speed']:.2f} acc/s")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\n[!] Dihentikan pengguna.")
        sys.exit(0)
