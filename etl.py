from __future__ import annotations

import argparse
from pathlib import Path

from core.logging_utils import configure_logging
from core.transform_runner import run_transform_job

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
    parser.add_argument(
        "--log-level",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Level logging ETL (default: INFO).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    configure_logging(args.log_level)
    run_transform_job(
        output_dir=args.output_dir,
        source_path=args.source,
        group=args.group,
    )


if __name__ == "__main__":
    main()
