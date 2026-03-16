# ruff: noqa: E501

from __future__ import annotations

import html
import re
from typing import Any

from selenium import webdriver

from .student_progress import build_attendance_item


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


def one(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.S)
    if not match:
        return ""
    return normalize_space(html.unescape(match.group(1)))


def many(pattern: str, text: str) -> list[tuple[str, ...]]:
    rows: list[tuple[str, ...]] = []
    for match in re.findall(pattern, text, flags=re.S):
        if isinstance(match, str):
            rows.append((normalize_space(html.unescape(match)),))
        else:
            rows.append(
                tuple(normalize_space(html.unescape(item)) for item in match)
            )
    return rows


def html_fragment_to_text(fragment: str) -> str:
    no_tags = re.sub(r"<[^>]+>", " ", fragment or "", flags=re.S)
    return normalize_space(html.unescape(no_tags))


def labeled_value(block_html: str, label: str) -> str:
    escaped_label = re.escape(label)
    patterns = [
        (
            rf"<p[^>]*>\s*{escaped_label}\s*</p>\s*</div>\s*"
            r'<p[^>]*class="[^"]*pl-4[^"]*"[^>]*>(.*?)</p>'
        ),
        (
            rf"<p[^>]*>\s*{escaped_label}\s*</p>\s*</div>\s*"
            r'<ul[^>]*class="[^"]*pl-4[^"]*"[^>]*>\s*'
            r"<li[^>]*>(.*?)</li>"
        ),
        (
            rf"<p[^>]*>\s*{escaped_label}\s*</p>.*?"
            r"<p[^>]*>(.*?)</p>"
        ),
    ]
    for pattern in patterns:
        match = re.search(pattern, block_html, flags=re.S)
        if not match:
            continue
        return html_fragment_to_text(match.group(1))
    return ""


def student_blocks(page_html: str) -> list[str]:
    marker = '<div class="container flex flex-col pb-8 border-b">'
    parts = page_html.split(marker)[1:]
    blocks: list[str] = []
    for idx, part in enumerate(parts):
        if idx < len(parts) - 1:
            part = part.split(marker)[0]
        blocks.append(part)
    return blocks


def parse_student(block_html: str) -> dict:
    profile = {
        "name": one(
            r'<h3 class="text-3xl font-semibold">([^<]+)</h3>', block_html
        ),
        "profile_link": one(r'<h1><a href="([^"]+)"', block_html),
        "photo_url": one(
            r'<img alt="[^"]+" src="([^"]+firebasestorage[^"]+)"', block_html
        ),
        "status_badge": one(
            r'<div class="inline-block text-xs font-medium[^>]*><p>([^<]+)</p></div>',
            block_html,
        ),
        "university": labeled_value(block_html, "University"),
        "major": labeled_value(block_html, "Major"),
        "facilitator": labeled_value(block_html, "Facilitator"),
        "lecturer": labeled_value(block_html, "Lecturer"),
    }

    attendance_section = one(
        r'<section class="attendances w-full">(.*?)</section>', block_html
    )
    attendances = [
        build_attendance_item(event, status)
        for event, status in many(
            r'data-event-name="([^"]+)".*?data-element="item-status-label">([^<]+)<',
            attendance_section,
        )
    ]
    attendance_last_updated = one(
        r'data-element="attendance-last-update">Last updated: ([^<]+)<',
        attendance_section,
    )
    attendance_fallback = one(
        r'data-element="attendance-none">\s*([^<]+)\s*<', attendance_section
    )

    course_section = one(
        r'(data-element="course-progress-title".*?</div></div></div></section>)',
        block_html,
    )
    courses = [
        {
            "course": course,
            "progress_percent": percent,
            "status": status,
        }
        for course, percent, status in many(
            r'data-course="([^"]+)".*?<span[^>]*class="mr-2">([^<]+)</span><span[^>]*data-element="item-status-label">([^<]+)</span>',
            course_section,
        )
    ]
    course_last_updated = one(
        r'data-element="course-progress-last-update">Last updated: ([^<]+)<',
        course_section,
    )

    assignment_section = one(
        r'<section class="assignments w-full">(.*?)</section>', block_html
    )
    assignments = [
        {"assignment": name, "status": status}
        for name, status in many(
            r'data-assign-name="([^"]+)".*?data-element="item-status-label">([^<]+)<',
            assignment_section,
        )
    ]
    assignment_last_updated = one(
        r'data-element="assignment-last-update">Last updated: ([^<]+)<',
        assignment_section,
    )
    assignment_fallback = one(
        r'data-element="assignment-none">\s*([^<]+)\s*<', assignment_section
    )

    daily_section = one(
        r'<section class="daily-checkins w-full">(.*?)</section>', block_html
    )
    daily_checkins = [
        {
            "mood": mood,
            "date": date,
            "reflection": reflection,
        }
        for mood, date, reflection in many(
            r'alt="([A-Za-z]+) mood".*?<p class="text-sm text-gray-500">([^<]+)</p>.*?<p class="text-sm text-gray-700">([^<]*)</p>',
            daily_section,
        )
    ]

    return {
        "profile": profile,
        "progress": {
            "attendances": {
                "last_updated": attendance_last_updated,
                "items": attendances,
                "fallback_text_if_empty": attendance_fallback,
                "item_schema": {
                    "event": "string",
                    "status": "string",
                },
            },
            "course_progress": {
                "last_updated": course_last_updated,
                "items": courses,
            },
            "assignments": {
                "last_updated": assignment_last_updated,
                "items": assignments,
                "fallback_text_if_empty": assignment_fallback,
            },
            "daily_checkins": {
                "items": daily_checkins,
            },
        },
    }


def extract_students_from_dom(driver: webdriver.Chrome) -> list[dict]:
    payload = driver.execute_script(
        r"""
        const text = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();

        const readLabeledValue = (card, label) => {
          const target = (label || "").trim().toLowerCase();
          if (!target) {
            return "";
          }

          const labelNode = Array.from(card.querySelectorAll("p,span,label,dt,th"))
            .find((el) => text(el).toLowerCase() === target);
          if (!labelNode) {
            return "";
          }

          const labelContainer = labelNode.closest("div,li,section,article,tr,td,dl");
          const directValue = text(
            labelContainer?.parentElement?.querySelector("p.pl-4, ul.pl-4")
          );
          if (directValue && directValue.toLowerCase() !== target) {
            return directValue;
          }

          const nextSiblingValue = text(labelContainer?.nextElementSibling);
          if (nextSiblingValue && nextSiblingValue.toLowerCase() !== target) {
            return nextSiblingValue;
          }

          const container = labelContainer?.parentElement || labelNode.parentElement;
          if (!container) {
            return "";
          }

          const candidate = Array.from(
            container.querySelectorAll("p,li,span,div,a")
          )
            .map((el) => text(el))
            .find((value) => value && value.toLowerCase() !== target);
          return candidate || "";
        };

        const cards = Array.from(
          document.querySelectorAll("div.container.flex.flex-col.pb-8.border-b")
        );

        return cards.map((card) => {
          const profileLink = card.querySelector("h1 a[href], h3 a[href], a[href*='/u/']");
          const photo = card.querySelector("img[src], img[alt]");
          const statusBadge = card.querySelector("div.inline-block.text-xs.font-medium");

          const courseSection = card.querySelector("section.course-progress") || card;
          const courseItems = Array.from(card.querySelectorAll("[data-course]")).map((row) => ({
            course: (row.getAttribute("data-course") || "").trim(),
            progress_percent: text(
              row.querySelector("span.mr-2, [data-element='item-progress-label']")
            ),
            status: text(row.querySelector("[data-element='item-status-label']")),
          }));

          const assignmentSection = card.querySelector("section.assignments") || card;
          const assignmentItems = Array.from(
            assignmentSection.querySelectorAll("[data-assign-name]")
          ).map((row) => ({
            assignment: (row.getAttribute("data-assign-name") || "").trim(),
            status: text(row.querySelector("[data-element='item-status-label']")),
          }));

          const attendanceSection =
            card.querySelector("section.attendances") ||
            card.querySelector("section.attendance") ||
            card;
          const attendanceItems = Array.from(
            attendanceSection.querySelectorAll("[data-event-name]")
          ).map((row) => ({
            event: (row.getAttribute("data-event-name") || "").trim(),
            status: text(row.querySelector("[data-element='item-status-label']")),
          }));

          return {
            profile: {
              name: text(card.querySelector("h3.text-3xl.font-semibold, h3")),
              profile_link: profileLink?.getAttribute("href") || "",
              photo_url: photo?.getAttribute("src") || "",
              status_badge: text(statusBadge),
              university: readLabeledValue(card, "University"),
              major: readLabeledValue(card, "Major"),
              facilitator: readLabeledValue(card, "Facilitator"),
              lecturer: readLabeledValue(card, "Lecturer"),
            },
            progress: {
              attendances: {
                last_updated: text(
                  attendanceSection.querySelector(
                    "[data-element='attendance-last-update']"
                  )
                ).replace(/^Last updated:\s*/i, ""),
                items: attendanceItems,
                fallback_text_if_empty: text(
                  attendanceSection.querySelector(
                    "[data-element='attendance-none']"
                  )
                ),
                item_schema: {
                  event: "string",
                  status: "string",
                },
              },
              course_progress: {
                last_updated: text(
                  courseSection.querySelector(
                    "[data-element='course-progress-last-update']"
                  )
                ).replace(/^Last updated:\s*/i, ""),
                items: courseItems,
              },
              assignments: {
                last_updated: text(
                  assignmentSection.querySelector(
                    "[data-element='assignment-last-update']"
                  )
                ).replace(/^Last updated:\s*/i, ""),
                items: assignmentItems,
                fallback_text_if_empty: text(
                  assignmentSection.querySelector(
                    "[data-element='assignment-none']"
                  )
                ),
              },
              daily_checkins: {
                items: [],
              },
            },
          };
        });
        """
    )
    if not isinstance(payload, list):
        raise RuntimeError("DOM extraction students gagal: payload invalid")

    students: list[dict] = []
    for raw_student in payload:
        if not isinstance(raw_student, dict):
            continue

        raw_profile = raw_student.get("profile", {})
        raw_progress = raw_student.get("progress", {})
        raw_attendances = (
            raw_progress.get("attendances", {})
            if isinstance(raw_progress, dict)
            else {}
        )
        raw_course_progress = (
            raw_progress.get("course_progress", {})
            if isinstance(raw_progress, dict)
            else {}
        )
        raw_assignments = (
            raw_progress.get("assignments", {})
            if isinstance(raw_progress, dict)
            else {}
        )

        attendance_items: list[dict[str, str]] = []
        for raw_item in raw_attendances.get("items", []):
            if not isinstance(raw_item, dict):
                continue
            attendance_items.append(
                build_attendance_item(
                    str(raw_item.get("event", "")),
                    str(raw_item.get("status", "")),
                )
            )

        course_items: list[dict[str, str]] = []
        for raw_item in raw_course_progress.get("items", []):
            if not isinstance(raw_item, dict):
                continue
            course_items.append(
                {
                    "course": normalize_space(str(raw_item.get("course", ""))),
                    "progress_percent": normalize_space(
                        str(raw_item.get("progress_percent", ""))
                    ),
                    "status": normalize_space(str(raw_item.get("status", ""))),
                }
            )

        assignment_items: list[dict[str, str]] = []
        for raw_item in raw_assignments.get("items", []):
            if not isinstance(raw_item, dict):
                continue
            assignment_items.append(
                {
                    "assignment": normalize_space(
                        str(raw_item.get("assignment", ""))
                    ),
                    "status": normalize_space(str(raw_item.get("status", ""))),
                }
            )

        students.append(
            {
                "profile": {
                    "name": normalize_space(
                        str(raw_profile.get("name", ""))
                    ),
                    "profile_link": normalize_space(
                        str(raw_profile.get("profile_link", ""))
                    ),
                    "photo_url": normalize_space(
                        str(raw_profile.get("photo_url", ""))
                    ),
                    "status_badge": normalize_space(
                        str(raw_profile.get("status_badge", ""))
                    ),
                    "university": normalize_space(
                        str(raw_profile.get("university", ""))
                    ),
                    "major": normalize_space(
                        str(raw_profile.get("major", ""))
                    ),
                    "facilitator": normalize_space(
                        str(raw_profile.get("facilitator", ""))
                    ),
                    "lecturer": normalize_space(
                        str(raw_profile.get("lecturer", ""))
                    ),
                },
                "progress": {
                    "attendances": {
                        "last_updated": normalize_space(
                            str(raw_attendances.get("last_updated", ""))
                        ),
                        "items": attendance_items,
                        "fallback_text_if_empty": normalize_space(
                            str(
                                raw_attendances.get(
                                    "fallback_text_if_empty", ""
                                )
                            )
                        ),
                        "item_schema": {
                            "event": "string",
                            "status": "string",
                        },
                    },
                    "course_progress": {
                        "last_updated": normalize_space(
                            str(raw_course_progress.get("last_updated", ""))
                        ),
                        "items": course_items,
                    },
                    "assignments": {
                        "last_updated": normalize_space(
                            str(raw_assignments.get("last_updated", ""))
                        ),
                        "items": assignment_items,
                        "fallback_text_if_empty": normalize_space(
                            str(
                                raw_assignments.get(
                                    "fallback_text_if_empty", ""
                                )
                            )
                        ),
                    },
                    "daily_checkins": {
                        "items": [],
                    },
                },
            }
        )

    return students


def extract_mentor_from_dom(
    driver: webdriver.Chrome, expected_email: str = ""
) -> dict:
    return driver.execute_script(
        r"""
        const text = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();
        const dedupe = (arr) => Array.from(new Set(arr));
        const expectedEmail = (arguments[0] || "").trim().toLowerCase();
        const emailRegex = /[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}/gi;
        const extractEmails = (value) => Array.from((value || "").matchAll(emailRegex)).map((m) => m[0].toLowerCase());
        const nav = Array.from(document.querySelectorAll("a.nav-link"))
          .map((el) => text(el))
          .filter(Boolean);
        const mailtoEmails = dedupe(
          Array.from(document.querySelectorAll("a[href^='mailto:']"))
            .map((el) => (el.getAttribute("href") || "").replace(/^mailto:/i, "").trim())
            .map((v) => v.toLowerCase())
            .filter(Boolean)
        );
        const sidebar = document.querySelector(".sidebar-menu");
        const sidebarEmails = dedupe(extractEmails(text(sidebar)));

        const visibleNodeEmails = dedupe(
          Array.from(document.querySelectorAll("p,span,div,label,li,td,th,a"))
            .map((el) => text(el))
            .filter((v) => v.includes("@"))
            .flatMap((v) => extractEmails(v))
        );

        const emailLabelCandidates = dedupe(
          Array.from(document.querySelectorAll("p,span,div,label,dt,th"))
            .filter((el) => /^email$/i.test(text(el)))
            .flatMap((emailLabel) => {
              const container = emailLabel.closest("li,div,section,tr,dl,article") || emailLabel.parentElement;
              return extractEmails(text(container));
            })
        );

        const allCandidates = dedupe([
          ...sidebarEmails,
          ...emailLabelCandidates,
          ...visibleNodeEmails,
          ...mailtoEmails,
        ]);

        const supportEmail = mailtoEmails[0] || "";
        let mentorEmail = "";

        if (expectedEmail && allCandidates.includes(expectedEmail)) {
          mentorEmail = expectedEmail;
        } else {
          mentorEmail =
            allCandidates.find((value) => value && value !== supportEmail) ||
            sidebarEmails[0] ||
            supportEmail ||
            "";
        }

        return {
          name: text(document.querySelector(".sidebar-menu .text-xl")),
          mentor_code: text(document.querySelector(".sidebar-menu .text-id.uppercase")),
          group: text(document.querySelector("li .font-normal.text-black.pt-1.pl-5")),
          nav_items: nav,
          email: mentorEmail
        };
        """,
        normalize_space(str(expected_email or "")),
    )
