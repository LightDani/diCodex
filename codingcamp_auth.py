from __future__ import annotations

import time
from dataclasses import dataclass
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from browser_runtime import create_bootstrapped_driver
from selenium_ui import click_element, find_first_visible, wait_for_page_ready

AUTH_WAIT_SECONDS = 30


def normalize_space(text: str) -> str:
    return " ".join((text or "").split()).strip()


@dataclass(frozen=True)
class CodingcampAuthOptions:
    auth_mode: str
    headed: bool
    profile_dir: Path
    load_images: bool
    enable_perf_logs: bool
    browser_path: str
    driver_path: str
    runtime_dir: Path
    offline: bool
    manual_login_timeout: int


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
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    email: str,
    password: str,
) -> None:
    wait.until(
        ec.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[type='password']")
        )
    )

    if not email or not password:
        raise ValueError(
            "EMAIL/PASSWORD kosong. "
            "Isi file `secret.py` agar bisa login otomatis."
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
                "//button[contains(., 'Sign in') "
                "or contains(., 'Login') "
                "or contains(., 'Masuk')]",
            ),
        ],
    )

    if not email_input or not password_input or not submit_button:
        raise NoSuchElementException(
            "Komponen form login email/password tidak lengkap."
        )

    email_input.clear()
    email_input.send_keys(email)
    password_input.clear()
    password_input.send_keys(password)
    click_element(driver, submit_button)


def is_authenticated(driver: webdriver.Chrome, codingcamp_url: str) -> bool:
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
            const hasLoginForm =
              hasPasswordInput || (hasEmailInput && hasLoginCta);

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

        if current_url.startswith(codingcamp_url) and not bool(
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
    codingcamp_url: str,
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

        if is_authenticated(driver, codingcamp_url):
            wait_for_page_ready(driver, wait)
            print("Login manual terdeteksi, lanjut ke proses scraping...")
            return
        time.sleep(1)

    raise TimeoutException(
        "Login manual timeout. Masih belum terdeteksi masuk ke dashboard "
        "CodingCamp sebelum batas waktu."
    )


def extract_logged_in_email(driver: webdriver.Chrome) -> str:
    value = driver.execute_script(
        r"""
        const readEmail = (storage) => {
          if (!storage) {
            return "";
          }
          for (let i = 0; i < storage.length; i += 1) {
            const key = storage.key(i) || "";
            if (!/firebase:authuser/i.test(key)) {
              continue;
            }
            const rawValue = storage.getItem(key) || "";
            if (!rawValue) {
              continue;
            }
            try {
              const parsed = JSON.parse(rawValue);
              if (
                parsed &&
                typeof parsed.email === "string" &&
                parsed.email.trim()
              ) {
                return parsed.email.trim().toLowerCase();
              }
            } catch (_error) {}
          }
          return "";
        };

        return (
          readEmail(window.localStorage) ||
          readEmail(window.sessionStorage)
        );
        """
    )
    return normalize_space(str(value or "")).lower()


def perform_codingcamp_auth(
    options: CodingcampAuthOptions,
    *,
    codingcamp_url: str,
    email: str,
    password: str,
    script_timeout_seconds: int,
) -> tuple[webdriver.Chrome, str]:
    has_secret = bool(email and password)
    expected_login_email = normalize_space(str(email or "")).lower()
    mode = options.auth_mode
    should_attempt_auto = mode == "auto" or (mode == "hybrid" and has_secret)
    initial_headless = should_attempt_auto and not options.headed
    profile_dir = options.profile_dir

    driver = create_bootstrapped_driver(
        headless=initial_headless,
        disable_images=not options.load_images,
        enable_perf_logs=options.enable_perf_logs,
        user_data_dir=profile_dir,
        browser_path_override=options.browser_path,
        driver_path_override=options.driver_path,
        runtime_dir=options.runtime_dir,
        offline=options.offline,
        script_timeout_seconds=script_timeout_seconds,
    )
    wait = WebDriverWait(driver, AUTH_WAIT_SECONDS)

    def go_home() -> None:
        driver.get(codingcamp_url)
        wait_for_page_ready(driver, wait)

    try:
        go_home()
        if is_authenticated(driver, codingcamp_url):
            return driver, (
                extract_logged_in_email(driver) or expected_login_email
            )

        if should_attempt_auto:
            try:
                if not has_secret:
                    raise ValueError(
                        "EMAIL/PASSWORD kosong; "
                        "auto-login tidak bisa dijalankan."
                    )

                click_password_link(driver, wait)
                login_with_email_password(driver, wait, email, password)
                wait.until(lambda d: is_authenticated(d, codingcamp_url))
                wait_for_page_ready(driver, wait)
                return driver, (
                    expected_login_email or extract_logged_in_email(driver)
                )
            except Exception as error:
                print(
                    f"Auto-login gagal ({error}). Fallback ke login manual..."
                )

        if initial_headless:
            driver.quit()
            driver = create_bootstrapped_driver(
                headless=False,
                disable_images=not options.load_images,
                enable_perf_logs=options.enable_perf_logs,
                user_data_dir=profile_dir,
                browser_path_override=options.browser_path,
                driver_path_override=options.driver_path,
                runtime_dir=options.runtime_dir,
                offline=options.offline,
                script_timeout_seconds=script_timeout_seconds,
            )
            wait = WebDriverWait(driver, AUTH_WAIT_SECONDS)

        go_home()
        wait_for_manual_codingcamp_login(
            driver,
            wait,
            options.manual_login_timeout,
            codingcamp_url,
        )
        return driver, (
            extract_logged_in_email(driver) or expected_login_email
        )
    except Exception:
        driver.quit()
        raise
