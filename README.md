# CodingCamp Data Extractor

Automasi Selenium untuk login ke `codingcamp.dicoding.com`, membuka semua data siswa, lalu mengekstrak data mentor + seluruh detail siswa ke JSON.

## Fitur Utama
- Login CodingCamp dengan mode fleksibel:
  - `hybrid` (default): auto jika `secret.py` tersedia, fallback ke manual
  - `auto`: paksa auto, jika gagal fallback ke manual
  - `manual`: langsung login manual
- Sesi login persisten dengan Chrome profile (`--profile-dir`) agar run berikutnya lebih cepat.
- Aksi otomatis:
  - klik `Input student's name or ID`
  - klik `Select All`
  - klik `Expand All`
- Ekstraksi data:
  - data mentor
  - semua siswa
  - profil siswa
  - attendance
  - course progress
  - assignment
  - daily checkins (full pagination)
  - point histories (full pagination)

## Prerequisites
- Python `>= 3.12`
- Google Chrome / Chromium terpasang
- ChromeDriver kompatibel dengan versi browser
  - download: `https://googlechromelabs.github.io/chrome-for-testing/`
  - letakkan di salah satu path:
    - `chromedriver/linux/chromedriver`
    - `chromedriver/windows/chromedriver.exe`
- (Opsional) `secret.py` untuk auto login

Contoh `secret.py`:

```python
EMAIL = "email_kamu@example.com"
PASSWORD = "password_kamu"
```

## Output
Semua hasil disimpan di folder `output/`.

- CodingCamp: `output/codingcamp_<nama_group>_full.json`
- ASAH reference: `output/asah_live_attendance_reference.json`

Nama file bersifat statis per group dan akan di-replace jika file sudah ada.

## Mode Login

Argumen auth baru:
- `--auth-mode {hybrid,auto,manual}` (default: `hybrid`)
- `--profile-dir <path>` (default: `.selenium_profile/codingcamp`)
- `--manual-login-timeout <seconds>` (default: `300`)

Catatan:
- Saat butuh login manual, browser akan otomatis headed (muncul UI).
- Jika sesi pada profile masih valid, script bisa langsung lanjut tanpa login ulang.

## Cara Menjalankan (UV)
1. Install dependency:
```bash
uv sync
```
2. Jalankan script (default hybrid):
```bash
uv run python main.py --auth-mode hybrid
```
3. Contoh mode lain:
```bash
uv run python main.py --auth-mode manual --headed
uv run python main.py --auth-mode auto
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
3. Jalankan script:
```bash
python main.py --auth-mode hybrid
```

## Catatan Penting
- `output/`, `chromedriver/`, `archive_unused/`, dan `.selenium_profile/` di-ignore git.
- Jika UI website berubah, selector klik/ekstraksi mungkin perlu penyesuaian.
