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
3. Menjalankan pipeline `scrape-transform`.
4. Menyimpan hasil CSV ke folder `output/`.

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

### Pipeline Mode
- `--pipeline-mode {scrape-transform,scrape,transform}`
- Default: `scrape-transform`
- Catatan: mode `transform` hanya valid untuk `--source codingcamp`.

Perilaku:
- `scrape-transform`: scrape live lalu transform ke CSV.
- `scrape`: scrape live saja (JSON).
- `transform`: transform JSON existing ke CSV tanpa Selenium login.

Catatan output:
- Pada `scrape-transform`, file CSV selalu dihasilkan.
- Jika `--output-format json` atau `both` dipakai saat `scrape-transform`,
  file JSON juga akan disimpan sebagai artefak tambahan.
- Pada `scrape`, output efektif selalu JSON.

Contoh:
```bash
uv run python main.py --pipeline-mode scrape-transform
uv run python main.py --pipeline-mode scrape --output-format json
uv run python main.py --pipeline-mode transform --transform-group CDC-04
```

Opsi khusus mode `transform`:
- `--transform-source <path_json>`
- `--transform-group <id_group>`

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
- `--log-level {DEBUG,INFO,WARNING,ERROR}` (default: `INFO`).

Contoh:
```bash
uv run python main.py --browser-path "C:\\Chrome\\chrome.exe" --driver-path "C:\\Driver\\chromedriver.exe"
uv run python main.py --offline
uv run python main.py --log-level DEBUG
```

### Format Output
- `--output-format {csv,json,both}` (default: `csv`)
- Pada `scrape-transform`, CSV selalu dihasilkan.
- `json`/`both` menambah file JSON hasil scrape.
- Pada `scrape`, output efektif selalu JSON.

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

## Struktur Project
Entry point tetap sederhana:
- `main.py`: launcher utama
- `etl.py`: transform JSON existing ke CSV

Modul internal sudah dipindah ke package `core/` agar lebih rapih, meliputi:
- auth/login flow
- browser/runtime bootstrap
- extractor DOM dan progress
- builder export JSON/CSV
- settings, UI actions, dan util output

## ETL Offline
Untuk transform JSON existing tanpa scraping ulang:

```bash
uv run python etl.py --group CDC-04
```

## Quality Checks
### Validasi Schema CSV Output
Validasi apakah file CSV output ada dan header kolomnya sesuai contract:

```bash
uv run python quality_checks.py
```

### Smoke Test Otomatis
Menjalankan `main.py --output-format csv` lalu validasi schema CSV:

```bash
uv run python smoke_test.py
```

Opsi penting:
- `--skip-run`: hanya validasi output yang sudah ada.
- `--run-mode {inprocess,subprocess}` (default: `inprocess`).

Untuk pakai argumen login/runtime yang sama seperti `main.py`, langsung
tambahkan di belakang command:

```bash
uv run python smoke_test.py --auth-mode hybrid --headed
uv run python smoke_test.py --run-mode subprocess --auth-mode hybrid
```

## Catatan
- First run bisa lebih lama karena bootstrap runtime.
- Sesi login tidak di-reuse antar-run; autentikasi dimulai dari sesi baru.
- Saat login manual dibutuhkan, browser otomatis berjalan dalam mode UI
  (headed).
- Folder lokal runtime di-ignore git:
  `output/`, `chromedriver/`, `.selenium_profile/`, `.runtime/`,
  `archive_unused/`.
