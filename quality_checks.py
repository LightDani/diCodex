from __future__ import annotations

import argparse
import csv
from pathlib import Path

from core.csv_pipeline import CSV_EXPORT_CONFIG


def expected_csv_schema() -> dict[str, list[str]]:
    return {filename: columns for filename, _, columns in CSV_EXPORT_CONFIG}


def count_rows(path: Path) -> int:
    with path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        next(reader, None)  # header
        return sum(1 for _ in reader)


def read_header(path: Path) -> list[str]:
    with path.open("r", newline="", encoding="utf-8") as file:
        reader = csv.reader(file)
        header = next(reader, [])
    return [str(value) for value in header]


def validate_csv_outputs(
    output_dir: Path,
    *,
    required_non_empty: set[str] | None = None,
) -> tuple[list[str], dict[str, int]]:
    expected = expected_csv_schema()
    errors: list[str] = []
    row_counts: dict[str, int] = {}
    required_non_empty = required_non_empty or set()

    for filename, expected_columns in expected.items():
        path = output_dir / filename
        if not path.exists():
            errors.append(f"Missing file: {path}")
            continue

        header = read_header(path)
        if header != expected_columns:
            errors.append(
                f"Invalid header {filename}. "
                f"Expected={expected_columns}, got={header}"
            )
            continue

        rows = count_rows(path)
        row_counts[filename] = rows
        if filename in required_non_empty and rows <= 0:
            errors.append(
                f"File {filename} harus berisi minimal 1 baris data."
            )

    return errors, row_counts


def parse_required_non_empty(raw_value: str) -> set[str]:
    return {
        item.strip() for item in (raw_value or "").split(",") if item.strip()
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validasi schema output CSV hasil scraping."
    )
    parser.add_argument(
        "--output-dir",
        default="output",
        help="Direktori output CSV.",
    )
    parser.add_argument(
        "--require-non-empty",
        default="mentor_data.csv,student.csv",
        help=(
            "Daftar file CSV (pisahkan koma) yang wajib punya minimal "
            "1 baris data."
        ),
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = Path(args.output_dir)
    required_non_empty = parse_required_non_empty(args.require_non_empty)

    errors, row_counts = validate_csv_outputs(
        output_dir, required_non_empty=required_non_empty
    )
    if errors:
        print("CSV schema validation: FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("CSV schema validation: OK")
    for filename in sorted(row_counts.keys()):
        print(f"- {filename}: {row_counts[filename]} baris")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
