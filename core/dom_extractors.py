# ruff: noqa: E501

from __future__ import annotations

import html
import re

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
        "university": one(
            r'<p class="text-sm text-gray-700">University</p></div><p class="font-normal text-black pl-4">([^<]+)</p>',
            block_html,
        ),
        "major": one(
            r'<p class="text-sm text-gray-700">Major</p></div><p class="font-normal text-black pl-4">([^<]+)</p>',
            block_html,
        ),
        "facilitator": one(
            r'<p class="text-sm text-gray-700">Facilitator</p></div><p class="font-normal text-black pl-4 break-words">([^<]+)</p>',
            block_html,
        ),
        "lecturer": one(
            r'<p class="text-sm text-gray-700">Lecturer</p></div><p class="font-normal text-black pl-4(?: break-words)?">([^<]+)</p>',
            block_html,
        ),
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
