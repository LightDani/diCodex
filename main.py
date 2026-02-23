# ruff: noqa: E501, W505

from pathlib import Path

from asah_capture import capture_asah_live_attendance_reference
from browser_runtime import DEFAULT_RUNTIME_DIR
from cli import parse_args
from codingcamp_capture import run_codingcamp_export

CODINGCAMP_URL = "https://codingcamp.dicoding.com"
ASAH_URL = "https://asah.dicoding.com"
OUTPUT_DIR = Path("output")
MAX_PAGINATION_STEPS = 300
INTERACTION_TIMEOUT_SECONDS = 20
ASYNC_SCRIPT_TIMEOUT_SECONDS = 240
FAST_PAGINATION_DELAY_MS = 120
DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS = 600

try:
    from secret import EMAIL, PASSWORD
except ImportError:
    EMAIL = ""
    PASSWORD = ""


def main() -> None:
    args = parse_args(
        default_email=EMAIL,
        default_runtime_dir=DEFAULT_RUNTIME_DIR,
        default_manual_login_timeout_seconds=DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS,
    )

    if args.source == "asah":
        out_path = capture_asah_live_attendance_reference(
            args.asah_email,
            asah_url=ASAH_URL,
            output_dir=OUTPUT_DIR,
            browser_path_override=args.browser_path,
            driver_path_override=args.driver_path,
            runtime_dir=Path(args.runtime_dir).expanduser(),
            offline=args.offline,
            enable_perf_logs=args.enable_perf_logs,
            interaction_timeout_seconds=INTERACTION_TIMEOUT_SECONDS,
            script_timeout_seconds=ASYNC_SCRIPT_TIMEOUT_SECONDS,
        )
        print(f"ASAH attendance reference: {out_path}")
        return

    run_codingcamp_export(
        args,
        email=EMAIL,
        password=PASSWORD,
        codingcamp_url=CODINGCAMP_URL,
        output_dir=OUTPUT_DIR,
        interaction_timeout_seconds=INTERACTION_TIMEOUT_SECONDS,
        async_script_timeout_seconds=ASYNC_SCRIPT_TIMEOUT_SECONDS,
        fast_pagination_delay_ms=FAST_PAGINATION_DELAY_MS,
        max_pagination_steps=MAX_PAGINATION_STEPS,
    )


if __name__ == "__main__":
    main()
