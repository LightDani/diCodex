from __future__ import annotations

import json
import re
from pathlib import Path


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
