from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from browser_runtime import DEFAULT_RUNTIME_DIR, create_bootstrapped_driver
from dom_extractors import normalize_space
from output_utils import write_json_replace
from page_actions import (
    expand_all_student_data,
    send_magic_link_from_asah,
    wait_for_manual_magic_link_login,
)
from student_progress import (
    build_attendance_progress_from_dom,
    ensure_student_progress_structure,
)


def capture_asah_live_attendance_reference(
    asah_email: str,
    *,
    asah_url: str,
    output_dir: Path,
    browser_path_override: str = "",
    driver_path_override: str = "",
    runtime_dir: Path = DEFAULT_RUNTIME_DIR,
    offline: bool = False,
    enable_perf_logs: bool = False,
    interaction_timeout_seconds: int = 20,
    script_timeout_seconds: int = 240,
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
        script_timeout_seconds=script_timeout_seconds,
    )
    wait = WebDriverWait(driver, 30)

    try:
        send_magic_link_from_asah(
            driver,
            wait,
            asah_email,
            asah_url=asah_url,
            interaction_timeout_seconds=interaction_timeout_seconds,
        )
        wait_for_manual_magic_link_login(driver, wait)
        expand_all_student_data(
            driver,
            interaction_timeout_seconds=interaction_timeout_seconds,
        )

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

        out_path = output_dir / "asah_live_attendance_reference.json"
        write_json_replace(out_path, payload)
        return out_path
    finally:
        driver.quit()
