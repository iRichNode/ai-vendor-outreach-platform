"""Structured JSON logging to stderr/stdout (12-factor style).

Secrets are never logged: helper `redact` scrubs common secret field names.
"""
from __future__ import annotations

import json
import logging
import sys
from typing import Any

_SENSITIVE_FIELDS = {
    "password",
    "token",
    "access_token",
    "refresh_token",
    "authorization",
    "cookie",
    "secret",
    "api_key",
    "client_secret",
}

RESERVED = object()


def redact(data: Any) -> Any:
    """Recursively scrub values whose key looks like a secret."""
    if isinstance(data, dict):
        return {k: "[REDACTED]" if k.lower() in _SENSITIVE_FIELDS else redact(v) for k, v in data.items()}
    if isinstance(data, (list, tuple)):
        return [redact(v) for v in data]
    return data


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        entry: dict[str, Any] = {
            "ts": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        for key in ("event", "job_id", "vendor_id", "campaign_id", "conversation_id", "user", "action"):
            value = getattr(record, key, None)
            if value is not None:
                entry[key] = value
        if record.exc_info:
            entry["exc"] = self.formatException(record.exc_info)
        extra = getattr(record, "extra_fields", None)
        if extra:
            entry["data"] = redact(extra)
        return json.dumps(entry, default=str)


def setup_logging(level: str = "INFO") -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers = [handler]
    root.setLevel(level.upper())


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)