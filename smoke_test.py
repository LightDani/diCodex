from __future__ import annotations

import argparse
import sys
from pathlib import Path

from core.app import run
from quality_checks import parse_required_non_empty, validate_csv_outputs


def parse_args() -> tuple[argparse.Namespace, list[str]]:
    parser = argparse.ArgumentParser(
        description=(
            "Smoke test end-to-end: jalankan scraping CSV lalu validasi "
            "schema output."
        )
    )
    parser.add_argument(
        "--skip-run",
        action="store_true",
        help="Lewati eksekusi main.py, hanya validasi output yang ada.",
    )
    parser.add_argument(
        "--main-script",
        default="main.py",
        help="Path script utama (dipakai pada mode subprocess).",
    )
    parser.add_argument(
        "--run-mode",
        choices=["inprocess", "subprocess"],
        default="inprocess",
        help=(
            "Cara menjalankan smoke run. 'inprocess' lebih stabil di sandbox."
        ),
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
    return parser.parse_known_args()


def ensure_output_format_csv(args: list[str]) -> list[str]:
    if "--output-format" in args:
        return args
    return [*args, "--output-format", "csv"]


def run_main_inprocess(main_script: str, forwarded_args: list[str]) -> int:
    effective_args = ensure_output_format_csv(forwarded_args)
    argv = [main_script, *effective_args]
    print("Menjalankan smoke command (inprocess):")
    print(f"- {' '.join(argv)}")

    previous_argv = sys.argv[:]
    try:
        sys.argv = argv
        run()
        return 0
    except SystemExit as error:
        code = error.code if isinstance(error.code, int) else 1
        return int(code)
    finally:
        sys.argv = previous_argv


def run_main_subprocess(main_script: str, forwarded_args: list[str]) -> int:
    import subprocess

    command = [
        sys.executable,
        main_script,
        *ensure_output_format_csv(forwarded_args),
    ]
    print("Menjalankan smoke command (subprocess):")
    print(f"- {' '.join(command)}")
    completed = subprocess.run(command, check=False)
    return int(completed.returncode)


def main() -> int:
    args, forwarded_args = parse_args()

    if not args.skip_run:
        if args.run_mode == "subprocess":
            exit_code = run_main_subprocess(args.main_script, forwarded_args)
        else:
            exit_code = run_main_inprocess(args.main_script, forwarded_args)
        if exit_code != 0:
            print(f"Smoke run FAILED. Exit code: {exit_code}")
            return exit_code

    output_dir = Path(args.output_dir)
    required_non_empty = parse_required_non_empty(args.require_non_empty)
    errors, row_counts = validate_csv_outputs(
        output_dir, required_non_empty=required_non_empty
    )
    if errors:
        print("Smoke validation FAILED")
        for error in errors:
            print(f"- {error}")
        return 1

    print("Smoke validation OK")
    for filename in sorted(row_counts.keys()):
        print(f"- {filename}: {row_counts[filename]} baris")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
