from __future__ import annotations

from pathlib import Path

CODINGCAMP_URL = "https://codingcamp.dicoding.com"
ASAH_URL = "https://asah.dicoding.com"
OUTPUT_DIR = Path("output")
MAX_PAGINATION_STEPS = 300
INTERACTION_TIMEOUT_SECONDS = 20
ASYNC_SCRIPT_TIMEOUT_SECONDS = 240
FAST_PAGINATION_DELAY_MS = 120
DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS = 600


def load_credentials() -> tuple[str, str]:
    try:
        from secret import EMAIL, PASSWORD
    except ImportError:
        return "", ""
    return str(EMAIL or ""), str(PASSWORD or "")
