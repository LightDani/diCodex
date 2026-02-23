# ruff: noqa: E501, W505

import argparse
import json
import re
from pathlib import Path

from selenium.webdriver.support.ui import WebDriverWait

from asah_capture import capture_asah_live_attendance_reference
from browser_runtime import DEFAULT_RUNTIME_DIR
from codingcamp_auth import CodingcampAuthOptions, perform_codingcamp_auth
from csv_pipeline import export_tables_to_csv, transform_payload_to_tables
from export_builder import build_export_json
from page_actions import (
    expand_all_student_data,
)
from selenium_ui import wait_for_page_ready

CODINGCAMP_URL = "https://codingcamp.dicoding.com"
ASAH_URL = "https://asah.dicoding.com"
OUTPUT_DIR = Path("output")
MAX_PAGINATION_STEPS = 300
INTERACTION_TIMEOUT_SECONDS = 20
ASYNC_SCRIPT_TIMEOUT_SECONDS = 240
FAST_PAGINATION_DELAY_MS = 120
DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS = 600

try:
    from secret import EMAIL, PASSWORD
except ImportError:
    EMAIL = ""
    PASSWORD = ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export data CodingCamp/ASAH."
    )
    parser.set_defaults(experimental_fast_daily=True)
    parser.add_argument(
        "--source",
        choices=["codingcamp", "asah"],
        default="codingcamp",
        help="Pilih sumber data. 'asah' dipakai untuk capture referensi struktur live.",
    )
    parser.add_argument(
        "--asah-email",
        default=EMAIL,
        help="Email untuk request magic link saat mode --source asah.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Jalankan browser dengan UI (non-headless).",
    )
    parser.add_argument(
        "--auth-mode",
        choices=["hybrid", "auto", "manual"],
        default="hybrid",
        help=(
            "Mode autentikasi CodingCamp: "
            "hybrid (auto jika secret ada, fallback manual), "
            "auto (paksa auto lalu fallback manual), "
            "manual (langsung login manual)."
        ),
    )
    parser.add_argument(
        "--profile-dir",
        default=".selenium_profile/codingcamp",
        help=(
            "Folder Chrome profile persisten untuk menyimpan sesi login "
            "antar-run."
        ),
    )
    parser.add_argument(
        "--manual-login-timeout",
        type=int,
        default=DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS,
        help="Batas tunggu (detik) untuk proses login manual.",
    )
    parser.add_argument(
        "--browser-path",
        default="",
        help="Path browser Chrome/Chromium custom (opsional, advanced).",
    )
    parser.add_argument(
        "--driver-path",
        default="",
        help="Path chromedriver custom (opsional, advanced).",
    )
    parser.add_argument(
        "--runtime-dir",
        default=str(DEFAULT_RUNTIME_DIR),
        help=(
            "Folder cache runtime browser+driver otomatis "
            "(dipakai bila environment belum siap)."
        ),
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Jangan download runtime otomatis dari internet. "
            "Jika browser/driver tidak tersedia, proses akan gagal."
        ),
    )
    parser.add_argument(
        "--load-images",
        action="store_true",
        help="Muat gambar normal. Default: gambar diblokir untuk speed.",
    )
    parser.add_argument(
        "--enable-perf-logs",
        action="store_true",
        help="Aktifkan performance logs Chrome (khusus debug/inspeksi).",
    )
    parser.add_argument(
        "--experimental-fast-daily",
        action="store_true",
        help="Pakai mode daily-checkins super cepat (default aktif).",
    )
    parser.add_argument(
        "--no-fast-daily",
        dest="experimental_fast_daily",
        action="store_false",
        help="Nonaktifkan mode cepat daily-checkins dan pakai mode aman.",
    )
    parser.add_argument(
        "--output-format",
        choices=["csv", "json", "both"],
        default="csv",
        help=(
            "Format output untuk mode codingcamp: "
            "csv (default), json, atau both."
        ),
    )
    return parser.parse_args()


def sanitize_filename_part(text: str) -> str:
    cleaned = re.sub(r"[^\w\-]+", "_", (text or "").strip(), flags=re.ASCII)
    cleaned = cleaned.strip("_")
    return cleaned or "unknown_group"


def write_json_replace(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> None:
    args = parse_args()

    if args.source == "asah":
        out_path = capture_asah_live_attendance_reference(
            args.asah_email,
            asah_url=ASAH_URL,
            output_dir=OUTPUT_DIR,
            browser_path_override=args.browser_path,
            driver_path_override=args.driver_path,
            runtime_dir=Path(args.runtime_dir).expanduser(),
            offline=args.offline,
            enable_perf_logs=args.enable_perf_logs,
            interaction_timeout_seconds=INTERACTION_TIMEOUT_SECONDS,
            script_timeout_seconds=ASYNC_SCRIPT_TIMEOUT_SECONDS,
        )
        print(f"ASAH attendance reference: {out_path}")
        return

    auth_options = CodingcampAuthOptions(
        auth_mode=args.auth_mode,
        headed=args.headed,
        profile_dir=Path(args.profile_dir),
        load_images=args.load_images,
        enable_perf_logs=args.enable_perf_logs,
        browser_path=args.browser_path,
        driver_path=args.driver_path,
        runtime_dir=Path(args.runtime_dir).expanduser(),
        offline=args.offline,
        manual_login_timeout=args.manual_login_timeout,
    )
    driver, login_email_used = perform_codingcamp_auth(
        auth_options,
        codingcamp_url=CODINGCAMP_URL,
        email=EMAIL,
        password=PASSWORD,
        script_timeout_seconds=ASYNC_SCRIPT_TIMEOUT_SECONDS,
    )

    try:
        wait = WebDriverWait(driver, 30)
        wait_for_page_ready(driver, wait)
        print("Autentikasi selesai. Memulai ekstraksi data...")

        expand_all_student_data(
            driver,
            interaction_timeout_seconds=INTERACTION_TIMEOUT_SECONDS,
        )

        payload = build_export_json(
            driver,
            login_email=login_email_used,
            fallback_login_email=EMAIL,
            use_fast_daily=args.experimental_fast_daily,
            use_fast_points=True,
            fast_pagination_delay_ms=FAST_PAGINATION_DELAY_MS,
            max_pagination_steps=MAX_PAGINATION_STEPS,
        )
        group_name = sanitize_filename_part(
            payload["mentor"].get("group", "unknown_group")
        )

        if args.output_format in ("json", "both"):
            json_path = OUTPUT_DIR / f"codingcamp_{group_name}_full.json"
            write_json_replace(json_path, payload)
            print(f"Export JSON: {json_path}")

        if args.output_format in ("csv", "both"):
            tables = transform_payload_to_tables(payload)
            row_count_by_file = export_tables_to_csv(tables, OUTPUT_DIR)
            print("Export CSV:")
            for filename, count in row_count_by_file.items():
                print(f"- {filename}: {count} baris data")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
