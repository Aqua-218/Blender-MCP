from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RoleName = Literal["viewer", "editor", "destructive_editor", "operator"]
TransportName = Literal["stdio", "http"]
ControllerMode = Literal["auto", "blender", "mock"]

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}
_REPO_MARKERS = ("pyproject.toml", "alembic.ini")


def _parse_bool(value: str | bool | None, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Invalid boolean value: {value}")


def _parse_csv(value: str | None, *, default: list[str]) -> list[str]:
    if value is None or not value.strip():
        return default
    return [part.strip() for part in value.split(",") if part.strip()]


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


def _is_loopback_host(host: str) -> bool:
    return host.strip().lower() in _LOOPBACK_HOSTS


class ArtifactDirectories(BaseModel):
    model_config = ConfigDict(frozen=True)

    projects: str = "projects"
    renders: str = "renders"
    exports: str = "exports"
    logs: str = "logs"
    snapshots: str = "snapshots"
    metadata: str = "metadata"


class ServerSettings(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    repo_root: Path
    server_name: str = "blender-mcp"
    server_version: str = "0.1.0"
    transport: TransportName = "stdio"
    unsafe_http_enabled: bool = False
    http_host: str = "127.0.0.1"
    http_port: int = 8765
    http_allowed_origins: list[str] = Field(default_factory=lambda: ["http://localhost"])
    http_auth_token: str | None = None
    http_auth_role: RoleName = "editor"
    http_max_request_bytes: int = 1_048_576
    workspace_roots: list[Path]
    artifact_directories: ArtifactDirectories = Field(default_factory=ArtifactDirectories)
    metadata_db_filename: str = "metadata.sqlite3"
    safe_mode_default: bool = True
    default_role: RoleName = "editor"
    log_level: str = "INFO"
    controller_mode: ControllerMode = "auto"
    controller_host: str = "127.0.0.1"
    controller_port: int = 8766
    controller_secret: str | None = None
    controller_attach_timeout_seconds: float = 0.0
    controller_start_timeout_seconds: float = 20.0
    controller_heartbeat_seconds: float = 5.0
    blender_binary: Path | None = None
    destructive_snapshot_threshold: int = 3
    max_safe_mode_polygon_budget: int = 100_000
    metrics_latency_window: int = 256
    allowed_import_extensions: list[str] = Field(
        default_factory=lambda: [".blend", ".glb", ".gltf", ".fbx", ".obj", ".usd", ".usdz", ".stl"]
    )
    allowed_export_extensions: list[str] = Field(
        default_factory=lambda: [".blend", ".glb", ".gltf", ".fbx", ".obj", ".usd", ".usdz", ".stl", ".png"]
    )

    @field_validator("workspace_roots", mode="before")
    @classmethod
    def _normalize_workspace_roots(cls, value: object) -> object:
        if isinstance(value, list):
            return [Path(str(item)).resolve() for item in value]
        return value

    @field_validator("allowed_import_extensions", "allowed_export_extensions")
    @classmethod
    def _normalize_extensions(cls, value: list[str]) -> list[str]:
        return sorted({item.lower() if item.startswith(".") else f".{item.lower()}" for item in value})

    @field_validator("http_allowed_origins")
    @classmethod
    def _normalize_http_allowed_origins(cls, value: list[str]) -> list[str]:
        return list(dict.fromkeys(item.strip() for item in value if item.strip()))

    @field_validator("http_auth_token", mode="before")
    @classmethod
    def _normalize_http_auth_token(cls, value: object) -> object:
        if value is None:
            return None
        normalized = str(value).strip()
        return normalized or None

    @model_validator(mode="after")
    def _validate_workspace_roots(self) -> ServerSettings:
        if not self.workspace_roots:
            raise ValueError("At least one workspace root is required")
        basenames = [root.name for root in self.workspace_roots]
        if len(set(basenames)) != len(basenames):
            raise ValueError("Workspace roots must have unique basenames")
        if not _is_loopback_host(self.controller_host):
            raise ValueError("Controller host must be a loopback address")
        if self.controller_attach_timeout_seconds < 0:
            raise ValueError("Controller attach timeout must be non-negative")
        if self.controller_start_timeout_seconds <= 0:
            raise ValueError("Controller start timeout must be positive")
        if self.controller_heartbeat_seconds <= 0:
            raise ValueError("Controller heartbeat interval must be positive")
        if self.http_max_request_bytes <= 0:
            raise ValueError("HTTP max request bytes must be positive")
        if self.max_safe_mode_polygon_budget <= 0:
            raise ValueError("Safe-mode polygon budget must be positive")
        if self.metrics_latency_window <= 0:
            raise ValueError("Metrics latency window must be positive")
        if self.transport == "http" and not self.unsafe_http_enabled and self.http_auth_token is None:
            raise ValueError(
                "HTTP transport requires BLENDER_MCP_HTTP_AUTH_TOKEN unless unsafe HTTP is explicitly enabled"
            )
        return self

    @classmethod
    def from_env(
        cls,
        env: Mapping[str, str] | None = None,
        *,
        base_dir: Path | None = None,
    ) -> ServerSettings:
        source = dict(os.environ if env is None else env)
        repo_root = _discover_repo_root(base_dir, source.get("BLENDER_MCP_REPO_ROOT"))
        workspace_base = (base_dir or repo_root).resolve()
        workspace_roots = [
            (workspace_base / item).resolve()
            if not Path(item).is_absolute()
            else Path(item).resolve()
            for item in _parse_csv(source.get("BLENDER_MCP_WORKSPACE_ROOTS"), default=["workspace"])
        ]
        blender_binary = source.get("BLENDER_MCP_BLENDER_BINARY") or None
        return cls(
            repo_root=repo_root,
            server_name=source.get("BLENDER_MCP_SERVER_NAME", "blender-mcp"),
            server_version=source.get("BLENDER_MCP_SERVER_VERSION", "0.1.0"),
            transport=source.get("BLENDER_MCP_TRANSPORT", "stdio"),
            unsafe_http_enabled=_parse_bool(
                source.get("BLENDER_MCP_ENABLE_UNAUTHENTICATED_HTTP"), False
            ),
            http_host=source.get("BLENDER_MCP_HTTP_HOST", "127.0.0.1"),
            http_port=int(source.get("BLENDER_MCP_HTTP_PORT", "8765")),
            http_allowed_origins=_parse_csv(
                source.get("BLENDER_MCP_HTTP_ALLOWED_ORIGINS"), default=["http://localhost"]
            ),
            http_auth_token=source.get("BLENDER_MCP_HTTP_AUTH_TOKEN") or None,
            http_auth_role=source.get(
                "BLENDER_MCP_HTTP_AUTH_ROLE",
                source.get("BLENDER_MCP_DEFAULT_ROLE", "editor"),
            ),
            http_max_request_bytes=int(
                source.get("BLENDER_MCP_HTTP_MAX_REQUEST_BYTES", "1048576")
            ),
            workspace_roots=workspace_roots,
            safe_mode_default=_parse_bool(source.get("BLENDER_MCP_SAFE_MODE_DEFAULT"), True),
            default_role=source.get("BLENDER_MCP_DEFAULT_ROLE", "editor"),
            log_level=source.get("BLENDER_MCP_LOG_LEVEL", "INFO"),
            controller_mode=source.get("BLENDER_MCP_CONTROLLER_MODE", "auto"),
            controller_host=source.get("BLENDER_MCP_CONTROLLER_HOST", "127.0.0.1"),
            controller_port=int(source.get("BLENDER_MCP_CONTROLLER_PORT", "8766")),
            controller_secret=source.get("BLENDER_MCP_CONTROLLER_SECRET") or None,
            controller_attach_timeout_seconds=float(
                source.get("BLENDER_MCP_CONTROLLER_ATTACH_TIMEOUT_SECONDS", "0")
            ),
            controller_start_timeout_seconds=float(
                source.get("BLENDER_MCP_CONTROLLER_START_TIMEOUT_SECONDS", "20")
            ),
            controller_heartbeat_seconds=float(
                source.get("BLENDER_MCP_CONTROLLER_HEARTBEAT_SECONDS", "5")
            ),
            blender_binary=Path(blender_binary).resolve() if blender_binary else None,
            destructive_snapshot_threshold=int(
                source.get("BLENDER_MCP_DESTRUCTIVE_SNAPSHOT_THRESHOLD", "3")
            ),
            max_safe_mode_polygon_budget=int(
                source.get("BLENDER_MCP_MAX_SAFE_MODE_POLYGON_BUDGET", "100000")
            ),
            metrics_latency_window=int(
                source.get("BLENDER_MCP_METRICS_LATENCY_WINDOW", "256")
            ),
        )

    def metadata_db_path(self, workspace_root: Path | None = None) -> Path:
        root = (workspace_root or self.workspace_roots[0]).resolve()
        return root / self.artifact_directories.metadata / self.metadata_db_filename

    def ensure_workspace_directories(self) -> None:
        for root in self.workspace_roots:
            root.mkdir(parents=True, exist_ok=True)
            for subdir in self.artifact_directories.model_dump().values():
                (root / subdir).mkdir(parents=True, exist_ok=True)
