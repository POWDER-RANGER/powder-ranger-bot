# ============================================================
# utils/logger.py — rotating colour logger
# ============================================================

from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

import colorlog


def setup_logger(
    name:         str,
    level:        str = "INFO",
    log_file:     str = "logs/bot.log",
    max_bytes:    int = 5_242_880,
    backup_count: int = 3,
) -> logging.Logger:
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Console handler — colour
    ch = colorlog.StreamHandler()
    ch.setFormatter(colorlog.ColoredFormatter(
        "%(log_color)s%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    ))
    logger.addHandler(ch)

    # File handler — rotating
    os.makedirs(os.path.dirname(log_file), exist_ok=True)
    fh = RotatingFileHandler(log_file, maxBytes=max_bytes, backupCount=backup_count)
    fh.setFormatter(logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
    ))
    logger.addHandler(fh)

    return logger
