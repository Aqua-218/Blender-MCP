from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, cast

ControllerBackend = Literal["mock", "blender"]

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_REPO_MARKERS = ("pyproject.toml", "alembic.ini")


def _discover_repo_root(base_dir: Path | None, env_repo_root: str | None) -> Path:
    candidates: list[Path] = []
    if env_repo_root:
        candidates.append(Path(env_repo_root).resolve())
    if base_dir is not None:
        resolved_base = base_dir.resolve()
        candidates.extend([resolved_base, *resolved_base.parents])
    module_root = Path(__file__).resolve().parent.parent
    candidates.extend([module_root, *module_root.parents])
    seen: set[Path] = set()
    for candidate in candidates:
        if candidate in seen:
            continue
        seen.add(candidate)
        if all((candidate / marker).exists() for marker in _REPO_MARKERS):
            return candidate
    if env_repo_root:
        return Path(env_repo_root).resolve()
    return module_root


def _require_mapping(value: object) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("ControllerSettings payload must be a mapping")
    return value


def _parse_port(value: object) -> int:
    try:
        port = int(cast(Any, value))
    except (TypeError, ValueError) as exc:
        raise ValueError("Controller port must be an integer") from exc
    if port <= 0:
        raise ValueError("Controller port must be positive")
    return port


def _parse_heartbeat(value: object) -> float:
    try:
        heartbeat = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("Controller heartbeat interval must be numeric") from exc
    if heartbeat <= 0:
        raise ValueError("Controller heartbeat interval must be positive")
    return heartbeat


@dataclass(slots=True)
class ControllerSettings:
    host: str
    port: int
    shared_secret: str
    heartbeat_seconds: float
    log_level: str
    backend: ControllerBackend
    repo_root: Path
    blender_binary: Path | None = None

    def __post_init__(self) -> None:
        self.repo_root = Path(self.repo_root).resolve()
        if self.blender_binary is not None:
            self.blender_binary = Path(self.blender_binary).resolve()
        if self.host.strip().lower() not in _LOOPBACK_HOSTS:
            raise ValueError("Controller host must be a loopback address")
        if self.backend not in {"mock", "blender"}:
            raise ValueError("Controller backend must be 'mock' or 'blender'")
        self.port = _parse_port(self.port)
        self.heartbeat_seconds = _parse_heartbeat(self.heartbeat_seconds)

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def model_validate(cls, value: object) -> ControllerSettings:
        data = _require_mapping(value)
        shared_secret = data.get("shared_secret")
        if not isinstance(shared_secret, str):
            raise ValueError("shared_secret is required")
        repo_root = data.get("repo_root")
        if repo_root is None:
            raise ValueError("repo_root is required")
        backend = data.get("backend", "mock")
        if not isinstance(backend, str):
            raise ValueError("backend must be a string")
        blender_binary = data.get("blender_binary")
        return cls(
            host=str(data.get("host", "127.0.0.1")),
            port=_parse_port(data.get("port", 8766)),
            shared_secret=shared_secret,
            heartbeat_seconds=_parse_heartbeat(data.get("heartbeat_seconds", 5.0)),
            log_level=str(data.get("log_level", "INFO")),
            backend=backend,
            repo_root=Path(repo_root),
            blender_binary=Path(blender_binary) if blender_binary else None,
        )

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        base_dir: Path | None = None,
        require_secret: bool = True,
    ) -> ControllerSettings:
        source = dict(os.environ if env is None else env)
        secret = source.get("BLENDER_MCP_CONTROLLER_SECRET")
        if require_secret and not secret:
            raise ValueError("BLENDER_MCP_CONTROLLER_SECRET is required")
        blender_binary = source.get("BLENDER_MCP_BLENDER_BINARY") or None
        backend = source.get("BLENDER_MCP_CONTROLLER_MODE") or source.get(
            "BLENDER_MCP_CONTROLLER_BACKEND", "mock"
        )
        return cls(
            host=source.get("BLENDER_MCP_CONTROLLER_HOST", "127.0.0.1"),
            port=_parse_port(source.get("BLENDER_MCP_CONTROLLER_PORT", "8766")),
            shared_secret=secret or "",
            heartbeat_seconds=_parse_heartbeat(source.get("BLENDER_MCP_CONTROLLER_HEARTBEAT_SECONDS", "5")),
            log_level=source.get("BLENDER_MCP_LOG_LEVEL", "INFO"),
            backend=backend,
            repo_root=_discover_repo_root(base_dir, source.get("BLENDER_MCP_REPO_ROOT")),
            blender_binary=Path(blender_binary).resolve() if blender_binary else None,
        )
