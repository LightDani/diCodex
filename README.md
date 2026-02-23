# CodingCamp Data Extractor

Script Selenium untuk login ke `codingcamp.dicoding.com`, membuka semua data
siswa, lalu mengekstrak data mentor + detail semua siswa ke CSV (default).

## Quick Start
Perintah paling simpel:

```bash
uv run python main.py
```

Pada mode default, script akan:
1. Menyiapkan browser/driver otomatis.
2. Login dengan mode `hybrid`.
3. Mengekstrak data dan menyimpan CSV ke folder `output/`.

## Kenapa Bisa "Zero Config"
Saat startup, script mencoba strategi ini berurutan:
1. Browser + driver yang sudah ada di sistem/proyek.
2. Selenium Manager.
3. Download Chrome for Testing + chromedriver ke cache lokal (`.runtime/`).

Jadi user biasa cukup jalankan satu command, sementara user advanced tetap bisa
override path browser/driver secara manual.

## Prasyarat
- Python `>= 3.12`
- Internet pada first run jika browser/driver belum tersedia.
- (Opsional) `secret.py` untuk auto login:

```python
EMAIL = "email_kamu@example.com"
PASSWORD = "password_kamu"
```

## Instalasi Dependency
### Opsi UV
```bash
uv sync
```

### Opsi PIP
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Untuk Windows (PowerShell):
```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

## Menjalankan Script
### Default
```bash
uv run python main.py
```

### Mode Login
- `--auth-mode {hybrid,auto,manual}` (default: `hybrid`)
- `--profile-dir <path>` (default: `.selenium_profile/codingcamp`)
- `--manual-login-timeout <seconds>` (default: `600`)

Contoh:
```bash
uv run python main.py --auth-mode manual --headed
uv run python main.py --auth-mode auto
```

### Opsi Runtime (Advanced)
- `--browser-path <path>`: pakai binary browser tertentu.
- `--driver-path <path>`: pakai chromedriver tertentu.
- `--runtime-dir <path>`: lokasi cache runtime otomatis
  (default: `.runtime/browser`).
- `--offline`: nonaktifkan download runtime otomatis.

Contoh:
```bash
uv run python main.py --browser-path "C:\\Chrome\\chrome.exe" --driver-path "C:\\Driver\\chromedriver.exe"
uv run python main.py --offline
```

### Format Output
- `--output-format {csv,json,both}` (default: `csv`)

Contoh:
```bash
uv run python main.py --output-format csv
uv run python main.py --output-format json
uv run python main.py --output-format both
```

## Output
Semua hasil disimpan di `output/`.

- Default (CSV):
  - `output/mentor_data.csv`
  - `output/student.csv`
  - `output/student_daily_checkin.csv`
  - `output/student_assignment.csv`
  - `output/student_attendance.csv`
  - `output/student_course_progress.csv`
- Jika `--output-format json` atau `both`:
  - `output/codingcamp_<nama_group>_full.json`
- ASAH reference: `output/asah_live_attendance_reference.json`

File output bersifat statis per group dan akan di-replace jika sudah ada.

## ETL Offline
Untuk transform JSON existing tanpa scraping ulang:

```bash
uv run python etl.py --group CDC-04
```

## Catatan
- First run bisa lebih lama karena bootstrap runtime.
- Saat login manual dibutuhkan, browser otomatis berjalan dalam mode UI
  (headed).
- Folder lokal runtime di-ignore git:
  `output/`, `chromedriver/`, `.selenium_profile/`, `.runtime/`,
  `archive_unused/`.
