from __future__ import annotations

from pathlib import Path
from typing import Any

from .csv_pipeline import (
    export_tables_to_csv,
    load_json_payload,
    resolve_default_json_source,
    transform_payload_to_tables,
)


def run_transform_job(
    *,
    output_dir: Path,
    source_path: Path | None = None,
    group: str = "",
) -> dict[str, Any]:
    resolved_source = source_path or resolve_default_json_source(
        output_dir, group
    )
    payload = load_json_payload(resolved_source)
    tables = transform_payload_to_tables(payload)
    row_count_by_file = export_tables_to_csv(tables, output_dir)

    print(f"Sumber JSON: {resolved_source}")
    for filename, count in row_count_by_file.items():
        print(f"- {filename}: {count} baris data")

    return {
        "source_path": str(resolved_source),
        "row_count_by_file": row_count_by_file,
    }
