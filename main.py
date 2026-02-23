# ruff: noqa: E501, W505

import argparse
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from browser_runtime import DEFAULT_RUNTIME_DIR, create_bootstrapped_driver
from codingcamp_auth import CodingcampAuthOptions, perform_codingcamp_auth
from csv_pipeline import export_tables_to_csv, transform_payload_to_tables
from export_builder import build_export_json
from dom_extractors import (
    normalize_space,
)
from selenium_ui import click_element, find_first_visible, wait_for_page_ready
from student_progress import (
    build_attendance_progress_from_dom,
    ensure_student_progress_structure,
)

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


def click_from_locators(
    driver: webdriver.Chrome,
    locators: list[tuple[str, str]],
    action_label: str,
) -> None:
    deadline = time.time() + INTERACTION_TIMEOUT_SECONDS
    last_error = None

    while time.time() < deadline:
        for by, value in locators:
            element = find_first_visible(driver, [(by, value)])
            if not element:
                continue
            try:
                click_element(driver, element)
                return
            except Exception as error:
                last_error = error
        time.sleep(0.4)

    message = f"Gagal klik '{action_label}'. Elemen tidak ditemukan atau tidak bisa diklik."
    if last_error:
        raise NoSuchElementException(
            f"{message} Detail: {last_error}"
        ) from last_error
    raise NoSuchElementException(message)


def expand_all_student_data(driver: webdriver.Chrome) -> None:
    text_normalizer = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    text_lower = "abcdefghijklmnopqrstuvwxyz"

    student_input_locators = [
        (
            By.XPATH,
            f"//input[contains(translate(@placeholder, '{text_normalizer}', '{text_lower}'), 'student') "
            f"and contains(translate(@placeholder, '{text_normalizer}', '{text_lower}'), 'id')]",
        ),
        (
            By.XPATH,
            f"//input[contains(translate(@aria-label, '{text_normalizer}', '{text_lower}'), 'student') "
            f"and contains(translate(@aria-label, '{text_normalizer}', '{text_lower}'), 'id')]",
        ),
        (
            By.XPATH,
            f"//div[contains(translate(normalize-space(.), '{text_normalizer}', '{text_lower}'), \"student's name or id\")]",
        ),
    ]
    select_all_locators = [
        (
            By.XPATH,
            f"//button[contains(translate(normalize-space(.), '{text_normalizer}', '{text_lower}'), 'select all')]",
        ),
        (
            By.XPATH,
            f"//label[contains(translate(normalize-space(.), '{text_normalizer}', '{text_lower}'), 'select all')]",
        ),
        (
            By.XPATH,
            f"//span[contains(translate(normalize-space(.), '{text_normalizer}', '{text_lower}'), 'select all')]",
        ),
    ]
    expand_all_locators = [
        (
            By.XPATH,
            f"//button[contains(translate(normalize-space(.), '{text_normalizer}', '{text_lower}'), 'expand all')]",
        ),
        (
            By.XPATH,
            f"//span[contains(translate(normalize-space(.), '{text_normalizer}', '{text_lower}'), 'expand all')]",
        ),
        (
            By.XPATH,
            f"//*[@role='button' and contains(translate(normalize-space(.), '{text_normalizer}', '{text_lower}'), 'expand all')]",
        ),
    ]

    click_from_locators(
        driver, student_input_locators, "Input student's name or ID"
    )
    click_from_locators(driver, select_all_locators, "Select All")
    click_from_locators(driver, expand_all_locators, "Expand All")
    WebDriverWait(driver, INTERACTION_TIMEOUT_SECONDS).until(
        lambda d: (
            d.execute_script(
                "return document.querySelectorAll("
                "'div.container.flex.flex-col.pb-8.border-b'"
                ").length"
            )
            > 0
        )
    )
    time.sleep(0.25)


def send_magic_link_from_asah(
    driver: webdriver.Chrome, wait: WebDriverWait, email: str
) -> None:
    if not email:
        raise ValueError(
            "Email untuk Asah kosong. Isi secret.py atau kirim --asah-email."
        )

    driver.get(f"{ASAH_URL}/login")
    wait_for_page_ready(driver, wait)

    email_input = find_first_visible(
        driver,
        [
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.NAME, "email"),
            (By.ID, "email"),
            (
                By.XPATH,
                "//input[contains(@placeholder, 'Email') or contains(@placeholder, 'email')]",
            ),
        ],
    )
    if not email_input:
        raise NoSuchElementException(
            "Input email tidak ditemukan pada halaman login ASAH."
        )

    email_input.clear()
    email_input.send_keys(email)

    text_normalizer = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    text_lower = "abcdefghijklmnopqrstuvwxyz"
    send_magic_locators = [
        (
            By.XPATH,
            f"//button[contains(translate(normalize-space(.), '{text_normalizer}', '{text_lower}'), 'send magic link to email')]",
        ),
        (
            By.XPATH,
            f"//button[contains(translate(normalize-space(.), '{text_normalizer}', '{text_lower}'), 'send magic link')]",
        ),
        (By.CSS_SELECTOR, "button[type='submit']"),
        (By.CSS_SELECTOR, "input[type='submit']"),
    ]
    click_from_locators(driver, send_magic_locators, "Send Magic Link")


def wait_for_manual_magic_link_login(
    driver: webdriver.Chrome, wait: WebDriverWait
) -> None:
    print(
        "Silakan paste+go magic link di browser Selenium yang terbuka "
        "(tab yang sama), lalu tekan Enter di terminal ini."
    )
    input("Tekan Enter setelah login berhasil... ")
    wait.until(lambda d: "/login" not in d.current_url)
    wait_for_page_ready(driver, wait)
    if "/login" in driver.current_url:
        raise TimeoutException(
            "Masih berada di halaman login setelah langkah manual."
        )


def capture_asah_live_attendance_reference(
    asah_email: str,
    *,
    browser_path_override: str = "",
    driver_path_override: str = "",
    runtime_dir: Path = DEFAULT_RUNTIME_DIR,
    offline: bool = False,
    enable_perf_logs: bool = False,
) -> Path:
    driver = create_bootstrapped_driver(
        headless=False,
        disable_images=True,
        enable_perf_logs=enable_perf_logs,
        user_data_dir=None,
        browser_path_override=browser_path_override,
        driver_path_override=driver_path_override,
        runtime_dir=runtime_dir,
        offline=offline,
        script_timeout_seconds=ASYNC_SCRIPT_TIMEOUT_SECONDS,
    )
    wait = WebDriverWait(driver, 30)

    try:
        send_magic_link_from_asah(driver, wait, asah_email)
        wait_for_manual_magic_link_login(driver, wait)
        expand_all_student_data(driver)

        sections = driver.find_elements(By.CSS_SELECTOR, "section.attendances")
        first_attendance = build_attendance_progress_from_dom(driver, 0)
        first_attendance = ensure_student_progress_structure(
            {"progress": {"attendances": first_attendance}}
        )["progress"]["attendances"]
        first_student_name = driver.execute_script(
            """
            const el = document.querySelector("h3.text-3xl.font-semibold");
            return (el?.textContent || "").trim();
            """
        )

        payload = {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_url": driver.current_url,
            "source": "asah_live",
            "student_total": len(sections),
            "first_student_name": normalize_space(first_student_name),
            "attendance_reference": first_attendance,
        }

        out_path = OUTPUT_DIR / "asah_live_attendance_reference.json"
        write_json_replace(out_path, payload)
        return out_path
    finally:
        driver.quit()


def main() -> None:
    args = parse_args()

    if args.source == "asah":
        out_path = capture_asah_live_attendance_reference(
            args.asah_email,
            browser_path_override=args.browser_path,
            driver_path_override=args.driver_path,
            runtime_dir=Path(args.runtime_dir).expanduser(),
            offline=args.offline,
            enable_perf_logs=args.enable_perf_logs,
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

        expand_all_student_data(driver)

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
