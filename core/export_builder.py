from __future__ import annotations

import time
from datetime import datetime, timezone

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException

from .dom_extractors import (
    extract_mentor_from_dom,
    normalize_space,
    parse_student,
    student_blocks,
)
from .student_progress import (
    build_attendance_progress_from_dom,
    click_all_buttons_by_keyword,
    ensure_student_progress_structure,
    extract_daily_checkins_all_pages,
    extract_daily_checkins_all_students_fast,
    extract_point_histories_all_pages,
    extract_point_histories_all_students_fast,
)


def build_export_json(
    driver: webdriver.Chrome,
    *,
    login_email: str = "",
    fallback_login_email: str = "",
    use_fast_daily: bool = False,
    use_fast_points: bool = True,
    fast_pagination_delay_ms: int = 120,
    max_pagination_steps: int = 300,
) -> dict:
    normalized_login_email = normalize_space(str(login_email or "")).lower()
    mentor = extract_mentor_from_dom(
        driver, normalized_login_email or fallback_login_email
    )
    if normalized_login_email:
        mentor["email"] = normalized_login_email
    else:
        mentor["email"] = normalize_space(str(mentor.get("email", ""))).lower()

    click_all_buttons_by_keyword(driver, "show all courses")
    click_all_buttons_by_keyword(driver, "show all assignments")
    time.sleep(0.2)

    source = driver.page_source
    blocks = student_blocks(source)
    if not blocks:
        raise NoSuchElementException(
            "Tidak ada student block yang bisa diekstrak."
        )

    students = [
        ensure_student_progress_structure(parse_student(block))
        for block in blocks
    ]

    fast_daily_by_student: list[list[dict]] | None = None
    fast_point_by_student: list[dict] | None = None

    if use_fast_daily:
        try:
            fast_daily_by_student = extract_daily_checkins_all_students_fast(
                driver,
                delay_ms=fast_pagination_delay_ms,
            )
        except Exception as error:
            print(
                f"[warn] Fast daily-checkins gagal, fallback mode lama: "
                f"{error}"
            )

    if use_fast_points:
        try:
            fast_point_by_student = extract_point_histories_all_students_fast(
                driver,
                delay_ms=fast_pagination_delay_ms,
            )
        except Exception as error:
            print(
                f"[warn] Fast point-histories gagal, fallback mode lama: "
                f"{error}"
            )

    for idx in range(len(students)):
        students[idx]["progress"]["attendances"] = (
            build_attendance_progress_from_dom(driver, idx)
        )
        if fast_daily_by_student and idx < len(fast_daily_by_student):
            students[idx]["progress"]["daily_checkins"] = {
                "items": fast_daily_by_student[idx]
            }
        else:
            students[idx]["progress"]["daily_checkins"] = {
                "items": extract_daily_checkins_all_pages(
                    driver, idx, max_steps=max_pagination_steps
                )
            }

        if fast_point_by_student and idx < len(fast_point_by_student):
            students[idx]["progress"]["point_histories"] = (
                fast_point_by_student[idx]
            )
        else:
            students[idx]["progress"]["point_histories"] = (
                extract_point_histories_all_pages(
                    driver, idx, max_steps=max_pagination_steps
                )
            )

        students[idx] = ensure_student_progress_structure(students[idx])
        progress = students[idx].get("progress", {})
        if isinstance(progress, dict):
            for attendance_key in ("attendances", "attendance"):
                attendance_section = progress.get(attendance_key)
                if isinstance(attendance_section, dict):
                    attendance_section.pop("fallback_text_if_empty", None)
                    attendance_section.pop("item_schema", None)
                    attendance_section.pop("item_template", None)

            assignments = progress.get("assignments")
            if isinstance(assignments, dict):
                assignments.pop("fallback_text_if_empty", None)

            point_histories = progress.get("point_histories")
            if isinstance(point_histories, dict):
                point_histories.pop("fallback_text_if_empty", None)

    return {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_url": driver.current_url,
            "student_total": len(students),
        },
        "mentor": mentor,
        "students": students,
    }
