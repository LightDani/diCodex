from __future__ import annotations

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as ec
from selenium.webdriver.support.ui import WebDriverWait


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
