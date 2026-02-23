# CodingCamp Data Extractor

Automasi Selenium untuk login ke `codingcamp.dicoding.com`, membuka semua data siswa, lalu mengekstrak data mentor + seluruh detail siswa ke JSON.

## TL;DR
Jalankan saja:

```bash
uv run python main.py
```

Script akan mencoba menyiapkan browser/driver otomatis (termasuk fallback download runtime jika perlu).

## Fitur Utama
- Login mode fleksibel:
  - `hybrid` (default): auto jika `secret.py` ada, fallback manual.
  - `auto`: paksa auto, jika gagal fallback manual.
  - `manual`: langsung tunggu login manual.
- Session persisten via `--profile-dir` agar run berikutnya lebih cepat.
- Bootstrap runtime otomatis:
  - deteksi browser/driver yang sudah ada
  - fallback Selenium Manager
  - fallback Chrome for Testing (download ke cache lokal)
- Ekstraksi lengkap:
  - mentor
  - profile siswa
  - attendance
  - course progress
  - assignment
  - daily checkins (full)
  - point histories (full)

## Prerequisites
- Python `>= 3.12`
- Internet pada first run jika browser/driver belum tersedia (untuk auto-bootstrap).
- (Opsional) `secret.py` untuk auto login:

```python
EMAIL = "email_kamu@example.com"
PASSWORD = "password_kamu"
```

## Output
Semua hasil disimpan di folder `output/`.

- CodingCamp: `output/codingcamp_<nama_group>_full.json`
- ASAH reference: `output/asah_live_attendance_reference.json`

File output statis per group dan akan di-replace jika sudah ada.

## Cara Menjalankan (UV)
1. Install dependency:
```bash
uv sync
```
2. Jalankan default:
```bash
uv run python main.py
```

## Cara Menjalankan (PIP)
1. (Opsional) buat virtualenv:
```bash
python -m venv .venv
source .venv/bin/activate
```
2. Install dependency:
```bash
pip install -r requirements.txt
```
3. Jalankan:
```bash
python main.py
```

## Opsi Login
- `--auth-mode {hybrid,auto,manual}` (default: `hybrid`)
- `--profile-dir <path>` (default: `.selenium_profile/codingcamp`)
- `--manual-login-timeout <seconds>` (default: `300`)

## Opsi Runtime (Advanced)
- `--browser-path <path>`: pakai browser binary tertentu.
- `--driver-path <path>`: pakai chromedriver tertentu.
- `--runtime-dir <path>`: lokasi cache runtime otomatis (default: `.runtime/browser`).
- `--offline`: nonaktifkan download runtime otomatis.

Contoh:

```bash
uv run python main.py --auth-mode manual --headed
uv run python main.py --browser-path "C:\\Chrome\\chrome.exe" --driver-path "C:\\Driver\\chromedriver.exe"
uv run python main.py --offline
```

## Catatan Penting
- First run bisa lebih lama jika perlu bootstrap runtime.
- Jika mode manual dibutuhkan, browser akan muncul (headed).
- Folder `output/`, `chromedriver/`, `.selenium_profile/`, `.runtime/`, dan `archive_unused/` di-ignore git.
