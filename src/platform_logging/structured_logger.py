"""Created: 2026-03-31

Purpose: Implements the structured logger module for the shared platform logging platform layer.
"""

from __future__ import annotations

import logging as std_logging


def StructuredLogger(name: str = "platform") -> std_logging.Logger:
    logger = std_logging.getLogger(name)
    if not logger.handlers:
        handler = std_logging.StreamHandler()
        formatter = std_logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)
    logger.setLevel(std_logging.INFO)
    return logger

