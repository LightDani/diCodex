from __future__ import annotations

import time
from datetime import datetime, timezone
from logging import Logger

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
from .logging_utils import get_logger

LOGGER: Logger = get_logger(__name__)


def extract_session_email(driver: webdriver.Chrome) -> str:
    value = driver.execute_script(
        r"""
        const normalize = (value) =>
          (value || "").replace(/\s+/g, " ").trim().toLowerCase();
        const emailRegex = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;

        const parseMaybeJson = (rawValue) => {
          if (!rawValue) {
            return null;
          }
          try {
            return JSON.parse(rawValue);
          } catch (_error) {
            return null;
          }
        };

        const extractFromParsed = (parsed) => {
          if (!parsed) {
            return "";
          }
          if (typeof parsed === "string") {
            const nested = parseMaybeJson(parsed);
            if (nested && nested !== parsed) {
              return extractFromParsed(nested);
            }
            const matched = parsed.match(emailRegex);
            return matched?.[0] || "";
          }
          if (
            typeof parsed.email === "string" &&
            normalize(parsed.email)
          ) {
            return parsed.email;
          }
          const asText = JSON.stringify(parsed);
          const matched = asText.match(emailRegex);
          return matched?.[0] || "";
        };

        const readFromStorage = (storage) => {
          if (!storage) {
            return "";
          }
          for (let i = 0; i < storage.length; i += 1) {
            const key = storage.key(i) || "";
            if (!/firebase:authuser/i.test(key)) {
              continue;
            }
            const raw = storage.getItem(key) || "";
            const fromParsed = extractFromParsed(parseMaybeJson(raw));
            if (normalize(fromParsed)) {
              return fromParsed;
            }
            const fromRaw = raw.match(emailRegex)?.[0] || "";
            if (normalize(fromRaw)) {
              return fromRaw;
            }
          }
          return "";
        };

        return readFromStorage(window.localStorage) ||
          readFromStorage(window.sessionStorage);
        """
    )
    return normalize_space(str(value or "")).lower()


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
    normalized_fallback_email = normalize_space(
        str(fallback_login_email or "")
    ).lower()
    session_email = extract_session_email(driver)
    effective_email = (
        normalized_login_email or session_email or normalized_fallback_email
    )

    mentor = extract_mentor_from_dom(driver, effective_email)
    if effective_email:
        mentor["email"] = effective_email
    else:
        LOGGER.warning(
            "mentor_email.fallback_to_dom reason=no_login_or_session_email"
        )
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
            LOGGER.warning(
                "fast_daily.failed fallback=legacy error=%s",
                error,
            )

    if use_fast_points:
        try:
            fast_point_by_student = extract_point_histories_all_students_fast(
                driver,
                delay_ms=fast_pagination_delay_ms,
            )
        except Exception as error:
            LOGGER.warning(
                "fast_points.failed fallback=legacy error=%s",
                error,
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
