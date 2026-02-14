# backend-python/infra/logging/setup.py
from __future__ import annotations

import logging


def setup_logging(level: str) -> None:
    root = logging.getLogger()
    root.setLevel(level)

    if root.handlers:
        return

    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
