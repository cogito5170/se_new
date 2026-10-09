"""Logging with secret redaction.

A filter on the root magref logger rewrites every record's final message:
values of credential-like query parameters, `Authorization`/`Cookie` headers,
bearer tokens, `key=...`-style pairs and the user's home directory are masked.
"""
from __future__ import annotations

import logging
import os
import re
from pathlib import Path

_PATTERNS = [
    (re.compile(r"(?i)\b(authorization|cookie|set-cookie|x-api-key)\s*[:=]\s*[^\s,;]+(\s+[^\s,;]+)?"),
     r"\1: [REDACTED]"),
    (re.compile(r"(?i)\bbearer\s+[A-Za-z0-9._~+/=-]+"), "Bearer [REDACTED]"),
    (re.compile(r"(?i)([?&;\s](?:[a-z0-9_]*?(?:key|token|secret|sig|signature|password|passwd|auth|"
                r"session|sid)[a-z0-9_]*)=)[^&\s\"']+"), r"\1[REDACTED]"),
    (re.compile(r"(?i)\b((?:api[_-]?key|access[_-]?token|secret|password)\s*[:=]\s*)[^\s,;&\"']+"),
     r"\1[REDACTED]"),
]


def redact(text: str) -> str:
    for rx, repl in _PATTERNS:
        text = rx.sub(repl, text)
    home = str(Path.home())
    if home and home not in ("/", "") and len(home) > 1:
        text = text.replace(home, "~")
    return text


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # noqa: BLE001 -- never let logging crash the program
            return True
        record.msg = redact(message)
        record.args = ()
        return True


def setup_logging(level: str = "INFO", log_file: Path | None = None) -> None:
    logger = logging.getLogger("magref")
    logger.setLevel(level)
    for h in list(logger.handlers):
        logger.removeHandler(h)
    fmt = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if log_file is not None:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))
    for h in handlers:
        h.setFormatter(fmt)
        h.addFilter(RedactingFilter())
        logger.addHandler(h)
    logger.propagate = False
    if os.environ.get("MAGREF_LOG_QUIET"):
        logger.setLevel("WARNING")
