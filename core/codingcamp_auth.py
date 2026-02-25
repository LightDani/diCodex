from __future__ import annotations

import shutil
import time
from dataclasses import dataclass
from logging import Logger
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait

from .browser_runtime import create_bootstrapped_driver
from .logging_utils import get_logger
from .selenium_ui import click_element, find_first_visible, wait_for_page_ready

AUTH_WAIT_SECONDS = 30
LOGGER: Logger = get_logger(__name__)


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
    LOGGER.info(
        "Silakan login manual pada browser Selenium yang terbuka. "
        "Script akan menunggu sampai login berhasil (maks %s detik).",
        timeout,
    )

    deadline = time.time() + timeout
    while time.time() < deadline:
        current_url = (driver.current_url or "").lower()
        if "/login" not in current_url:
            try:
                wait_for_page_ready(driver, wait)
            except Exception:
                pass
            LOGGER.info("manual_login.detected state=url_non_login")
            return

        if is_authenticated(driver, codingcamp_url):
            wait_for_page_ready(driver, wait)
            LOGGER.info("manual_login.detected state=authenticated")
            return
        time.sleep(1)

    raise TimeoutException(
        "Login manual timeout. Masih belum terdeteksi masuk ke dashboard "
        "CodingCamp sebelum batas waktu."
    )


def extract_logged_in_email(driver: webdriver.Chrome) -> str:
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
            const fromParsed = extractFromParsed(parseMaybeJson(rawValue));
            if (normalize(fromParsed)) {
              return fromParsed;
            }
            const fromRaw = rawValue.match(emailRegex)?.[0] || "";
            if (normalize(fromRaw)) {
              return fromRaw;
            }
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


def extract_logged_in_email_from_indexeddb(driver: webdriver.Chrome) -> str:
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
                return rawValue.match(emailRegex)?.[0] || "";
              }
              if (
                typeof rawValue.email === "string" &&
                normalize(rawValue.email)
              ) {
                return rawValue.email;
              }
              const asText = JSON.stringify(rawValue);
              return asText.match(emailRegex)?.[0] || "";
            };

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


def cached_login_email_path(profile_dir: Path) -> Path:
    return profile_dir.expanduser() / ".last_login_email"


def save_cached_login_email(profile_dir: Path, email: str) -> None:
    normalized = normalize_space(str(email or "")).lower()
    if not normalized:
        return
    cache_path = cached_login_email_path(profile_dir)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(normalized, encoding="utf-8")


def reset_profile_session(profile_dir: Path) -> None:
    resolved = profile_dir.expanduser()
    if resolved.exists():
        shutil.rmtree(resolved)
    resolved.mkdir(parents=True, exist_ok=True)
    LOGGER.info("auth.profile_reset path=%s", resolved)


def perform_codingcamp_auth(
    options: CodingcampAuthOptions,
    *,
    codingcamp_url: str,
    email: str,
    password: str,
    script_timeout_seconds: int,
) -> tuple[webdriver.Chrome, str]:
    profile_dir = options.profile_dir
    reset_profile_session(profile_dir)
    has_secret = bool(email and password)
    mode = options.auth_mode

    should_attempt_auto = mode == "auto" or (mode == "hybrid" and has_secret)
    needs_manual_login = mode == "manual" or not should_attempt_auto
    initial_headless = not options.headed and not needs_manual_login
    LOGGER.info(
        "auth.mode mode=%s has_secret=%s "
        "should_attempt_auto=%s initial_headless=%s",
        mode,
        has_secret,
        should_attempt_auto,
        initial_headless,
    )

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

        if should_attempt_auto:
            LOGGER.info("auth.auto_attempt enabled=true")
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
                LOGGER.info("auth.auto_success")
                resolved_email = (
                    extract_logged_in_email(driver)
                    or extract_logged_in_email_from_indexeddb(driver)
                )
                save_cached_login_email(profile_dir, resolved_email)
                return driver, resolved_email
            except Exception as error:
                LOGGER.warning(
                    "auto_login.failed fallback=manual error=%s",
                    error,
                )

        if initial_headless:
            LOGGER.info("auth.relaunch_headed reason=manual_fallback")
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
        LOGGER.info("auth.manual_wait_start")
        wait_for_manual_codingcamp_login(
            driver,
            wait,
            options.manual_login_timeout,
            codingcamp_url,
        )
        LOGGER.info("auth.manual_success")
        resolved_email = (
            extract_logged_in_email(driver)
            or extract_logged_in_email_from_indexeddb(driver)
        )
        save_cached_login_email(profile_dir, resolved_email)
        return driver, resolved_email
    except Exception:
        driver.quit()
        raise
