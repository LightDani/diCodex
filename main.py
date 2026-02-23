# ruff: noqa: E501, W505

import argparse
import html
import json
import re
import time
from datetime import datetime, timezone
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

CODINGCAMP_URL = "https://codingcamp.dicoding.com"
ASAH_URL = "https://asah.dicoding.com"
OUTPUT_DIR = Path("output")
MAX_PAGINATION_STEPS = 300
INTERACTION_TIMEOUT_SECONDS = 20
ASYNC_SCRIPT_TIMEOUT_SECONDS = 240
FAST_PAGINATION_DELAY_MS = 120
DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS = 300

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
    return parser.parse_args()


def build_driver(
    *,
    headless: bool = False,
    disable_images: bool = False,
    enable_perf_logs: bool = False,
    user_data_dir: Path | None = None,
) -> webdriver.Chrome:
    options = webdriver.ChromeOptions()
    options.page_load_strategy = "eager"

    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--disable-extensions")
    options.add_argument("--disable-notifications")
    options.add_argument("--no-default-browser-check")
    options.add_argument("--no-first-run")
    if user_data_dir:
        profile_dir = user_data_dir.expanduser()
        profile_dir.mkdir(parents=True, exist_ok=True)
        options.add_argument(f"--user-data-dir={profile_dir.resolve()}")

    if disable_images:
        options.add_experimental_option(
            "prefs",
            {
                "profile.managed_default_content_settings.images": 2,
            },
        )

    if enable_perf_logs:
        options.set_capability(
            "goog:loggingPrefs",
            {
                "performance": "ALL",
            },
        )

    if Path("chromedriver/linux/chromedriver").exists():
        service = Service(executable_path="chromedriver/linux/chromedriver")
    elif Path("chromedriver/windows/chromedriver.exe").exists():
        service = Service(
            executable_path="chromedriver/windows/chromedriver.exe"
        )
    else:
        raise FileNotFoundError(
            "Chromedriver tidak ditemukan. Pastikan ada di "
            "`chromedriver/linux/chromedriver` atau `chromedriver/windows/chromedriver.exe`."
        )

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_script_timeout(ASYNC_SCRIPT_TIMEOUT_SECONDS)
    return driver


def normalize_space(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "")).strip()


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


def find_first_visible(
    driver: webdriver.Chrome, locators: list[tuple[str, str]]
):
    for by, value in locators:
        for element in driver.find_elements(by, value):
            if element.is_displayed():
                return element
    return None


def wait_for_page_ready(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    wait.until(
        lambda d: d.execute_script("return document.readyState") == "complete"
    )
    wait.until(ec.presence_of_element_located((By.CSS_SELECTOR, "body")))


def click_element(driver: webdriver.Chrome, element) -> None:
    driver.execute_script(
        "arguments[0].scrollIntoView({block: 'center'});", element
    )
    try:
        element.click()
    except Exception:
        driver.execute_script("arguments[0].click();", element)


def click_password_link(driver: webdriver.Chrome, wait: WebDriverWait) -> None:
    locators = [
        (By.LINK_TEXT, "your password"),
        (By.XPATH, "//a[normalize-space()='your password']"),
        (By.XPATH, "//a[contains(normalize-space(.), 'your password')]"),
    ]

    for locator in locators:
        try:
            element = wait.until(ec.element_to_be_clickable(locator))
            click_element(driver, element)
            return
        except TimeoutException:
            continue

    raise NoSuchElementException(
        "Link 'your password' tidak ditemukan atau tidak bisa diklik."
    )


def login_with_email_password(
    driver: webdriver.Chrome, wait: WebDriverWait
) -> None:
    wait.until(
        ec.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[type='password']")
        )
    )

    if not EMAIL or not PASSWORD:
        raise ValueError(
            "EMAIL/PASSWORD kosong. Isi file `secret.py` agar bisa login otomatis."
        )

    email_input = find_first_visible(
        driver,
        [
            (By.CSS_SELECTOR, "input[type='email']"),
            (By.NAME, "email"),
            (By.ID, "email"),
        ],
    )
    password_input = find_first_visible(
        driver,
        [
            (By.CSS_SELECTOR, "input[type='password']"),
            (By.NAME, "password"),
            (By.ID, "password"),
        ],
    )
    submit_button = find_first_visible(
        driver,
        [
            (By.CSS_SELECTOR, "button[type='submit']"),
            (By.CSS_SELECTOR, "input[type='submit']"),
            (
                By.XPATH,
                "//button[contains(., 'Sign in') or contains(., 'Login') or contains(., 'Masuk')]",
            ),
        ],
    )

    if not email_input or not password_input or not submit_button:
        raise NoSuchElementException(
            "Komponen form login email/password tidak lengkap."
        )

    email_input.clear()
    email_input.send_keys(EMAIL)
    password_input.clear()
    password_input.send_keys(PASSWORD)
    click_element(driver, submit_button)


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


def is_authenticated(driver: webdriver.Chrome) -> bool:
    current_url = (driver.current_url or "").lower()
    if "/login" in current_url:
        return False

    try:
        state = driver.execute_script(
            r"""
            const href = (window.location.href || "").toLowerCase();
            const normalized = (value) =>
              (value || "").replace(/\s+/g, " ").trim().toLowerCase();

            const hasPasswordInput = Boolean(
              document.querySelector("input[type='password']")
            );
            const hasEmailInput = Boolean(
              document.querySelector("input[type='email']")
            );
            const hasLoginCta = Array.from(
              document.querySelectorAll("button, input[type='submit']")
            ).some((el) => {
              const text = normalized(el.textContent || el.value);
              return (
                text.includes("send magic link") ||
                text.includes("sign in") ||
                text.includes("login") ||
                text.includes("masuk")
              );
            });
            const hasLoginForm = hasPasswordInput || (hasEmailInput && hasLoginCta);

            const hasStudentPicker = Array.from(
              document.querySelectorAll("input, button, div, span, label")
            ).some((el) => {
              const text = normalized(el.textContent);
              const placeholder = normalized(el.getAttribute("placeholder"));
              const ariaLabel = normalized(el.getAttribute("aria-label"));
              return (
                text.includes("student's name or id") ||
                placeholder.includes("student's name or id") ||
                ariaLabel.includes("student's name or id")
              );
            });
            const hasAttendanceSection =
              document.querySelectorAll("section.attendances").length > 0;

            let hasFirebaseSession = false;
            try {
              for (let i = 0; i < localStorage.length; i += 1) {
                const key = (localStorage.key(i) || "").toLowerCase();
                if (key.includes("firebase:authuser")) {
                  hasFirebaseSession = true;
                  break;
                }
              }
            } catch (_error) {}

            return {
              href,
              has_login_form: hasLoginForm,
              has_dashboard_signals: hasStudentPicker || hasAttendanceSection,
              has_firebase_session: hasFirebaseSession,
            };
            """
        )
        if not isinstance(state, dict):
            return "/login" not in current_url

        if "/login" in str(state.get("href", "")).lower():
            return False

        if bool(state.get("has_dashboard_signals", False)):
            return True

        if bool(state.get("has_firebase_session", False)) and not bool(
            state.get("has_login_form", False)
        ):
            return True

        if current_url.startswith(CODINGCAMP_URL) and not bool(
            state.get("has_login_form", False)
        ):
            return True
        return False
    except Exception:
        return "/login" not in current_url


def wait_for_manual_codingcamp_login(
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    timeout_seconds: int,
) -> None:
    timeout = max(1, timeout_seconds)
    print(
        "Silakan login manual pada browser Selenium yang terbuka. "
        f"Script akan menunggu sampai login berhasil (maks {timeout} detik)."
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        current_url = (driver.current_url or "").lower()
        if "/login" not in current_url:
            try:
                wait_for_page_ready(driver, wait)
            except Exception:
                pass
            print("Login manual terdeteksi, lanjut ke proses scraping...")
            return

        if is_authenticated(driver):
            wait_for_page_ready(driver, wait)
            print("Login manual terdeteksi, lanjut ke proses scraping...")
            return
        time.sleep(1)

    raise TimeoutException(
        "Login manual timeout. Masih belum terdeteksi masuk ke dashboard "
        "CodingCamp sebelum batas waktu."
    )


def perform_codingcamp_auth(args: argparse.Namespace) -> webdriver.Chrome:
    has_secret = bool(EMAIL and PASSWORD)
    mode = args.auth_mode
    should_attempt_auto = mode == "auto" or (mode == "hybrid" and has_secret)
    initial_headless = should_attempt_auto and not args.headed
    profile_dir = Path(args.profile_dir)

    driver = build_driver(
        headless=initial_headless,
        disable_images=not args.load_images,
        enable_perf_logs=args.enable_perf_logs,
        user_data_dir=profile_dir,
    )
    wait = WebDriverWait(driver, 30)

    def go_home() -> None:
        driver.get(CODINGCAMP_URL)
        wait_for_page_ready(driver, wait)

    try:
        go_home()
        if is_authenticated(driver):
            return driver

        if should_attempt_auto:
            try:
                if not has_secret:
                    raise ValueError(
                        "EMAIL/PASSWORD kosong; auto-login tidak bisa dijalankan."
                    )

                click_password_link(driver, wait)
                login_with_email_password(driver, wait)
                wait.until(is_authenticated)
                wait_for_page_ready(driver, wait)
                return driver
            except Exception as error:
                print(
                    f"Auto-login gagal ({error}). Fallback ke login manual..."
                )

        if initial_headless:
            driver.quit()
            driver = build_driver(
                headless=False,
                disable_images=not args.load_images,
                enable_perf_logs=args.enable_perf_logs,
                user_data_dir=profile_dir,
            )
            wait = WebDriverWait(driver, 30)

        go_home()
        wait_for_manual_codingcamp_login(
            driver, wait, args.manual_login_timeout
        )
        return driver
    except Exception:
        driver.quit()
        raise


def build_attendance_progress_from_dom(
    driver: webdriver.Chrome, student_index: int
) -> dict:
    sections = driver.find_elements(By.CSS_SELECTOR, "section.attendances")
    if student_index >= len(sections):
        return {
            "last_updated": "",
            "items": [],
            "fallback_text_if_empty": "",
        }

    section = sections[student_index]
    payload = driver.execute_script(
        r"""
        const section = arguments[0];
        const text = (el) => (el?.textContent || "").replace(/\s+/g, " ").trim();

        const rows = Array.from(section.querySelectorAll("[data-event-name]")).map((row) => {
          const statusEl = row.querySelector("[data-element='item-status-label']");
          return {
            event_name: (row.getAttribute("data-event-name") || "").trim(),
            status_label: text(statusEl),
          };
        });

        const fallbackText =
          text(section.querySelector("[data-element='attendance-none']")) ||
          text(section.querySelector("p.text-sm.text-gray-700"));

        const lastUpdatedRaw = text(
          section.querySelector("[data-element='attendance-last-update']")
        );

        return {
          last_updated: lastUpdatedRaw.replace(/^Last updated:\s*/i, ""),
          fallback_text_if_empty: fallbackText,
          items: rows,
        };
        """,
        section,
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

    # Keep singular alias so downstream consumer that expects "attendance"
    # still gets a stable structure.
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

        const loginEmailFoundInDom = expectedEmail ? allCandidates.includes(expectedEmail) : false;

        return {
          name: text(document.querySelector(".sidebar-menu .text-xl")),
          mentor_code: text(document.querySelector(".sidebar-menu .text-id.uppercase")),
          group: text(document.querySelector("li .font-normal.text-black.pt-1.pl-5")),
          nav_items: nav,
          email: mentorEmail,
          support_email: supportEmail,
          login_email_expected: expectedEmail,
          login_email_found_in_dom: loginEmailFoundInDom,
          email_candidates: allCandidates
        };
        """,
        expected_email,
    )


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
        FAST_PAGINATION_DELAY_MS,
    )

    if not payload or not payload.get("ok"):
        message = (
            payload.get("error") if isinstance(payload, dict) else payload
        )
        raise RuntimeError(f"Fast extraction daily-checkins gagal: {message}")
    return payload.get("items", [])


def extract_point_histories_all_students_fast(
    driver: webdriver.Chrome,
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
        FAST_PAGINATION_DELAY_MS,
    )

    if not payload or not payload.get("ok"):
        message = (
            payload.get("error") if isinstance(payload, dict) else payload
        )
        raise RuntimeError(f"Fast extraction point-histories gagal: {message}")
    return payload.get("items", [])


def extract_daily_checkins_all_pages(
    driver: webdriver.Chrome, student_index: int
) -> list[dict]:
    items: list[dict] = []
    seen: set[str] = set()
    stale_rounds = 0

    for _ in range(MAX_PAGINATION_STEPS):
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
    driver: webdriver.Chrome, student_index: int
) -> dict:
    last_updated = ""
    total_point = ""
    items: list[dict] = []
    seen: set[str] = set()
    none_text = ""
    stale_rounds = 0

    for _ in range(MAX_PAGINATION_STEPS):
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


def build_export_json(
    driver: webdriver.Chrome,
    *,
    use_fast_daily: bool = False,
    use_fast_points: bool = True,
) -> dict:
    mentor = extract_mentor_from_dom(driver, EMAIL)

    show_all_courses_clicked = click_all_buttons_by_keyword(
        driver, "show all courses"
    )
    show_all_assignments_clicked = click_all_buttons_by_keyword(
        driver, "show all assignments"
    )
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
                driver
            )
        except Exception as error:
            print(
                f"[warn] Fast daily-checkins gagal, fallback mode lama: "
                f"{error}"
            )

    if use_fast_points:
        try:
            fast_point_by_student = extract_point_histories_all_students_fast(
                driver
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
                "items": extract_daily_checkins_all_pages(driver, idx)
            }

        if fast_point_by_student and idx < len(fast_point_by_student):
            students[idx]["progress"]["point_histories"] = (
                fast_point_by_student[idx]
            )
        else:
            students[idx]["progress"]["point_histories"] = (
                extract_point_histories_all_pages(driver, idx)
            )

        students[idx] = ensure_student_progress_structure(students[idx])

    return {
        "metadata": {
            "generated_at_utc": datetime.now(timezone.utc).isoformat(),
            "source_url": driver.current_url,
            "student_total": len(students),
            "show_all_courses_clicked": show_all_courses_clicked,
            "show_all_assignments_clicked": show_all_assignments_clicked,
        },
        "mentor": mentor,
        "students": students,
    }


def capture_asah_live_attendance_reference(
    asah_email: str,
    *,
    enable_perf_logs: bool = False,
) -> Path:
    driver = build_driver(
        headless=False,
        disable_images=True,
        enable_perf_logs=enable_perf_logs,
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
            enable_perf_logs=args.enable_perf_logs,
        )
        print(f"ASAH attendance reference: {out_path}")
        return

    driver = perform_codingcamp_auth(args)

    try:
        wait = WebDriverWait(driver, 30)
        wait_for_page_ready(driver, wait)
        print("Autentikasi selesai. Memulai ekstraksi data...")

        expand_all_student_data(driver)

        payload = build_export_json(
            driver,
            use_fast_daily=args.experimental_fast_daily,
            use_fast_points=True,
        )
        group_name = sanitize_filename_part(
            payload["mentor"].get("group", "unknown_group")
        )
        out_path = OUTPUT_DIR / f"codingcamp_{group_name}_full.json"
        write_json_replace(out_path, payload)

        print(f"Export JSON: {out_path}")
    finally:
        driver.quit()


if __name__ == "__main__":
    main()
