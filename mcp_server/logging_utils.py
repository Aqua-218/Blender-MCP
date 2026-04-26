from __future__ import annotations

import json
import logging
import re
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from types import ModuleType
from typing import Any

orjson: ModuleType | None
try:
    import orjson as _orjson
    orjson = _orjson
except ImportError:  # pragma: no cover - fallback when dependency is unavailable
    orjson = None


_REDACT_KEYS = re.compile(r"(secret|token|authorization)", re.IGNORECASE)
_LOG_FIELDS = {
    "request_id",
    "project_id",
    "tool_name",
    "family",
    "status",
    "duration_ms",
    "warnings_count",
    "errors_count",
    "error_code",
    "transport",
    "origin",
    "role",
    "authenticated",
    "client_host",
    "auth_fingerprint",
}


def _serialize(payload: Mapping[str, Any]) -> str:
    if orjson is not None:
        return orjson.dumps(payload).decode("utf-8")
    return json.dumps(payload, sort_keys=True)


def redact_sensitive(payload: Any) -> Any:
    if isinstance(payload, Mapping):
        return {
            key: ("***REDACTED***" if _REDACT_KEYS.search(key) else redact_sensitive(value))
            for key, value in payload.items()
        }
    if isinstance(payload, list):
        return [redact_sensitive(item) for item in payload]
    if isinstance(payload, tuple):
        return tuple(redact_sensitive(item) for item in payload)
    return payload


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        base = {
            "timestamp": datetime.now(tz=UTC).isoformat(),
            "logger": record.name,
            "level": record.levelname,
            "message": record.getMessage(),
        }
        extras = {
            key: value
            for key, value in record.__dict__.items()
            if key in _LOG_FIELDS and value is not None
        }
        if extras:
            base.update(redact_sensitive(extras))
        if record.exc_info:
            base["exception"] = self.formatException(record.exc_info)
        return _serialize(base)


def setup_structured_logger(name: str, level: str = "INFO") -> logging.Logger:
    logger = logging.getLogger(name)
    logger.setLevel(level.upper())
    if logger.handlers:
        return logger
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(JsonFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger
