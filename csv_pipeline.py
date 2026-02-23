from __future__ import annotations

import csv
import json
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable
from zoneinfo import ZoneInfo

SOURCE_GLOB = "codingcamp_*.json"
SOURCE_NAME_TEMPLATE = "codingcamp_{group}_full.json"
WIB_TZ = ZoneInfo("Asia/Jakarta")

MOOD_MAP = {"bad": 1, "neutral": 2, "good": 3}
ASSIGNMENT_FLAG_MAP = {"Uncompleted": 0, "Completed": 1, "Late": 2}
ATTENDANCE_FLAG_MAP = {"Absent": 0, "Attending": 1, "Late": 2}

ASSIGNMENT_NAMES = [
    (
        "Assignment Soft Skill 1 Personal Productivity: "
        "How to Boost Your Output"
    ),
    (
        "Assignment Soft Skill 2 Growth Mindset and Personal Development: "
        "Establish Your All Star Potentials"
    ),
    (
        "Assignment Soft Skill 3 Flexing Under Pressure: "
        "Mastering Stress Management and Adaptability"
    ),
    (
        "Assignment Soft Skill 4 Communication and Networking: "
        "The Art of Persuasion and Creating Connection"
    ),
    "Assignment Soft Skill 5 Project Management",
    (
        "Assignment Soft Skill 6 Personal Branding: "
        "Be The Best Version of Yourself"
    ),
    (
        "Assignment Soft Skill 7 Interview Preparation: "
        "How to Deal with Recruiter?"
    ),
]
ASSIGNMENT_ID_MAP = {
    name: index for index, name in enumerate(ASSIGNMENT_NAMES, start=1)
}

COURSE_NAMES = [
    "Memulai Dasar Pemrograman untuk Menjadi Pengembang Software",
    "Pengenalan ke Logika Pemrograman (Programming Logic 101)",
    "Belajar Dasar Git dengan GitHub",
    "Belajar Dasar Data Science",
    "Belajar Dasar Visualisasi Data",
    "Memulai Pemrograman dengan Python",
    "Belajar Machine Learning untuk Pemula",
    "Belajar Fundamental Analisis Data",
    "Belajar Fundamental Pemrosesan Data",
    "Belajar Matematika untuk Data Science",
    "Belajar Dasar AI",
    "Belajar Fundamental Deep Learning",
    "Membangun Proyek Deep Learning Tingkat Mahir",
    "Belajar Dasar Cloud dan Gen AI di AWS",
    "Belajar Dasar Pemrograman Web",
    "Belajar Dasar Pemrograman JavaScript",
    "Belajar Membuat Front-End Web untuk Pemula",
    "Belajar Membuat Aplikasi Web dengan React",
    "Belajar Fundamental Aplikasi Web dengan React",
    "Belajar Back-End Pemula dengan JavaScript",
    "Belajar Fundamental Back-End dengan JavaScript",
]
COURSE_ID_MAP = {
    name: index for index, name in enumerate(COURSE_NAMES, start=1)
}

CSV_EXPORT_CONFIG = [
    (
        "mentor_data.csv",
        "mentor_data",
        ["id", "name", "email", "number_of_student"],
    ),
    (
        "student.csv",
        "student",
        [
            "id",
            "name",
            "group",
            "university",
            "major",
            "lecturer",
            "profile_picture",
            "last_update",
        ],
    ),
    (
        "student_daily_checkin.csv",
        "student_daily_checkin",
        ["student_id", "quantitative_mood", "qualitative", "date"],
    ),
    (
        "student_assignment.csv",
        "student_assignment",
        ["student_id", "assignment_id", "assignment_flag"],
    ),
    (
        "student_attendance.csv",
        "student_attendance",
        ["student_id", "activity_name", "flag"],
    ),
    (
        "student_course_progress.csv",
        "student_course_progress",
        ["student_id", "course_id", "quantitative"],
    ),
]


def resolve_default_json_source(output_dir: Path, group: str) -> Path:
    group_name = (group or "").strip()
    if group_name:
        path = output_dir / SOURCE_NAME_TEMPLATE.format(group=group_name)
        if not path.exists():
            raise FileNotFoundError(
                f"File group tidak ditemukan: {path}. "
                "Pastikan nama group benar."
            )
        return path

    candidates = sorted(output_dir.glob(SOURCE_GLOB))
    if len(candidates) == 1:
        return candidates[0]
    if not candidates:
        raise FileNotFoundError(
            f"Tidak ada file '{SOURCE_GLOB}' di direktori: {output_dir}"
        )
    names = ", ".join(path.name for path in candidates[:5])
    if len(candidates) > 5:
        names += ", ..."
    raise ValueError(
        "Ditemukan lebih dari satu file sumber. "
        "Pilih file spesifik dengan --source atau tentukan --group.\n"
        f"Kandidat: {names}"
    )


def load_json_payload(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"File tidak ditemukan: {path}")
    with path.open("r", encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise TypeError(
            "Format JSON tidak valid: root JSON harus object/dict."
        )
    return data


def parse_generated_at_to_wib(generated_at_utc: str) -> str:
    if not generated_at_utc:
        return ""
    value = (generated_at_utc or "").replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return ""
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    try:
        return parsed.astimezone(WIB_TZ).strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        fallback_wib = timezone(timedelta(hours=7))
        return parsed.astimezone(fallback_wib).strftime("%Y-%m-%d %H:%M:%S")


def parse_checkin_date(value: str) -> str:
    if not value:
        return ""
    try:
        return datetime.strptime(value, "%a, %b %d, %Y").date().isoformat()
    except ValueError:
        return ""


def extract_student_id(profile_link: str) -> str:
    cleaned = (profile_link or "").strip()
    if not cleaned:
        return ""
    match = re.search(r"/u/([^/?#]+)", cleaned)
    if match:
        return match.group(1).strip()
    return cleaned.rstrip("/").split("/")[-1].split("?")[0].strip()


def parse_progress_percent(raw_value: str) -> int | None:
    match = re.search(r"\d+", raw_value or "")
    if not match:
        return None
    return int(match.group(0))


def write_csv(
    path: Path,
    fieldnames: list[str],
    rows: Iterable[dict[str, Any]],
) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    row_count = 0
    with path.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {field: row.get(field, "") for field in fieldnames}
            )
            row_count += 1
    return row_count


def transform_payload_to_tables(
    payload: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    mentor = payload.get("mentor", {})
    metadata = payload.get("metadata", {})
    students = payload.get("students", [])
    group = str(mentor.get("group", ""))
    last_update = parse_generated_at_to_wib(
        str(metadata.get("generated_at_utc", ""))
    )

    mentor_rows = [
        {
            "id": group,
            "name": mentor.get("name", ""),
            "email": mentor.get("email", ""),
            "number_of_student": metadata.get("student_total", 0),
        }
    ]

    student_rows: list[dict[str, Any]] = []
    student_daily_checkin_rows: list[dict[str, Any]] = []
    student_assignment_rows: list[dict[str, Any]] = []
    student_attendance_rows: list[dict[str, Any]] = []
    student_course_progress_rows: list[dict[str, Any]] = []

    for student in students:
        profile = student.get("profile", {})
        progress = student.get("progress", {})
        student_id = extract_student_id(str(profile.get("profile_link", "")))

        student_rows.append(
            {
                "id": student_id,
                "name": profile.get("name", ""),
                "group": group,
                "university": profile.get("university", ""),
                "major": profile.get("major", ""),
                "lecturer": profile.get("lecturer", ""),
                "profile_picture": profile.get("photo_url", ""),
                "last_update": last_update,
            }
        )

        for checkin in progress.get("daily_checkins", {}).get("items", []):
            student_daily_checkin_rows.append(
                {
                    "student_id": student_id,
                    "quantitative_mood": MOOD_MAP.get(checkin.get("mood")),
                    "qualitative": checkin.get("reflection", ""),
                    "date": parse_checkin_date(checkin.get("date", "")),
                }
            )

        for assignment in progress.get("assignments", {}).get("items", []):
            student_assignment_rows.append(
                {
                    "student_id": student_id,
                    "assignment_id": ASSIGNMENT_ID_MAP.get(
                        assignment.get("assignment", "")
                    ),
                    "assignment_flag": ASSIGNMENT_FLAG_MAP.get(
                        assignment.get("status", "")
                    ),
                }
            )

        for attendance in progress.get("attendances", {}).get("items", []):
            student_attendance_rows.append(
                {
                    "student_id": student_id,
                    "activity_name": attendance.get("event", ""),
                    "flag": ATTENDANCE_FLAG_MAP.get(
                        attendance.get("status", "")
                    ),
                }
            )

        for course in progress.get("course_progress", {}).get("items", []):
            student_course_progress_rows.append(
                {
                    "student_id": student_id,
                    "course_id": COURSE_ID_MAP.get(course.get("course", "")),
                    "quantitative": parse_progress_percent(
                        course.get("progress_percent", "")
                    ),
                }
            )

    return {
        "mentor_data": mentor_rows,
        "student": student_rows,
        "student_daily_checkin": student_daily_checkin_rows,
        "student_assignment": student_assignment_rows,
        "student_attendance": student_attendance_rows,
        "student_course_progress": student_course_progress_rows,
    }


def export_tables_to_csv(
    tables: dict[str, list[dict[str, Any]]], output_dir: Path
) -> dict[str, int]:
    row_count_by_file: dict[str, int] = {}
    for filename, table_name, fields in CSV_EXPORT_CONFIG:
        row_count_by_file[filename] = write_csv(
            output_dir / filename, fields, tables[table_name]
        )
    return row_count_by_file
