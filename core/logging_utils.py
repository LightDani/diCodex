from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Iterator

LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


def configure_logging(level: str = "INFO") -> None:
    normalized_level = (level or "INFO").upper()
    numeric_level = getattr(logging, normalized_level, logging.INFO)
    logging.basicConfig(
        level=numeric_level,
        format=LOG_FORMAT,
        datefmt=DATE_FORMAT,
        force=True,
    )


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


@contextmanager
def timed_operation(
    logger: logging.Logger,
    operation: str,
) -> Iterator[None]:
    started_at = time.perf_counter()
    logger.info("operation.start name=%s", operation)
    try:
        yield
    finally:
        elapsed = time.perf_counter() - started_at
        logger.info(
            "operation.done name=%s duration_sec=%.3f",
            operation,
            elapsed,
        )
