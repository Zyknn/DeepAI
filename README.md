<div align="center">

# DeepAI Account Harvest & 9Router Integrator

High-performance automated account harvesting, auto-harvesting API key, and instant SQLite ingestion pipeline for **[DeepAI](https://deepai.org)** into **[9Router](https://github.com/alienxp03/9router)**.

[![Python](https://img.shields.io/badge/Python-3.10%2B-blue.svg?style=flat-square&logo=python&logoColor=white)](https://python.org)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg?style=flat-square)](LICENSE)
[![Speed](https://img.shields.io/badge/Speed-~2.7_acc%2Fs-orange.svg?style=flat-square)](https://github.com/Zyknn/DeepAI)
[![9Router](https://img.shields.io/badge/Integration-9Router_Ready-purple.svg?style=flat-square)](https://github.com/alienxp03/9router)
[![Author](https://img.shields.io/badge/Crafted_by-Zykuan_(@Zyknn)-black.svg?style=flat-square&logo=github)](https://github.com/Zyknn)

</div>

---

## About

High-performance automated account harvesting, auto-harvesting API key, and instant SQLite ingestion pipeline for DeepAI into 9Router. Designed for generating thousands of verified accounts without browser overhead and loading them directly into multi-key LLM proxies for free inference (`deepai/glm-5.3-flash`, `deepai/gpt-oss-120b`).

### Benchmark Produksi

| Metrik | Hasil Uji Lapangan |
| :--- | :--- |
| **Throughput harvesting** | ~2.7 akun / detik (12 concurrent worker threads) |
| **Kapasitas Batch** | 2.000 akun selesai dalam **~12 menit** (1.994 sukses, 6 timeout/retry) |
| **Throughput Ingest DB** | 2.000+ akun terindeks ke SQLite dalam **< 1.5 detik** |
| **Model LLM Aktif** | `deepai/glm-5.3-flash`, `deepai/gpt-oss-120b` |

---

## Architecture Pipeline

```text
[ Disposable Mailbox ] (api.mail.tm)
 │
 ▼
[ Proxy Pool / Direct VPS ] (Rotasi per thread)
 │
 ▼
[ Direct HTTP Register ] ──► POST https://api.deepai.org/daily-time-sync/registration/
 │
 ▼
[ Harvest UUID API Key ] ──► GET https://deepai.org/profile/ (Session Auth)
 │
 ├──► CSV Output : out_deepai/deepai.csv
 ├──► JSONL Output : out_deepai/deepai.jsonl
 └──► SQLite Ingest : ~/.9router/db/data.sqlite (Table: providerConnections)
 │
 ▼
 [ 9Router Multi-Key Load Balancer ]
 (Port 20128 : Chat SSE)
```

---

## Project Structure

```text
.
├── deepai.py          # Launcher utama CLI & TUI Dashboard
├── main.py            # Alias launcher entrypoint
├── tui.py             # Interactive TUI (animated harvest, stats, share, test)
├── bulk_create.py     # Engine utama: multi-threaded direct HTTP harvesting & live sync
├── sync_to_9router.py # Ingest tool: CSV -> 9Router SQLite DB
├── proxylist.py       # Helper proxy rotation pool
├── tempmail.py        # Helper mailbox generator & token handler (mail.tm)
├── util.py            # Logging helper & sanitasi proxy string
├── proxies.example.txt# Contoh struktur file konfigurasi proxy
├── requirements.txt   # Daftar dependensi Python
├── LICENSE            # Lisensi resmi MIT (Copyright Zykuan)
└── README.md
```

---

## Quickstart (Interactive TUI)

Cara paling praktis menjalankan harvesting dan manajemen akun adalah menggunakan antarmuka interaktif TUI:

```bash
git clone https://github.com/Zyknn/DeepAI.git
cd DeepAI
python3 deepai.py
```
*(Catatan: `python3 main.py` juga tetap didukung sebagai launcher)*

Antarmuka siap pakai tanpa konfigurasi tambahan:
- **[1] Quick Harvest:** Pilih target (100 / 500 / 1000 / 5000 multi-batch safe cooldown)
- **[2] Cek Statistik:** Ringkasan akun valid, gagal, ukuran CSV, dan 5 akun terakhir
- **[3] Auto Kirim / Share CSV:** Instant download web server & auto upload ke Telegram
- **[4] Test API Key:** Verifikasi format key & probe live ke endpoint DeepAI
- **[5] Sync ke 9Router:** Ingest langsung ke SQLite 9Router lokal

---

## Manual CLI Usage (Headless / Scripting)

### 1. Kloning Repositori & Setup Environment

```bash
git clone https://github.com/Zyknn/DeepAI.git
cd DeepAI

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Konfigurasi Proxy (Opsional)

Jika ingin memakai proxy rotasi, buat berkas `proxies_live.txt` atau `proxies.txt` pada root folder:

```text
http://user:password@proxy1.example.com:8080
http://user:password@proxy2.example.com:8080
```

> **Catatan Direct VPS:** Registrasi dan inferensi ke DeepAI dapat berjalan secara direct tanpa proxy selama subnet IP VPS tidak masuk daftar blokir Cloudflare.

### 3. Eksekusi harvesting Massal

Jalankan `bulk_create.py` dengan menentukan jumlah akun dan worker threads:

```bash
# Harvest 2.000 akun dengan 12 threads:
python3 bulk_create.py --count 2000 --workers 12

# Harvest skala kecil untuk pengujian (5 akun, 2 threads):
python3 bulk_create.py --count 5 --workers 2
```

Semua credential akun, email, password, dan API Key tersimpan otomatis di:
- `out_deepai/deepai.csv`
- `out_deepai/deepai.jsonl`

---

## 9Router Integration

### Sinkronisasi ke Database SQLite

Jika Anda menjalankan 9Router pada VPS yang sama, akun hasil harvesting dapat langsung di-ingest ke tabel `providerConnections`:

```bash
# Default target DB: ~/.9router/db/data.sqlite
python3 sync_to_9router.py

# Atau tentukan path database kustom:
ROUTER_DB_PATH="/path/to/data.sqlite" python3 sync_to_9router.py
```

Setelah ingest selesai, reload proses PM2 9Router:

```bash
pm2 reload 9router --update-env
```

---

## Troubleshooting

Bagian ini merangkum masalah teknis nyata yang sering ditemui di lapangan beserta langkah solusinya:

### 1. Masalah Tampilan UI 9Router: Hanya Muncul 5 Koneksi

* **Gejala:** Database SQLite menyimpan ribuan akun di tabel `providerConnections`, namun halaman dashboard UI 9Router (`/dashboard/providers`) hanya menampilkan 5 akun.
* **Penyebab:** Frontend 9Router memfilter koneksi berdasarkan nilai field strict `c.authType === "apikey"`. Jika script ingest menyimpan nilai `authType` sebagai `"api_key"` (memakai underscore `_`), baris tersebut tetap tersimpan di SQLite namun disaring/dilewati oleh komponen UI.
* **Solusi Perbaikan:**
 Jalankan perintah SQL berikut untuk menormalisasi nilai `authType`:
 ```bash
 sqlite3 ~/.9router/db/data.sqlite "UPDATE providerConnections SET authType = 'apikey' WHERE provider = 'openai-compatible-chat-deepai' AND authType = 'api_key';"
 pm2 reload 9router
 ```
 *(Script `bulk_create.py` dan `sync_to_9router.py` pada repositori ini sudah diperbarui dengan standar `authType = 'apikey'`)*.

---

### 2. Upstream 401 Unauthorized / Request Ditolak

* **Gejala:** Pemanggilan endpoint chat streaming melempar error `401 Unauthorized` atau menganggap request sebagai guest user tanpa kuota.
* **Penyebab:** Endpoint upstream DeepAI (`https://api.deepai.org/deepai_code`) mewajibkan header autentikasi bertipe:
 ```http
 api-key: [UUID_API_KEY]
 ```
 DeepAI **menolak** header standar OpenAI `Authorization: Bearer [UUID_API_KEY]`.
* **Solusi Perbaikan:**
 Pastikan adapter/proxy Anda (misal pada `open-sse/executors/default.js` 9Router) memetakan header khusus DeepAI:
 ```javascript
 if (targetUrl.includes("deepai.org")) {
 headers["api-key"] = connection.apiKey;
 delete headers["authorization"];
 delete headers["Authorization"];
 }
 ```

---

### 3. Cloudflare 403 Forbidden / Challenge saat Registrasi

* **Gejala:** Permintaan registrasi gagal dengan status HTTP `403` atau menerima respon Cloudflare challenge page.
* **Penyebab:** IP subnet terkena rate-limiting atau terdeteksi oleh Cloudflare bot detection.
* **Solusi Perbaikan:**
 - Masukkan daftar proxy residential atau rotating HTTP proxy ke file `proxies_live.txt`.
 - Kurangi intensitas thread jika menggunakan direct IP (misal `--workers 4`).
 - Script telah dilengkapi auto-retry dan fallback proxy per thread worker.

---

### 4. Error `sqlite3.OperationalError: database is locked`

* **Gejala:** Muncul pesan database terkunci saat menggunakan jumlah worker thread yang sangat banyak.
* **Penyebab:** Concurrency limit SQLite pada mode write bersamaan dari thread-thread Python.
* **Solusi Perbaikan:**
 - Script `bulk_create.py` telah dilengkapi mekanisme in-memory batching (commit per 50 akun sekaligus) yang dilindungi `threading.Lock()`.
 - Opsi alternatif: Lakukan harvesting murni ke CSV terlebih dahulu, lalu jalankan `sync_to_9router.py` setelah seluruh proses registrasi selesai.

---

## Author

Crafted with high attention to performance and resilience by:

* **Zykuan** ([@Zyknn](https://github.com/Zyknn))
* Project Lab: **XIEZUMEDIA Infrastructure**

---

## License

Proyek ini dirilis di bawah lisensi resmi **[MIT License](LICENSE)**.
Bebas dimodifikasi, didistribusikan, dan digunakan untuk keperluan riset otomasi dan pengujian sistem.
