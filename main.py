# ruff: noqa: E501, W505

from pathlib import Path

from asah_capture import capture_asah_live_attendance_reference
from browser_runtime import DEFAULT_RUNTIME_DIR
from cli import parse_args
from codingcamp_capture import run_codingcamp_export
from settings import (
    ASAH_URL,
    ASYNC_SCRIPT_TIMEOUT_SECONDS,
    CODINGCAMP_URL,
    DEFAULT_MANUAL_LOGIN_TIMEOUT_SECONDS,
    FAST_PAGINATION_DELAY_MS,
    INTERACTION_TIMEOUT_SECONDS,
    MAX_PAGINATION_STEPS,
    OUTPUT_DIR,
    load_credentials,
)


def main() -> None:
    email, password = load_credentials()

    args = parse_args(
        default_email=email,
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
        email=email,
        password=password,
        codingcamp_url=CODINGCAMP_URL,
        output_dir=OUTPUT_DIR,
        interaction_timeout_seconds=INTERACTION_TIMEOUT_SECONDS,
        async_script_timeout_seconds=ASYNC_SCRIPT_TIMEOUT_SECONDS,
        fast_pagination_delay_ms=FAST_PAGINATION_DELAY_MS,
        max_pagination_steps=MAX_PAGINATION_STEPS,
    )


if __name__ == "__main__":
    main()
