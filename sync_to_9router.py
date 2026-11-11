#!/usr/bin/env python3
"""
Sync akun dari deepai.csv ke data.sqlite 9Router.
"""
import csv
import json
import sqlite3
import sys
import uuid
from datetime import datetime, timezone
import os
from pathlib import Path

BASE_DIR = Path(__file__).parent.resolve()
CSV_FILE = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else (BASE_DIR / "out_deepai" / "deepai.csv")
DB_FILE = Path(os.environ.get("ROUTER_DB_PATH", Path.home() / ".9router/db/data.sqlite"))

def sync():
    if not CSV_FILE.exists():
        print("CSV tidak ditemukan")
        return
    if not DB_FILE.exists():
        print("DB 9Router tidak ditemukan")
        return

    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    existing = set()
    for row in cur.execute("SELECT email FROM providerConnections WHERE provider = 'openai-compatible-chat-deepai'"):
        if row[0]:
            existing.add(row[0])

    print(f"Akun DeepAI di 9Router saat ini: {len(existing)}")

    new_count = 0
    now_iso = datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")

    with open(CSV_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for r in reader:
            email = r.get("email")
            api_key = r.get("api_key")
            status = r.get("status")
            if not email or not api_key or status != "ok":
                continue
            if email in existing:
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
                INSERT INTO providerConnections
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
            existing.add(email)
            new_count += 1

    conn.commit()
    conn.close()
    print(f"Berhasil menambahkan {new_count} akun baru ke 9Router. Total: {len(existing)}")

if __name__ == "__main__":
    sync()
