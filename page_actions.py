# ruff: noqa: E501

from __future__ import annotations

import time

from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait

from selenium_ui import click_element, find_first_visible, wait_for_page_ready


def click_from_locators(
    driver: webdriver.Chrome,
    locators: list[tuple[str, str]],
    action_label: str,
    *,
    interaction_timeout_seconds: int = 20,
) -> None:
    deadline = time.time() + interaction_timeout_seconds
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

    message = (
        f"Gagal klik '{action_label}'. "
        "Elemen tidak ditemukan atau tidak bisa diklik."
    )
    if last_error:
        raise NoSuchElementException(
            f"{message} Detail: {last_error}"
        ) from last_error
    raise NoSuchElementException(message)


def expand_all_student_data(
    driver: webdriver.Chrome, *, interaction_timeout_seconds: int = 20
) -> None:
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
        driver,
        student_input_locators,
        "Input student's name or ID",
        interaction_timeout_seconds=interaction_timeout_seconds,
    )
    click_from_locators(
        driver,
        select_all_locators,
        "Select All",
        interaction_timeout_seconds=interaction_timeout_seconds,
    )
    click_from_locators(
        driver,
        expand_all_locators,
        "Expand All",
        interaction_timeout_seconds=interaction_timeout_seconds,
    )
    WebDriverWait(driver, interaction_timeout_seconds).until(
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
    driver: webdriver.Chrome,
    wait: WebDriverWait,
    email: str,
    *,
    asah_url: str,
    interaction_timeout_seconds: int = 20,
) -> None:
    if not email:
        raise ValueError(
            "Email untuk Asah kosong. Isi secret.py atau kirim --asah-email."
        )

    driver.get(f"{asah_url}/login")
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
    click_from_locators(
        driver,
        send_magic_locators,
        "Send Magic Link",
        interaction_timeout_seconds=interaction_timeout_seconds,
    )


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
