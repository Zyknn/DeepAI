from __future__ import annotations

import csv
import json
import secrets
import time
import urllib.parse
from datetime import datetime, timedelta, timezone
from pathlib import Path


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
