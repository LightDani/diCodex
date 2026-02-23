from __future__ import annotations

import argparse
from pathlib import Path

from csv_pipeline import (
    export_tables_to_csv,
    load_json_payload,
    resolve_default_json_source,
    transform_payload_to_tables,
)

OUTPUT_DIR = Path("output")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Transform JSON CodingCamp menjadi beberapa tabel CSV."
    )
    parser.add_argument(
        "--source",
        type=Path,
        help="Path JSON sumber. Jika diisi, ini diprioritaskan.",
    )
    parser.add_argument(
        "--group",
        type=str,
        default="",
        help=(
            "ID group untuk memilih file default "
            "(contoh: CDC-04 -> codingcamp_CDC-04_full.json)."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=OUTPUT_DIR,
        help="Folder output CSV (default: output).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    output_dir = args.output_dir
    source_path = args.source or resolve_default_json_source(
        output_dir, args.group
    )

    payload = load_json_payload(source_path)
    tables = transform_payload_to_tables(payload)
    row_count_by_file = export_tables_to_csv(tables, output_dir)

    print(f"Sumber JSON: {source_path}")
    for filename, count in row_count_by_file.items():
        print(f"- {filename}: {count} baris data")


if __name__ == "__main__":
    main()
