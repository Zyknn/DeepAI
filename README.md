# DeepAI Account Farm & API Integrator

Tool automasi farming akun [DeepAI](https://deepai.org) berkecepatan tinggi dengan auto-harvest API Key, rotasi proxy multi-threading, dan integrasi instan ke [9Router](https://github.com/alienxp03/9router).

---

## ⚡ Fitur Utama

- **Ultra-Fast Direct HTTP Farming (`bulk_create.py`)**:
  - Direct HTTP register via `api.deepai.org/daily-time-sync/registration/` (tanpa browser overhead).
  - Auto-fetch UUID API Key langsung dari dashboard profile.
  - Multi-threaded queue worker dengan rotasi proxy otomatis.
  - Kecepatan **~2.5 - 3 akun/detik** (2.000 akun selesai dalam ~12 menit).
- **Playwright Automation (`deepai.py`)**:
  - Mode browser Chromium headless alternatif.
- **Export Formats**:
  - Menyimpan hasil akun ke CSV (`out_deepai/deepai.csv`) & JSONL (`out_deepai/deepai.jsonl`).
- **9Router Integration (`sync_to_9router.py`)**:
  - Ingest akun massal langsung ke database SQLite 9Router (`providerConnections`).
  - Siap pakai untuk inferensi model AI gratis (seperti `deepai/glm-5.3-flash`, `deepai/gpt-oss-120b`).

---

## 📁 Struktur File

```
├── bulk_create.py         # Script utama: multi-threaded direct HTTP farming
├── sync_to_9router.py     # Sinkronisasi hasil CSV ke SQLite 9Router
├── deepai.py              # Script registrasi alternatif via Playwright Chromium
├── proxylist.py           # Helper pool dan rotasi proxy
├── tempmail.py            # Helper generator disposable mailbox (api.mail.tm)
├── util.py                # Utilitas logging, parsing proxy, dan delay
├── proxies.example.txt    # Contoh format daftar proxy
├── requirements.txt       # Dependensi Python
└── README.md
```

---

## 🚀 Panduan Instalasi & Penggunaan

### 1. Persiapan Environment

```bash
git clone https://github.com/Zyknn/DeepAI.git
cd DeepAI

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Setup Proxy (Opsional)

Jika ingin menggunakan proxy, buat file `proxies_live.txt` atau `proxies.txt` di root direktori:

```text
http://username:password@proxy_host:proxy_port
http://proxy_host:proxy_port
```

*Catatan: Registrasi dan inferensi chat DeepAI juga dapat berjalan direct tanpa proxy selama IP tidak terkena Cloudflare rate-limit.*

### 3. Jalankan Farming Massal

Jalankan `bulk_create.py` dengan parameter jumlah akun dan worker thread:

```bash
# Contoh: Farm 2.000 akun dengan 12 worker threads
python3 bulk_create.py --count 2000 --workers 12
```

Hasil akun akan otomatis tersimpan di:
- `out_deepai/deepai.csv`
- `out_deepai/deepai.jsonl`

---

## 🔌 Integrasi ke 9Router

DeepAI menyediakan akses gratis ke berbagai model LLM. Untuk memasukkan ribuan API key hasil farm ke 9Router:

1. Pastikan 9Router terpasang (database default di `~/.9router/db/data.sqlite`).
2. Jalankan sync:
   ```bash
   python3 sync_to_9router.py
   ```
3. Reload 9Router:
   ```bash
   pm2 reload 9router --update-env
   ```

### ⚠️ Catatan Penting untuk Upstream DeepAI
Endpoint upstream DeepAI (`https://api.deepai.org/deepai_code`) memerlukan header otentikasi berupa:
```http
api-key: <UUID_API_KEY>
```
*(DeepAI menolak header standar `Authorization: Bearer <key>`)*. Pastikan executor upstream / proxy Anda memetakan header otentikasi ke `api-key`.

---

## 📄 Lisensi
MIT License. Dibuat untuk tujuan riset dan pengujian otomatisasi.
