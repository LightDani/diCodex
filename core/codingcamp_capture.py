from __future__ import annotations

from pathlib import Path

from selenium.webdriver.support.ui import WebDriverWait

from .codingcamp_auth import CodingcampAuthOptions, perform_codingcamp_auth
from .csv_pipeline import export_tables_to_csv, transform_payload_to_tables
from .export_builder import build_export_json
from .output_utils import sanitize_filename_part, write_json_replace
from .page_actions import expand_all_student_data
from .selenium_ui import wait_for_page_ready


def run_codingcamp_export(
    args,
    *,
    email: str,
    password: str,
    codingcamp_url: str,
    output_dir: Path,
    pipeline_mode: str = "scrape-transform",
    interaction_timeout_seconds: int = 20,
    async_script_timeout_seconds: int = 240,
    fast_pagination_delay_ms: int = 120,
    max_pagination_steps: int = 300,
) -> None:
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
        codingcamp_url=codingcamp_url,
        email=email,
        password=password,
        script_timeout_seconds=async_script_timeout_seconds,
    )

    try:
        wait = WebDriverWait(driver, 30)
        wait_for_page_ready(driver, wait)
        print("Autentikasi selesai. Memulai ekstraksi data...")

        expand_all_student_data(
            driver,
            interaction_timeout_seconds=interaction_timeout_seconds,
        )

        payload = build_export_json(
            driver,
            login_email=login_email_used,
            fallback_login_email=email,
            use_fast_daily=args.experimental_fast_daily,
            use_fast_points=True,
            fast_pagination_delay_ms=fast_pagination_delay_ms,
            max_pagination_steps=max_pagination_steps,
        )
        group_name = sanitize_filename_part(
            payload["mentor"].get("group", "unknown_group")
        )

        should_write_json = (
            args.output_format in ("json", "both") or pipeline_mode == "scrape"
        )
        if should_write_json:
            json_path = output_dir / f"codingcamp_{group_name}_full.json"
            write_json_replace(json_path, payload)
            print(f"Export JSON: {json_path}")

        if pipeline_mode == "scrape":
            print("Pipeline mode 'scrape': proses transform CSV dilewati.")
            return

        if args.output_format in ("csv", "both"):
            tables = transform_payload_to_tables(payload)
            row_count_by_file = export_tables_to_csv(tables, output_dir)
            print("Export CSV:")
            for filename, count in row_count_by_file.items():
                print(f"- {filename}: {count} baris data")
    finally:
        driver.quit()
