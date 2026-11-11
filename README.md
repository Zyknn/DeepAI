# DeepAI Account Farm

Farm akun [deepai.org](https://deepai.org) otomatis — email acak via [api.mail.tm](https://api.mail.tm) (tempmail gratis, tanpa API key).

- **GitHub**: https://github.com/HihuProject
- **Dev**: HihuProject

---

## Logika / Alur Kerja

```
┌─────────────────────┐
│  TempmailInbox      │  api.mail.tm -> bikin mailbox sekali-pakai
│  .provision()       │  (gratis, tanpa API key)
└──────────┬──────────┘
           │  email acak
           v
┌─────────────────────┐
│  Playwright Chromium│  buka https://deepai.org/
│  openLogin()        │  -> toggleAuthOption('signup')
└──────────┬──────────┘
           │
           v
┌─────────────────────┐
│  Isi form signup    │  #user-email / #user-password / #confirm-user-password
│  submitAuth()       │  -> POST api.deepai.org/daily-time-sync/registration/
└──────────┬──────────┘
           │  201 + session cookie (tanpa verifikasi email, tanpa captcha)
           v
┌─────────────────────┐
│  /dashboard/profile │  baca input.api-password
│  ambil API key UUID │  validasi regex UUID
└──────────┬──────────┘
           │
           v
┌─────────────────────┐
│  Simpan hasil       │  out_deepai/deepai.jsonl + deepai.csv
└─────────────────────┘
```

### Langkah ringkas

1. **Provision mailbox** — `TempmailInbox.provision()` bikin email sekali-pakai via api.mail.tm.
2. **Buka deepai.org** — Playwright Chromium, `openLogin()` lalu `toggleAuthOption('signup')`.
3. **Submit signup** — isi email/password/confirm, `submitAuth()`. Server balas `201` + session cookie (tanpa verifikasi email, tanpa captcha).
4. **Ambil API key** — buka `/dashboard/profile`, baca `input.api-password`, validasi format UUID.
5. **Simpan** — tulis ke `deepai.jsonl` + `deepai.csv` (email, password, api_key, status, proxy, created_at_wib).

### Password generator

`gen_password(n=20)` — 20 karakter campuran (huruf besar/kecil/angka/simbol), dijamin minimal 1 dari tiap kategori via `secrets` (cryptographically secure).

### Proxy support

`ProxyPool` dari `proxylist.py` — rotasi proxy per akun, opsional validasi. Lewati dengan `--no-validate-proxy`.

---

## Catatan Penting

- API key akun free **valid** tapi endpoint model balas `402` (butuh Pro).
- `/deepai_code/chat/completions` balas `403 social_login_required` untuk akun email baru.
- Modul tetap menyimpan key untuk arsip; gunakan bila akun punya akses Pro/Google.
- `curl`/`requests` diblok CloudFront `403` — **wajib browser nyata** (Chromium via Playwright).

### Perubahan dari versi asli

Pemasok email **Temfex** (`temfex.com`, butuh `TEMFEX_API_KEY`) diganti jadi **tempmail api.mail.tm** (gratis, tanpa API key).

---

## Instalasi

```bash
pip install playwright
playwright install chromium
```

## Penggunaan

```bash
# farm 5 akun (default, headless)
python -m relayfarm.deepai register

# farm 10 akun, tampilkan browser, pakai proxy
python -m relayfarm.deepai register --count 10 --headed --proxy-file proxies.txt

# custom delay antar akun (detik)
python -m relayfarm.deepai register --count 20 --delay-min 10 --delay-max 30
```

### Opsi CLI

| Flag | Default | Keterangan |
|------|---------|------------|
| `--count` | `5` | Jumlah akun yang di-farm |
| `--proxy-file` | `None` | File berisi daftar proxy (1 per baris) |
| `--no-validate-proxy` | `False` | Lewati validasi proxy |
| `--headed` | `False` | Tampilkan browser (tidak headless) |
| `--out-dir` | `out_deepai` | Direktori output |
| `--delay-min` | `5` | Delay minimum antar akun (detik) |
| `--delay-max` | `15` | Delay maksimum antar akun (detik) |

---

## Output

- `out_deepai/deepai.jsonl` — satu JSON object per baris
- `out_deepai/deepai.csv` — kolom: `email, password, api_key, status, proxy, created_at_wib`

### Contoh JSON

```json
{
  "email": "abc123@mail.tm",
  "password": "xY3!aBc...",
  "api_key": "12345678-1234-1234-1234-123456789abc",
  "status": "ok",
  "proxy": "http://user:pass@host:port",
  "created_at_wib": "2026-11-11 07:50:00"
}
```

### Status values

- `ok` — akun terdaftar + API key didapat
- `registered+no_key` — akun terdaftar tapi API key gagal diambil
- `error` — gagal (lihat field `error`)
- `unknown` — status tak terdeteksi

---

## License

MIT
