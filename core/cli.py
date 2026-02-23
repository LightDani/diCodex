from __future__ import annotations

import argparse
from pathlib import Path


def parse_args(
    *,
    default_email: str,
    default_runtime_dir: Path,
    default_manual_login_timeout_seconds: int = 600,
) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export data CodingCamp/ASAH."
    )
    parser.set_defaults(experimental_fast_daily=True)
    parser.add_argument(
        "--source",
        choices=["codingcamp", "asah"],
        default="codingcamp",
        help=(
            "Pilih sumber data. "
            "'asah' dipakai untuk capture referensi struktur live."
        ),
    )
    parser.add_argument(
        "--pipeline-mode",
        choices=["scrape-transform", "scrape", "transform"],
        default="scrape-transform",
        help=(
            "Mode pipeline untuk source codingcamp: "
            "scrape-transform (default), scrape, atau transform."
        ),
    )
    parser.add_argument(
        "--asah-email",
        default=default_email,
        help="Email untuk request magic link saat mode --source asah.",
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Jalankan browser dengan UI (non-headless).",
    )
    parser.add_argument(
        "--auth-mode",
        choices=["hybrid", "auto", "manual"],
        default="hybrid",
        help=(
            "Mode autentikasi CodingCamp: "
            "hybrid (auto jika secret ada, fallback manual), "
            "auto (paksa auto lalu fallback manual), "
            "manual (langsung login manual)."
        ),
    )
    parser.add_argument(
        "--profile-dir",
        default=".selenium_profile/codingcamp",
        help=(
            "Folder Chrome profile persisten untuk menyimpan sesi login "
            "antar-run."
        ),
    )
    parser.add_argument(
        "--manual-login-timeout",
        type=int,
        default=default_manual_login_timeout_seconds,
        help="Batas tunggu (detik) untuk proses login manual.",
    )
    parser.add_argument(
        "--browser-path",
        default="",
        help="Path browser Chrome/Chromium custom (opsional, advanced).",
    )
    parser.add_argument(
        "--driver-path",
        default="",
        help="Path chromedriver custom (opsional, advanced).",
    )
    parser.add_argument(
        "--runtime-dir",
        default=str(default_runtime_dir),
        help=(
            "Folder cache runtime browser+driver otomatis "
            "(dipakai bila environment belum siap)."
        ),
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help=(
            "Jangan download runtime otomatis dari internet. "
            "Jika browser/driver tidak tersedia, proses akan gagal."
        ),
    )
    parser.add_argument(
        "--load-images",
        action="store_true",
        help="Muat gambar normal. Default: gambar diblokir untuk speed.",
    )
    parser.add_argument(
        "--enable-perf-logs",
        action="store_true",
        help="Aktifkan performance logs Chrome (khusus debug/inspeksi).",
    )
    parser.add_argument(
        "--experimental-fast-daily",
        action="store_true",
        help="Pakai mode daily-checkins super cepat (default aktif).",
    )
    parser.add_argument(
        "--no-fast-daily",
        dest="experimental_fast_daily",
        action="store_false",
        help="Nonaktifkan mode cepat daily-checkins dan pakai mode aman.",
    )
    parser.add_argument(
        "--output-format",
        choices=["csv", "json", "both"],
        default="csv",
        help=(
            "Format output untuk mode codingcamp: "
            "csv (default), json, atau both."
        ),
    )
    parser.add_argument(
        "--transform-source",
        type=Path,
        default=None,
        help=(
            "Path JSON sumber saat --pipeline-mode transform. "
            "Jika kosong, dipilih otomatis dari output/."
        ),
    )
    parser.add_argument(
        "--transform-group",
        default="",
        help=(
            "Group untuk memilih file default saat transform "
            "(contoh CDC-04 -> codingcamp_CDC-04_full.json)."
        ),
    )
    return parser.parse_args()
