from __future__ import annotations

import json
import logging
import os
import platform
import shutil
import stat
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.service import Service

DEFAULT_RUNTIME_DIR = Path(".runtime/browser")
CFT_LKG_URL = "https://googlechromelabs.github.io/chrome-for-testing/last-known-good-versions-with-downloads.json"
LOGGER = logging.getLogger(__name__)


def build_driver(
    *,
    headless: bool = False,
    disable_images: bool = False,
    enable_perf_logs: bool = False,
    user_data_dir: Path | None = None,
    browser_path: Path | None = None,
    driver_path: Path | None = None,
    script_timeout_seconds: int = 240,
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
    if browser_path:
        options.binary_location = str(browser_path.expanduser().resolve())

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

    if driver_path:
        service = Service(
            executable_path=str(driver_path.expanduser().resolve())
        )
        driver = webdriver.Chrome(service=service, options=options)
    else:
        driver = webdriver.Chrome(options=options)
    driver.set_script_timeout(script_timeout_seconds)
    return driver


def resolve_existing_path(path_value: str, label: str) -> Path | None:
    raw = (path_value or "").strip()
    if not raw:
        return None
    path = Path(raw).expanduser()
    if not path.exists():
        raise FileNotFoundError(
            f"{label} tidak ditemukan: {path}. Periksa path yang kamu berikan."
        )
    return path


def detect_bundled_driver_path() -> Path | None:
    candidates = [
        Path("chromedriver/linux/chromedriver"),
        Path("chromedriver/windows/chromedriver.exe"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def detect_system_browser_path() -> Path | None:
    system_name = platform.system().lower()
    if system_name == "linux":
        for name in (
            "google-chrome",
            "google-chrome-stable",
            "chromium",
            "chromium-browser",
            "chrome",
        ):
            found = shutil.which(name)
            if found:
                return Path(found)
        return None

    if system_name == "windows":
        roots = [
            os.environ.get("PROGRAMFILES", ""),
            os.environ.get("PROGRAMFILES(X86)", ""),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        suffixes = [
            Path("Google/Chrome/Application/chrome.exe"),
            Path("Chromium/Application/chrome.exe"),
        ]
        for root in roots:
            if not root:
                continue
            for suffix in suffixes:
                candidate = Path(root) / suffix
                if candidate.exists():
                    return candidate
        found = shutil.which("chrome")
        return Path(found) if found else None

    if system_name == "darwin":
        candidates = [
            Path(
                "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
            ),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return None

    return None


def cft_platform_layout() -> tuple[str, Path, Path]:
    system_name = platform.system().lower()
    machine = platform.machine().lower()

    if system_name == "linux":
        return (
            "linux64",
            Path("chrome-linux64/chrome"),
            Path("chromedriver-linux64/chromedriver"),
        )
    if system_name == "windows":
        platform_key = "win64" if "64" in machine else "win32"
        return (
            platform_key,
            Path(f"chrome-{platform_key}/chrome.exe"),
            Path(f"chromedriver-{platform_key}/chromedriver.exe"),
        )
    if system_name == "darwin":
        platform_key = "mac-arm64" if "arm" in machine else "mac-x64"
        return (
            platform_key,
            Path(
                "chrome-"
                f"{platform_key}/"
                "Google Chrome for Testing.app/"
                "Contents/MacOS/Google Chrome for Testing"
            ),
            Path(f"chromedriver-{platform_key}/chromedriver"),
        )
    raise RuntimeError(
        "OS "
        f"'{platform.system()}' belum didukung untuk auto-bootstrap runtime."
    )


def mark_executable(path: Path) -> None:
    if platform.system().lower() == "windows":
        return
    mode = path.stat().st_mode
    path.chmod(mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)


def find_cached_cft_runtime(runtime_dir: Path) -> tuple[Path, Path] | None:
    _, browser_rel, driver_rel = cft_platform_layout()
    cft_root = runtime_dir / "cft"
    browser_path = cft_root / browser_rel
    driver_path = cft_root / driver_rel
    if browser_path.exists() and driver_path.exists():
        return browser_path, driver_path
    return None


def download_zip_and_extract(url: str, target_dir: Path) -> None:
    target_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as temp_file:
        temp_path = Path(temp_file.name)

    try:
        with urllib.request.urlopen(url, timeout=90) as response:
            temp_path.write_bytes(response.read())
        with zipfile.ZipFile(temp_path, "r") as zip_ref:
            zip_ref.extractall(target_dir)
    finally:
        if temp_path.exists():
            temp_path.unlink()


def ensure_cft_runtime(runtime_dir: Path, offline: bool) -> tuple[Path, Path]:
    cached = find_cached_cft_runtime(runtime_dir)
    if cached:
        return cached

    if offline:
        raise FileNotFoundError(
            "Runtime browser+driver tidak tersedia di cache "
            "dan mode offline aktif. "
            "Nonaktifkan --offline atau sediakan browser/driver manual."
        )

    platform_key, _, _ = cft_platform_layout()
    with urllib.request.urlopen(CFT_LKG_URL, timeout=30) as response:
        payload = json.loads(response.read().decode("utf-8"))

    stable_channel = payload.get("channels", {}).get("Stable", {})
    downloads = stable_channel.get("downloads", {})
    version = stable_channel.get("version", "unknown")

    def pick_url(items: list[dict]) -> str:
        for item in items:
            if item.get("platform") == platform_key:
                return str(item.get("url", ""))
        return ""

    chrome_url = pick_url(downloads.get("chrome", []))
    driver_url = pick_url(downloads.get("chromedriver", []))
    if not chrome_url or not driver_url:
        raise RuntimeError(
            "Tidak menemukan URL download Chrome for Testing "
            f"untuk platform {platform_key}."
        )

    cft_root = runtime_dir / "cft"
    if cft_root.exists():
        shutil.rmtree(cft_root)
    cft_root.mkdir(parents=True, exist_ok=True)

    LOGGER.info(
        "runtime.bootstrap_download version=%s platform=%s",
        version,
        platform_key,
    )
    download_zip_and_extract(chrome_url, cft_root)
    download_zip_and_extract(driver_url, cft_root)

    cached = find_cached_cft_runtime(runtime_dir)
    if not cached:
        raise RuntimeError(
            "Runtime berhasil diunduh, "
            "tetapi file browser/driver tidak ditemukan."
        )

    browser_path, driver_path = cached
    mark_executable(browser_path)
    mark_executable(driver_path)
    return browser_path, driver_path


def create_bootstrapped_driver(
    *,
    headless: bool,
    disable_images: bool,
    enable_perf_logs: bool,
    user_data_dir: Path | None,
    browser_path_override: str,
    driver_path_override: str,
    runtime_dir: Path,
    offline: bool,
    script_timeout_seconds: int = 240,
) -> webdriver.Chrome:
    explicit_browser = resolve_existing_path(
        browser_path_override, "Browser path"
    )
    explicit_driver = resolve_existing_path(
        driver_path_override, "Driver path"
    )
    if explicit_browser or explicit_driver:
        LOGGER.info("driver.strategy mode=explicit_override")
        return build_driver(
            headless=headless,
            disable_images=disable_images,
            enable_perf_logs=enable_perf_logs,
            user_data_dir=user_data_dir,
            browser_path=explicit_browser,
            driver_path=explicit_driver,
            script_timeout_seconds=script_timeout_seconds,
        )

    system_browser = detect_system_browser_path()
    bundled_driver = detect_bundled_driver_path()
    attempts: list[tuple[str, Path | None, Path | None]] = []
    if system_browser and bundled_driver:
        attempts.append(
            (
                "system browser + bundled chromedriver",
                system_browser,
                bundled_driver,
            )
        )
    if bundled_driver:
        attempts.append(("bundled chromedriver", None, bundled_driver))
    if system_browser:
        attempts.append(
            ("system browser + selenium manager", system_browser, None)
        )
    attempts.append(("selenium manager auto", None, None))

    errors: list[str] = []
    for strategy, browser_path, driver_path in attempts:
        try:
            driver = build_driver(
                headless=headless,
                disable_images=disable_images,
                enable_perf_logs=enable_perf_logs,
                user_data_dir=user_data_dir,
                browser_path=browser_path,
                driver_path=driver_path,
                script_timeout_seconds=script_timeout_seconds,
            )
            LOGGER.info("driver.strategy mode=%s", strategy)
            return driver
        except Exception as error:
            errors.append(f"{strategy}: {error}")

    try:
        browser_path, driver_path = ensure_cft_runtime(runtime_dir, offline)
        driver = build_driver(
            headless=headless,
            disable_images=disable_images,
            enable_perf_logs=enable_perf_logs,
            user_data_dir=user_data_dir,
            browser_path=browser_path,
            driver_path=driver_path,
            script_timeout_seconds=script_timeout_seconds,
        )
        LOGGER.info("driver.strategy mode=cached_or_downloaded_cft_runtime")
        return driver
    except Exception as error:
        errors.append(f"chrome-for-testing runtime: {error}")

    joined_errors = "\n- ".join(errors)
    raise RuntimeError(
        "Gagal menyiapkan browser untuk Selenium.\n"
        f"- {joined_errors}\n"
        "Kamu bisa tetap override manual "
        "dengan --browser-path dan --driver-path."
    )
