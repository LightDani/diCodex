from __future__ import annotations

import base64
import json
import re
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
    extract_attendances_all_students_fast,
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


def decode_jwt_payload(token: str) -> dict:
    parts = (token or "").split(".")
    if len(parts) < 2:
        return {}
    payload = parts[1]
    padding = "=" * (-len(payload) % 4)
    try:
        raw = base64.urlsafe_b64decode((payload + padding).encode("utf-8"))
        parsed = json.loads(raw.decode("utf-8"))
        return parsed if isinstance(parsed, dict) else {}
    except Exception:
        return {}


def extract_cookie_email(driver: webdriver.Chrome) -> str:
    email_pattern = r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}"
    for cookie in driver.get_cookies():
        raw_value = str(cookie.get("value", "") or "")
        direct_match = re.search(email_pattern, raw_value, flags=re.I)
        if direct_match:
            return normalize_space(direct_match.group(0)).lower()

        decoded = decode_jwt_payload(raw_value)
        for key in ("email", "user_email", "upn"):
            value = normalize_space(str(decoded.get(key, ""))).lower()
            if value and "@" in value:
                return value
    return ""


def extract_indexeddb_email(driver: webdriver.Chrome) -> str:
    try:
        value = driver.execute_async_script(
            r"""
            const done = arguments[arguments.length - 1];
            const normalize = (value) =>
              (value || "").replace(/\s+/g, " ").trim().toLowerCase();
            const emailRegex = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/i;
            const databasesApi = indexedDB?.databases?.bind(indexedDB);

            const extractEmail = (rawValue) => {
              if (!rawValue) {
                return "";
              }
              if (typeof rawValue === "string") {
                const matched = rawValue.match(emailRegex);
                return matched?.[0] || "";
              }
              if (
                typeof rawValue.email === "string" &&
                normalize(rawValue.email)
              ) {
                return rawValue.email;
              }
              const asText = JSON.stringify(rawValue);
              const matched = asText.match(emailRegex);
              return matched?.[0] || "";
            };

            const readStoreValues = (db, storeName) =>
              new Promise((resolve) => {
                try {
                  const tx = db.transaction(storeName, "readonly");
                  const store = tx.objectStore(storeName);
                  const req = store.getAll();
                  req.onsuccess = () => resolve(req.result || []);
                  req.onerror = () => resolve([]);
                } catch (_error) {
                  resolve([]);
                }
              });

            const openDb = (name) =>
              new Promise((resolve) => {
                try {
                  const req = indexedDB.open(name);
                  req.onsuccess = () => resolve(req.result || null);
                  req.onerror = () => resolve(null);
                } catch (_error) {
                  resolve(null);
                }
              });

            (async () => {
              const dbNames = ["firebaseLocalStorageDb"];
              if (databasesApi) {
                try {
                  const listed = await databasesApi();
                  for (const item of listed || []) {
                    const name = item?.name || "";
                    if (name && !dbNames.includes(name)) {
                      dbNames.push(name);
                    }
                  }
                } catch (_error) {}
              }

              for (const dbName of dbNames) {
                const db = await openDb(dbName);
                if (!db) {
                  continue;
                }
                try {
                  const stores = Array.from(db.objectStoreNames || []);
                  for (const storeName of stores) {
                    const rows = await readStoreValues(db, storeName);
                    for (const row of rows) {
                      const email =
                        extractEmail(row) ||
                        extractEmail(row?.value) ||
                        extractEmail(row?.fbase_key) ||
                        extractEmail(row?.rawUserInfo);
                      if (normalize(email)) {
                        db.close();
                        done(email);
                        return;
                      }
                    }
                  }
                } finally {
                  db.close();
                }
              }
              done("");
            })().catch(() => done(""));
            """
        )
        return normalize_space(str(value or "")).lower()
    except Exception:
        return ""


def is_email_present_in_live_source(
    driver: webdriver.Chrome, candidate_email: str
) -> bool:
    target = normalize_space(str(candidate_email or "")).lower()
    if not target:
        return False

    try:
        if target in (driver.page_source or "").lower():
            return True
    except Exception:
        pass

    try:
        found = driver.execute_script(
            r"""
            const target = (arguments[0] || "").trim().toLowerCase();
            if (!target) {
              return false;
            }

            const contains = (value) =>
              (value || "").toLowerCase().includes(target);

            const inStorage = (storage) => {
              if (!storage) {
                return false;
              }
              for (let i = 0; i < storage.length; i += 1) {
                const key = storage.key(i) || "";
                const raw = storage.getItem(key) || "";
                if (contains(key) || contains(raw)) {
                  return true;
                }
              }
              return false;
            };

            return inStorage(window.localStorage) ||
              inStorage(window.sessionStorage);
            """,
            target,
        )
        return bool(found)
    except Exception:
        found = False

    if found:
        return True

    lower_target = target.lower()
    for cookie in driver.get_cookies():
        raw_value = str(cookie.get("value", "") or "").lower()
        if lower_target in raw_value:
            return True
        decoded = decode_jwt_payload(str(cookie.get("value", "") or ""))
        decoded_email = normalize_space(str(decoded.get("email", ""))).lower()
        if decoded_email == lower_target:
            return True
    if extract_indexeddb_email(driver) == lower_target:
        return True
    return False


def build_export_json(
    driver: webdriver.Chrome,
    *,
    login_email: str = "",
    expected_login_email: str = "",
    fallback_login_email: str = "",
    use_fast_daily: bool = False,
    use_fast_points: bool = True,
    fast_pagination_delay_ms: int = 120,
    max_pagination_steps: int = 300,
) -> dict:
    normalized_login_email = normalize_space(str(login_email or "")).lower()
    normalized_expected_email = normalize_space(
        str(expected_login_email or "")
    ).lower()
    normalized_fallback_email = normalize_space(
        str(fallback_login_email or "")
    ).lower()
    session_email = (
        extract_session_email(driver)
        or extract_cookie_email(driver)
        or extract_indexeddb_email(driver)
    )
    verified_expected_email = (
        normalized_expected_email
        if is_email_present_in_live_source(driver, normalized_expected_email)
        else ""
    )
    effective_email = (
        normalized_login_email
        or session_email
        or verified_expected_email
        or normalized_fallback_email
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
    click_all_buttons_by_keyword(driver, "show all attend")
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

    fast_attendance_by_student: list[dict] | None = None
    fast_daily_by_student: list[list[dict]] | None = None
    fast_point_by_student: list[dict] | None = None

    try:
        candidate_attendance = extract_attendances_all_students_fast(driver)
        is_valid_attendance_payload = (
            isinstance(candidate_attendance, list)
            and len(candidate_attendance) == len(students)
            and all(
                isinstance(section, dict)
                for section in candidate_attendance
            )
            and all(
                isinstance(section.get("items", []), list)
                for section in candidate_attendance
            )
        )
        if is_valid_attendance_payload:
            fast_attendance_by_student = candidate_attendance
        else:
            LOGGER.warning(
                "fast_attendance.invalid_payload fallback=legacy "
                "student_total=%s attendance_total=%s",
                len(students),
                (
                    len(candidate_attendance)
                    if isinstance(candidate_attendance, list)
                    else "invalid"
                ),
            )
    except Exception as error:
        LOGGER.warning(
            "fast_attendance.failed fallback=legacy error=%s",
            error,
        )

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
        if (
            fast_attendance_by_student
            and idx < len(fast_attendance_by_student)
        ):
            students[idx]["progress"]["attendances"] = (
                fast_attendance_by_student[idx]
            )
        else:
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
