from __future__ import annotations

import json
from types import ModuleType
from typing import Any

orjson: ModuleType | None
try:
    import orjson as _orjson
    orjson = _orjson
except ImportError:  # pragma: no cover - fallback when dependency is unavailable
    orjson = None


def json_dumps(value: Any, *, pretty: bool = False) -> str:
    if orjson is not None:
        option = orjson.OPT_SORT_KEYS | (orjson.OPT_INDENT_2 if pretty else 0)
        return orjson.dumps(value, option=option).decode("utf-8")
    if pretty:
        return json.dumps(value, indent=2, sort_keys=True)
    return json.dumps(value, separators=(",", ":"), sort_keys=True)


def json_loads(value: str | bytes | bytearray) -> Any:
    if orjson is not None:
        return orjson.loads(value)
    return json.loads(value)
