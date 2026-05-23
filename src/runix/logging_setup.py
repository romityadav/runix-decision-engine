"""Centralised logging configuration.

We use the standard library ``logging`` (never ``print``) so that every layer of
the pipeline can emit levelled, timestamped diagnostics that the CLI, the tests,
and the dashboard can all route however they like. Data-quality findings in
particular are logged at WARNING so they are impossible to miss but never fatal.
"""

from __future__ import annotations

import logging

_CONFIGURED = False


def configure_logging(verbose: bool = False) -> None:
    """Configure root logging once, idempotently.

    Args:
        verbose: If True, emit DEBUG-level records; otherwise INFO and above.
    """
    global _CONFIGURED
    level = logging.DEBUG if verbose else logging.INFO
    if _CONFIGURED:
        logging.getLogger().setLevel(level)
        return
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )
    _CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    """Return a module logger (namespaced under ``runix``)."""
    return logging.getLogger(name)
