# ruff: noqa: E501

from __future__ import annotations

import json
import time

from selenium import webdriver
from selenium.webdriver.common.by import By

from .selenium_ui import click_element


def normalize_space(text: str) -> str:
    return " ".join((text or "").split()).strip()


def build_attendance_item(activity_name: str, status: str) -> dict:
    event = normalize_space(activity_name)
    status = normalize_space(status)
    return {
        "event": event,
        "status": status,
    }


def ensure_student_progress_structure(student: dict) -> dict:
    progress = student.get("progress")
    if not isinstance(progress, dict):
        progress = {}
    student["progress"] = progress

    attendances = progress.get("attendances")
    if not isinstance(attendances, dict):
        attendances = {}
    attendances.setdefault("last_updated", "")
    attendances.setdefault("items", [])
    attendances.setdefault("fallback_text_if_empty", "")
    attendances.setdefault(
        "item_schema",
        {
            "event": "string",
            "status": "string",
        },
    )
    attendances.setdefault(
        "item_template",
        {
            "event": "",
            "status": "",
        },
    )

    normalized_items = []
    for raw_item in attendances.get("items", []):
        if not isinstance(raw_item, dict):
            continue
        activity_name = (
            raw_item.get("event") or raw_item.get("activity_name") or ""
        )
        status = raw_item.get("status") or ""
        normalized_items.append(build_attendance_item(activity_name, status))
    if not normalized_items:
        normalized_items = [build_attendance_item("", "")]
    attendances["items"] = normalized_items

    progress["attendances"] = attendances

    progress["attendance"] = {
        "last_updated": attendances.get("last_updated", ""),
        "items": attendances.get("items", []),
        "fallback_text_if_empty": attendances.get(
            "fallback_text_if_empty", ""
        ),
        "item_schema": attendances.get("item_schema", {}),
        "item_template": attendances.get("item_template", {}),
    }

    return student


def build_attendance_progress_from_dom(
    driver: webdriver.Chrome, student_index: int
) -> dict:
    student_cards = driver.find_elements(
        By.CSS_SELECTOR, "div.container.flex.flex-col.pb-8.border-b"
    )
    if student_index >= len(student_cards):
        return {
            "last_updated": "",
            "items": [],
            "fallback_text_if_empty": "",
        }

    card = student_cards[student_index]
    payload = driver.execute_script(
        r"""
        const card = arguments[0];
        const text = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();
        const section =
          card.querySelector("section.attendances") ||
          card.querySelector("section.attendance");
        const scope = section || card;

        const rows = Array.from(scope.querySelectorAll("[data-event-name]")).map((row) => {
          const statusEl = row.querySelector("[data-element='item-status-label']");
          return {
            event_name: (row.getAttribute("data-event-name") || "").trim(),
            status_label: text(statusEl),
          };
        });

        const fallbackText =
          text(scope.querySelector("[data-element='attendance-none']")) ||
          text(scope.querySelector("p.text-sm.text-gray-700"));

        const lastUpdatedRaw = text(
          scope.querySelector("[data-element='attendance-last-update']")
        );

        return {
          last_updated: lastUpdatedRaw.replace(/^Last updated:\s*/i, ""),
          fallback_text_if_empty: fallbackText,
          items: rows,
        };
        """,
        card,
    )

    items = [
        build_attendance_item(
            row.get("event_name", ""), row.get("status_label", "")
        )
        for row in payload.get("items", [])
    ]
    return {
        "last_updated": normalize_space(payload.get("last_updated", "")),
        "items": items,
        "fallback_text_if_empty": normalize_space(
            payload.get("fallback_text_if_empty", "")
        ),
    }


def click_all_buttons_by_keyword(
    driver: webdriver.Chrome, keyword: str, max_clicks: int = 500
) -> int:
    keyword = keyword.lower()
    payload = driver.execute_async_script(
        """
        const keyword = arguments[0];
        const maxClicks = arguments[1];
        const done = arguments[arguments.length - 1];
        const text = (el) => (el?.textContent || "").replace(/\\s+/g, " ").trim().toLowerCase();
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

        (async () => {
          let clicked = 0;

          for (let round = 0; round < 30; round += 1) {
            const buttons = Array.from(document.querySelectorAll("button"))
              .filter((el) => {
                const visible = !!(el.offsetWidth || el.offsetHeight || el.getClientRects().length);
                const disabled = el.hasAttribute("disabled");
                return visible && !disabled && text(el).includes(keyword);
              });

            if (buttons.length === 0 || clicked >= maxClicks) {
              break;
            }

            for (const button of buttons) {
              if (clicked >= maxClicks) {
                break;
              }
              button.click();
              clicked += 1;
            }

            await sleep(60);
          }

          done({ ok: true, clicked });
        })().catch((error) => done({ ok: false, error: String(error) }));
        """,
        keyword,
        max_clicks,
    )
    if not payload or not payload.get("ok"):
        return 0
    return int(payload.get("clicked", 0))


def extract_daily_checkins_all_students_fast(
    driver: webdriver.Chrome,
    *,
    delay_ms: int = 120,
) -> list[list[dict]]:
    payload = driver.execute_async_script(
        r"""
        const delayMs = Number(arguments[0] || 80);
        const done = arguments[arguments.length - 1];
        const text = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const maxSteps = 300;

        const readEntries = (section) => {
          const cards = Array.from(section.querySelectorAll("div.border-b.p-6"));
          return cards.map((card) => {
            const mood = text(card.querySelector("p.text-lg"));
            const date = text(card.querySelector("p.text-sm.text-gray-500"));

            const reflectionHeading = Array.from(
              card.querySelectorAll("p.text-md.font-semibold")
            ).find((el) => /reflection/i.test(text(el)));
            let reflection = "";
            if (reflectionHeading) {
              reflection = text(
                reflectionHeading.parentElement?.querySelector(
                  "p.text-sm.text-gray-700"
                )
              );
            }

            const goalsHeading = Array.from(
              card.querySelectorAll("p.text-md.font-semibold")
            ).find((el) => /goals/i.test(text(el)));
            let goals = [];
            if (goalsHeading) {
              const goalsRoot = goalsHeading.parentElement;
              const groups = Array.from(
                goalsRoot.querySelectorAll("div.mb-3, div.last\\:mb-0")
              );

              if (groups.length === 0) {
                const fallbackItems = Array.from(
                  goalsRoot.querySelectorAll("li")
                )
                  .map((el) => text(el))
                  .filter(Boolean);
                if (fallbackItems.length > 0) {
                  goals.push({ title: "", items: fallbackItems });
                }
              } else {
                goals = groups.map((group) => ({
                  title: text(group.querySelector("p.text-sm.font-semibold")),
                  items: Array.from(group.querySelectorAll("li"))
                    .map((el) => text(el))
                    .filter(Boolean),
                }));
              }
            }

            return { mood, date, reflection, goals };
          });
        };

        const nextButton = (section) => {
          const buttons = Array.from(section.querySelectorAll("button"));
          return (
            buttons.find((btn) => /^next$/i.test(text(btn))) ||
            buttons.find((btn) => /next/i.test(text(btn))) ||
            null
          );
        };

        const isDisabled = (button) => {
          if (!button) {
            return true;
          }
          const disabledAttr = button.hasAttribute("disabled");
          const ariaDisabled = (button.getAttribute("aria-disabled") || "")
            .toLowerCase()
            .trim();
          return disabledAttr || ariaDisabled === "true" || !button.isConnected;
        };

        const keyForEntry = (entry) =>
          JSON.stringify({
            mood: entry.mood || "",
            date: entry.date || "",
            reflection: entry.reflection || "",
            goals: entry.goals || [],
          });

        (async () => {
          const sections = Array.from(
            document.querySelectorAll("section.daily-checkins")
          );
          const allItems = [];

          for (const section of sections) {
            const items = [];
            const seen = new Set();
            let staleRounds = 0;

            for (let step = 0; step < maxSteps; step += 1) {
              const entries = readEntries(section);
              const before = seen.size;

              for (const entry of entries) {
                const key = keyForEntry(entry);
                if (seen.has(key)) {
                  continue;
                }
                seen.add(key);
                items.push(JSON.parse(key));
              }

              staleRounds = seen.size === before ? staleRounds + 1 : 0;
              const next = nextButton(section);
              if (!next || isDisabled(next) || staleRounds >= 2) {
                break;
              }

              next.click();
              await sleep(delayMs);
            }

            allItems.push(items);
          }

          done({ ok: true, items: allItems });
        })().catch((error) => done({ ok: false, error: String(error) }));
        """,
        delay_ms,
    )

    if not payload or not payload.get("ok"):
        message = (
            payload.get("error") if isinstance(payload, dict) else payload
        )
        raise RuntimeError(f"Fast extraction daily-checkins gagal: {message}")
    return payload.get("items", [])


def extract_point_histories_all_students_fast(
    driver: webdriver.Chrome,
    *,
    delay_ms: int = 120,
) -> list[dict]:
    payload = driver.execute_async_script(
        r"""
        const delayMs = Number(arguments[0] || 80);
        const done = arguments[arguments.length - 1];
        const text = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
        const maxSteps = 300;

        const nextButton = (section) => {
          const buttons = Array.from(section.querySelectorAll("button"));
          return (
            buttons.find((btn) => /^next$/i.test(text(btn))) ||
            buttons.find((btn) => /next/i.test(text(btn))) ||
            null
          );
        };

        const isDisabled = (button) => {
          if (!button) {
            return true;
          }
          const disabledAttr = button.hasAttribute("disabled");
          const ariaDisabled = (button.getAttribute("aria-disabled") || "")
            .toLowerCase()
            .trim();
          return disabledAttr || ariaDisabled === "true" || !button.isConnected;
        };

        (async () => {
          const sections = Array.from(
            document.querySelectorAll("section.point-histories")
          );
          const allItems = [];

          for (const section of sections) {
            let lastUpdated = "";
            let totalPoint = "";
            let fallbackText = "";
            const items = [];
            const seen = new Set();
            let staleRounds = 0;

            for (let step = 0; step < maxSteps; step += 1) {
              const lastUpdatedRaw = text(
                section.querySelector("[data-element='point-histories-last-update']")
              );
              if (lastUpdatedRaw) {
                lastUpdated = lastUpdatedRaw.replace(/^Last updated:\s*/i, "");
              }

              const totalBlock = Array.from(
                section.querySelectorAll(
                  "div.flex.justify-between.items-center.border-b.p-6"
                )
              ).find((el) => /total point/i.test(text(el)));
              if (totalBlock) {
                totalPoint = text(totalBlock.querySelector("p.text-lg, p.text-xl"));
              }

              const noneText = text(
                section.querySelector("[data-element='point-histories-none']")
              );
              if (noneText) {
                fallbackText = noneText;
              }

              const rows = Array.from(
                section.querySelectorAll("div.space-y-0 > div")
              )
                .map((row) => {
                  const values = Array.from(row.querySelectorAll("p,span"))
                    .map((el) => text(el))
                    .filter(Boolean);
                  const rawText = text(row);
                  return { values, raw_text: rawText };
                })
                .filter(
                  (row) =>
                    row.raw_text &&
                    !/you have no point histories data/i.test(row.raw_text)
                );

              const before = seen.size;
              for (const row of rows) {
                const key = JSON.stringify({
                  raw_text: row.raw_text || "",
                  values: row.values || [],
                });
                if (seen.has(key)) {
                  continue;
                }
                seen.add(key);
                items.push(JSON.parse(key));
              }

              staleRounds = seen.size === before ? staleRounds + 1 : 0;
              const next = nextButton(section);
              if (!next || isDisabled(next) || staleRounds >= 2) {
                break;
              }

              next.click();
              await sleep(delayMs);
            }

            allItems.push({
              last_updated: lastUpdated,
              total_point: totalPoint,
              items,
              fallback_text_if_empty: fallbackText,
            });
          }

          done({ ok: true, items: allItems });
        })().catch((error) => done({ ok: false, error: String(error) }));
        """,
        delay_ms,
    )

    if not payload or not payload.get("ok"):
        message = (
            payload.get("error") if isinstance(payload, dict) else payload
        )
        raise RuntimeError(f"Fast extraction point-histories gagal: {message}")
    return payload.get("items", [])


def extract_daily_checkins_all_pages(
    driver: webdriver.Chrome,
    student_index: int,
    *,
    max_steps: int = 300,
) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    stale_rounds = 0

    for _ in range(max_steps):
        sections = driver.find_elements(
            By.CSS_SELECTOR, "section.daily-checkins"
        )
        if student_index >= len(sections):
            break
        section = sections[student_index]

        entries = driver.execute_script(
            r"""
            const section = arguments[0];
            const text = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();
            const cards = Array.from(section.querySelectorAll("div.border-b.p-6"));
            return cards.map((card) => {
              const mood = text(card.querySelector("p.text-lg"));
              const date = text(card.querySelector("p.text-sm.text-gray-500"));
              const reflectionHeading = Array.from(card.querySelectorAll("p.text-md.font-semibold"))
                .find((el) => /reflection/i.test(text(el)));
              let reflection = "";
              if (reflectionHeading) {
                reflection = text(reflectionHeading.parentElement?.querySelector("p.text-sm.text-gray-700"));
              }

              const goalsHeading = Array.from(card.querySelectorAll("p.text-md.font-semibold"))
                .find((el) => /goals/i.test(text(el)));
              let goals = [];
              if (goalsHeading) {
                const goalsRoot = goalsHeading.parentElement;
                const groups = Array.from(goalsRoot.querySelectorAll("div.mb-3, div.last\\:mb-0"));
                if (groups.length === 0) {
                  const fallbackItems = Array.from(goalsRoot.querySelectorAll("li")).map((el) => text(el)).filter(Boolean);
                  if (fallbackItems.length > 0) {
                    goals.push({ title: "", items: fallbackItems });
                  }
                } else {
                  goals = groups.map((group) => ({
                    title: text(group.querySelector("p.text-sm.font-semibold")),
                    items: Array.from(group.querySelectorAll("li")).map((el) => text(el)).filter(Boolean),
                  }));
                }
              }

              return { mood, date, reflection, goals };
            });
            """,
            section,
        )

        before = len(seen)
        for entry in entries:
            key = json.dumps(
                {
                    "mood": normalize_space(entry.get("mood", "")),
                    "date": normalize_space(entry.get("date", "")),
                    "reflection": normalize_space(entry.get("reflection", "")),
                    "goals": entry.get("goals", []),
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(json.loads(key))

        if len(seen) == before:
            stale_rounds += 1
        else:
            stale_rounds = 0

        next_buttons = section.find_elements(
            By.XPATH,
            ".//button[normalize-space()='Next' or .//span[normalize-space()='Next']]",
        )
        if not next_buttons:
            break
        next_button = next_buttons[0]
        disabled = next_button.get_attribute("disabled") is not None or (
            not next_button.is_enabled()
        )
        if disabled or stale_rounds >= 2:
            break

        click_element(driver, next_button)
        time.sleep(0.35)

    return items


def extract_point_histories_all_pages(
    driver: webdriver.Chrome,
    student_index: int,
    *,
    max_steps: int = 300,
) -> dict:
    last_updated = ""
    total_point = ""
    items: list[dict] = []
    seen: set[str] = set()
    none_text = ""
    stale_rounds = 0

    for _ in range(max_steps):
        sections = driver.find_elements(
            By.CSS_SELECTOR, "section.point-histories"
        )
        if student_index >= len(sections):
            break
        section = sections[student_index]

        payload = driver.execute_script(
            r"""
            const section = arguments[0];
            const text = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();

            const lastUpdatedRaw = text(section.querySelector("[data-element='point-histories-last-update']"));
            const totalBlock = Array.from(section.querySelectorAll("div.flex.justify-between.items-center.border-b.p-6"))
              .find((el) => /total point/i.test(text(el)));
            const totalPoint = totalBlock ? text(totalBlock.querySelector("p.text-lg, p.text-xl")) : "";
            const noneText = text(section.querySelector("[data-element='point-histories-none']"));

            const rows = Array.from(section.querySelectorAll("div.space-y-0 > div"))
              .map((row) => {
                const values = Array.from(row.querySelectorAll("p,span")).map((el) => text(el)).filter(Boolean);
                const rawText = text(row);
                return { values, raw_text: rawText };
              })
              .filter((row) => row.raw_text && !/you have no point histories data/i.test(row.raw_text));

            return {
              last_updated: lastUpdatedRaw.replace(/^Last updated:\s*/i, ""),
              total_point: totalPoint,
              none_text: noneText,
              rows
            };
            """,
            section,
        )

        last_updated = normalize_space(
            payload.get("last_updated", "") or last_updated
        )
        total_point = normalize_space(
            payload.get("total_point", "") or total_point
        )
        none_text = normalize_space(payload.get("none_text", "") or none_text)

        before = len(seen)
        for row in payload.get("rows", []):
            key = json.dumps(
                {
                    "raw_text": normalize_space(row.get("raw_text", "")),
                    "values": [
                        normalize_space(v) for v in row.get("values", [])
                    ],
                },
                ensure_ascii=False,
                sort_keys=True,
            )
            if key in seen:
                continue
            seen.add(key)
            items.append(json.loads(key))

        if len(seen) == before:
            stale_rounds += 1
        else:
            stale_rounds = 0

        next_buttons = section.find_elements(
            By.XPATH,
            ".//button[normalize-space()='Next' or .//span[normalize-space()='Next']]",
        )
        if not next_buttons:
            break
        next_button = next_buttons[0]
        disabled = next_button.get_attribute("disabled") is not None or (
            not next_button.is_enabled()
        )
        if disabled or stale_rounds >= 2:
            break

        click_element(driver, next_button)
        time.sleep(0.35)

    return {
        "last_updated": last_updated,
        "total_point": total_point,
        "items": items,
        "fallback_text_if_empty": none_text,
    }
