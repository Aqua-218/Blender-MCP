from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass, field
from typing import Any


def _require_mapping(value: object, *, field_name: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError(f"{field_name} must be a mapping")
    return value


def _require_str(data: Mapping[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str):
        raise ValueError(f"{key} must be a string")
    return value


def _require_bool(data: Mapping[str, Any], key: str, *, default: bool = False) -> bool:
    value = data.get(key, default)
    if not isinstance(value, bool):
        raise ValueError(f"{key} must be a boolean")
    return value


def _require_float(data: Mapping[str, Any], key: str) -> float:
    value = data.get(key)
    if not isinstance(value, (int, float)):
        raise ValueError(f"{key} must be numeric")
    return float(value)


def _require_dict(data: Mapping[str, Any], key: str) -> dict[str, Any]:
    value = data.get(key, {})
    return dict(_require_mapping(value, field_name=key))


def _validate_message_type(data: Mapping[str, Any], expected: str) -> None:
    actual = data.get("message_type")
    if actual != expected:
        raise ValueError(f"message_type must be {expected}")


@dataclass(slots=True)
class BridgeEnvelope:
    message_type: str = field(init=False, default="")

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class BridgeRequest(BridgeEnvelope):
    request_id: str
    command: str
    auth_token: str
    payload: dict[str, Any] = field(default_factory=dict)
    read_only: bool = False
    message_type: str = field(init=False, default="request")

    @classmethod
    def model_validate(cls, value: object) -> BridgeRequest:
        data = _require_mapping(value, field_name="BridgeRequest")
        _validate_message_type(data, "request")
        return cls(
            request_id=_require_str(data, "request_id"),
            command=_require_str(data, "command"),
            auth_token=_require_str(data, "auth_token"),
            payload=_require_dict(data, "payload"),
            read_only=_require_bool(data, "read_only", default=False),
        )


@dataclass(slots=True)
class BridgeProgress(BridgeEnvelope):
    request_id: str
    command: str
    progress: float
    message: str
    message_type: str = field(init=False, default="progress")

    @classmethod
    def model_validate(cls, value: object) -> BridgeProgress:
        data = _require_mapping(value, field_name="BridgeProgress")
        _validate_message_type(data, "progress")
        return cls(
            request_id=_require_str(data, "request_id"),
            command=_require_str(data, "command"),
            progress=_require_float(data, "progress"),
            message=_require_str(data, "message"),
        )


@dataclass(slots=True)
class BridgeResult(BridgeEnvelope):
    request_id: str
    command: str
    payload: dict[str, Any] = field(default_factory=dict)
    message_type: str = field(init=False, default="result")

    @classmethod
    def model_validate(cls, value: object) -> BridgeResult:
        data = _require_mapping(value, field_name="BridgeResult")
        _validate_message_type(data, "result")
        return cls(
            request_id=_require_str(data, "request_id"),
            command=_require_str(data, "command"),
            payload=_require_dict(data, "payload"),
        )


@dataclass(slots=True)
class BridgeError(BridgeEnvelope):
    request_id: str
    command: str
    error_code: str
    message: str
    details: dict[str, Any] = field(default_factory=dict)
    message_type: str = field(init=False, default="error")

    @classmethod
    def model_validate(cls, value: object) -> BridgeError:
        data = _require_mapping(value, field_name="BridgeError")
        _validate_message_type(data, "error")
        return cls(
            request_id=_require_str(data, "request_id"),
            command=_require_str(data, "command"),
            error_code=_require_str(data, "error_code"),
            message=_require_str(data, "message"),
            details=_require_dict(data, "details"),
        )


@dataclass(slots=True)
class BridgeHeartbeat(BridgeEnvelope):
    request_id: str
    command: str
    timestamp: str
    message_type: str = field(init=False, default="heartbeat")

    @classmethod
    def model_validate(cls, value: object) -> BridgeHeartbeat:
        data = _require_mapping(value, field_name="BridgeHeartbeat")
        _validate_message_type(data, "heartbeat")
        return cls(
            request_id=_require_str(data, "request_id"),
            command=_require_str(data, "command"),
            timestamp=_require_str(data, "timestamp"),
        )


@dataclass(slots=True)
class BridgeCancel(BridgeEnvelope):
    request_id: str
    auth_token: str
    message_type: str = field(init=False, default="cancel")

    @classmethod
    def model_validate(cls, value: object) -> BridgeCancel:
        data = _require_mapping(value, field_name="BridgeCancel")
        _validate_message_type(data, "cancel")
        return cls(
            request_id=_require_str(data, "request_id"),
            auth_token=_require_str(data, "auth_token"),
        )
