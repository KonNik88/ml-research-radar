from __future__ import annotations

import logging
from typing import Final

from services.api.settings import get_settings

_LOG_FORMAT: Final[str] = (
    "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
)


def configure_logging() -> None:
    settings = get_settings()
    level_name = settings.log_level.upper()
    level = getattr(logging, level_name, logging.INFO)

    root_logger = logging.getLogger()
    if not root_logger.handlers:
        logging.basicConfig(level=level, format=_LOG_FORMAT)
    else:
        root_logger.setLevel(level)
        for handler in root_logger.handlers:
            handler.setLevel(level)


def get_logger(name: str) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name)