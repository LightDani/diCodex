from __future__ import annotations

from logging import Logger
from pathlib import Path
from typing import Any

from .csv_pipeline import (
    export_tables_to_csv,
    load_json_payload,
    resolve_default_json_source,
    transform_payload_to_tables,
)
from .logging_utils import get_logger, timed_operation

LOGGER: Logger = get_logger(__name__)


def run_transform_job(
    *,
    output_dir: Path,
    source_path: Path | None = None,
    group: str = "",
) -> dict[str, Any]:
    with timed_operation(LOGGER, "transform_resolve_source"):
        resolved_source = source_path or resolve_default_json_source(
            output_dir, group
        )
    LOGGER.info("transform.source path=%s", resolved_source)

    with timed_operation(LOGGER, "transform_load_payload"):
        payload = load_json_payload(resolved_source)
    with timed_operation(LOGGER, "transform_build_tables"):
        tables = transform_payload_to_tables(payload)
    with timed_operation(LOGGER, "transform_export_csv"):
        row_count_by_file = export_tables_to_csv(tables, output_dir)

    LOGGER.info("transform.summary.start")
    for filename, count in row_count_by_file.items():
        LOGGER.info("transform.file file=%s rows=%s", filename, count)

    return {
        "source_path": str(resolved_source),
        "row_count_by_file": row_count_by_file,
    }
