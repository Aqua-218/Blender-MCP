from __future__ import annotations

import asyncio
import hashlib
import math
import secrets
import sys
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from time import perf_counter
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from mcp_server.bridge import ControllerBridgeClient, ControllerBridgeError
from mcp_server.config import ServerSettings
from mcp_server.logger import get_logger
from mcp_server.models.common import failed_result
from mcp_server.persistence import (
    DatabaseManager,
    EntityRepository,
    ExportRecordRepository,
    OperationRepository,
    ProjectRepository,
    QAReportRepository,
    SnapshotRepository,
)
from mcp_server.policy import PolicyEngine, ToolClass
from mcp_server.serialization import json_dumps, json_loads
from mcp_server.tools.helpers import create_internal_snapshot, require_project
from mcp_server.tools.system import (
    BridgePingRequest,
    RuntimeInfoRequest,
    SafeConfigRequest,
    ServerMetricsRequest,
    get_runtime_info,
    get_safe_config,
    get_server_metrics,
    ping_bridge,
)
from mcp_server.workspace import WorkspaceManager, WorkspaceViolationError

ModelT = TypeVar("ModelT", bound=BaseModel)
HandlerT = Callable[["AppContext", ModelT], Awaitable[BaseModel]]
SUPPORTED_MCP_PROTOCOL_VERSION = "2024-11-05"


def _percentile_ms(samples: list[float], fraction: float) -> float:
    if not samples:
        return 0.0
    ordered = sorted(samples)
    index = max(0, min(len(ordered) - 1, math.ceil(len(ordered) * fraction) - 1))
    return round(float(ordered[index]), 3)


def _record_latency_bucket(bucket: dict[str, Any], latency_ms: float, *, sample_limit: int) -> None:
    samples = bucket.setdefault("_samples_ms", [])
    samples.append(latency_ms)
    if len(samples) > sample_limit:
        del samples[: len(samples) - sample_limit]
    bucket["count"] = int(bucket.get("count", 0)) + 1
    bucket["total_ms"] = round(float(bucket.get("total_ms", 0.0)) + latency_ms, 3)
    bucket["max_ms"] = round(max(float(bucket.get("max_ms", 0.0)), latency_ms), 3)
    bucket["avg_ms"] = round(float(bucket["total_ms"]) / int(bucket["count"]), 3)
    bucket["percentiles_ms"] = {
        "p50_ms": _percentile_ms(samples, 0.50),
        "p95_ms": _percentile_ms(samples, 0.95),
        "p99_ms": _percentile_ms(samples, 0.99),
    }


def _increment_status_bucket(bucket: dict[str, Any], status: str) -> None:
    bucket["count"] = int(bucket.get("count", 0)) + 1
    if status == "success":
        bucket["success_count"] = int(bucket.get("success_count", 0)) + 1
    bucket["success_rate"] = round(
        float(bucket.get("success_count", 0)) / float(bucket["count"]),
        4,
    )


def _record_duration_bucket(bucket: dict[str, Any], status: str, latency_ms: float) -> None:
    _increment_status_bucket(bucket, status)
    bucket["total_duration_ms"] = round(float(bucket.get("total_duration_ms", 0.0)) + latency_ms, 3)
    bucket["max_duration_ms"] = round(max(float(bucket.get("max_duration_ms", 0.0)), latency_ms), 3)
    bucket["avg_duration_ms"] = round(float(bucket["total_duration_ms"]) / float(bucket["count"]), 3)


@dataclass
class ToolDefinition:
    name: str
    description: str
    family: str
    input_model: type[BaseModel]
    handler: HandlerT[Any]
    read_only: bool
    tool_class: ToolClass


@dataclass
class AppContext:
    settings: ServerSettings
    logger: Any
    db: DatabaseManager
    workspace: WorkspaceManager
    bridge: ControllerBridgeClient
    projects: ProjectRepository
    entities: EntityRepository
    operations: OperationRepository
    snapshots: SnapshotRepository
    qa_reports: QAReportRepository
    export_records: ExportRecordRepository
    policy: PolicyEngine
    metrics: dict[str, Any]
    active_project_id: str | None = None


class MCPServerApplication:
    def __init__(self, settings: ServerSettings):
        logger = get_logger(settings.log_level)
        db = DatabaseManager(settings.repo_root, settings.metadata_db_path())
        self.context = AppContext(
            settings=settings,
            logger=logger,
            db=db,
            workspace=WorkspaceManager(settings),
            bridge=ControllerBridgeClient(settings),
            projects=ProjectRepository(db),
            entities=EntityRepository(db),
            operations=OperationRepository(db),
            snapshots=SnapshotRepository(db),
            qa_reports=QAReportRepository(db),
            export_records=ExportRecordRepository(db),
            policy=PolicyEngine(settings),
            metrics={
                "tool_calls": {"total": 0, "by_tool": {}, "by_family": {}, "by_status": {}},
                "latency_ms": {"by_tool": {}, "by_family": {}},
                "controller": {"available": False, "timeouts": 0},
                "renders": {"count": 0, "success_count": 0, "success_rate": 0.0, "by_preset": {}},
                "exports": {"count": 0, "success_count": 0, "success_rate": 0.0, "by_format": {}},
                "snapshots": {"count": 0, "success_count": 0, "success_rate": 0.0, "total_duration_ms": 0.0, "max_duration_ms": 0.0, "avg_duration_ms": 0.0},
                "qa": {"severity_counts": {}},
                "security": {
                    "policy_violations": 0,
                    "http_auth_failures": 0,
                    "http_origin_rejections": 0,
                    "oversized_request_rejections": 0,
                },
            },
        )
        self._started = False
        self._infra_started = False
        self._http_server: ThreadingHTTPServer | None = None
        self.tools: dict[str, ToolDefinition] = {}
        self._register_system_tools()
        self._register_family_tools()

    def _ensure_infra_started(self) -> None:
        if self._infra_started:
            return
        self.context.workspace.bootstrap()
        self.context.db.initialize()
        self._infra_started = True

    @staticmethod
    def tool_definition(
        *,
        name: str,
        description: str,
        family: str,
        input_model: type[BaseModel],
        handler: HandlerT[Any],
        read_only: bool,
    ) -> ToolDefinition:
        return ToolDefinition(
            name=name,
            description=description,
            family=family,
            input_model=input_model,
            handler=handler,
            read_only=read_only,
            tool_class=ToolClass.QUERY if read_only else ToolClass.SAFE_MUTATION,
        )

    def _register_system_tools(self) -> None:
        self.register_tool(
            ToolDefinition(
                name="ping_bridge",
                description="Ping the controller bridge and return health information.",
                family="system",
                input_model=BridgePingRequest,
                handler=ping_bridge,
                read_only=True,
                tool_class=ToolClass.QUERY,
            )
        )
        self.register_tool(
            ToolDefinition(
                name="get_server_metrics",
                description="Return in-memory server metrics and counters.",
                family="system",
                input_model=ServerMetricsRequest,
                handler=get_server_metrics,
                read_only=True,
                tool_class=ToolClass.QUERY,
            )
        )
        self.register_tool(
            ToolDefinition(
                name="get_safe_config",
                description="Return non-secret server configuration values.",
                family="system",
                input_model=SafeConfigRequest,
                handler=get_safe_config,
                read_only=True,
                tool_class=ToolClass.QUERY,
            )
        )

    def _record_tool_metrics(
        self,
        tool_name: str,
        family: str,
        status: str,
        latency_ms: float,
        *,
        arguments: dict[str, Any] | None = None,
        payload: dict[str, Any] | None = None,
    ) -> None:
        metrics = self.context.metrics
        tool_calls = metrics["tool_calls"]
        tool_calls["total"] += 1
        tool_calls["by_status"][status] = tool_calls["by_status"].get(status, 0) + 1
        per_tool = tool_calls["by_tool"].setdefault(tool_name, {"count": 0, "status": {}})
        per_tool["count"] += 1
        per_tool["status"][status] = per_tool["status"].get(status, 0) + 1

        per_family = tool_calls["by_family"].setdefault(family, {"count": 0, "status": {}})
        per_family["count"] += 1
        per_family["status"][status] = per_family["status"].get(status, 0) + 1

        sample_limit = self.context.settings.metrics_latency_window
        latency = metrics["latency_ms"]["by_tool"].setdefault(tool_name, {})
        _record_latency_bucket(latency, latency_ms, sample_limit=sample_limit)

        family_latency = metrics["latency_ms"]["by_family"].setdefault(family, {})
        _record_latency_bucket(family_latency, latency_ms, sample_limit=sample_limit)

        if family == "render":
            renders = metrics["renders"]
            _record_duration_bucket(renders, status, latency_ms)
            preset_name = self._render_preset_for_metrics(tool_name, arguments, payload)
            preset_bucket = renders["by_preset"].setdefault(preset_name, {})
            _record_duration_bucket(preset_bucket, status, latency_ms)
        if tool_name.startswith("export_"):
            exports = metrics["exports"]
            _increment_status_bucket(exports, status)
            export_format = self._export_format_for_metrics(arguments, payload)
            format_bucket = exports["by_format"].setdefault(export_format, {})
            _increment_status_bucket(format_bucket, status)
        if tool_name == "create_snapshot":
            _record_duration_bucket(metrics["snapshots"], status, latency_ms)

        severity_summary = payload.get("severity_summary") if isinstance(payload, dict) else None
        if family == "qa" and isinstance(severity_summary, dict):
            qa_severity = metrics["qa"]["severity_counts"]
            for severity, count in severity_summary.items():
                qa_severity[str(severity)] = qa_severity.get(str(severity), 0) + int(count)

    def _render_preset_for_metrics(
        self,
        tool_name: str,
        arguments: dict[str, Any] | None,
        payload: dict[str, Any] | None,
    ) -> str:
        if isinstance(arguments, dict) and isinstance(arguments.get("preset_name"), str):
            return str(arguments["preset_name"])
        if tool_name.startswith("render_"):
            return tool_name.removeprefix("render_")
        if isinstance(payload, dict) and isinstance(payload.get("preset_name"), str):
            return str(payload["preset_name"])
        return "custom"

    @staticmethod
    def _export_format_for_metrics(
        arguments: dict[str, Any] | None,
        payload: dict[str, Any] | None,
    ) -> str:
        if isinstance(payload, dict) and isinstance(payload.get("export_format"), str):
            return str(payload["export_format"])
        if isinstance(arguments, dict) and isinstance(arguments.get("export_format"), str):
            return str(arguments["export_format"])
        return "profile_default"

    def _auth_fingerprint(self, token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]

    def _log_tool_result(
        self,
        *,
        tool_name: str,
        family: str,
        request_id: str,
        project_id: str | None,
        status: str,
        duration_ms: float,
        warnings_count: int,
        errors_count: int,
    ) -> None:
        log_method = self.context.logger.info if status == "success" else self.context.logger.warning
        log_method(
            "Tool completed." if status == "success" else "Tool completed with failures.",
            extra={
                "request_id": request_id,
                "project_id": project_id,
                "tool_name": tool_name,
                "family": family,
                "status": status,
                "duration_ms": round(duration_ms, 3),
                "warnings_count": warnings_count,
                "errors_count": errors_count,
            },
        )

    def _log_security_event(
        self,
        message: str,
        *,
        error_code: str,
        tool_name: str | None = None,
        request_id: str | None = None,
        origin: str | None = None,
        client_host: str | None = None,
        authenticated: bool | None = None,
        role: str | None = None,
        auth_fingerprint: str | None = None,
    ) -> None:
        self.context.logger.warning(
            message,
            extra={
                "request_id": request_id,
                "tool_name": tool_name,
                "status": "failed",
                "error_code": error_code,
                "transport": "http" if origin is not None or client_host is not None else None,
                "origin": origin,
                "client_host": client_host,
                "authenticated": authenticated,
                "role": role,
                "auth_fingerprint": auth_fingerprint,
            },
        )

    def _attach_auth_context(
        self,
        arguments: dict[str, Any],
        auth_context: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if auth_context is None:
            return arguments
        return {**arguments, "_auth_context": auth_context}

    def _authenticate_http_request(
        self,
        handler: BaseHTTPRequestHandler,
    ) -> tuple[HTTPStatus | None, str | None, str | None, dict[str, Any] | None]:
        settings = self.context.settings
        origin = handler.headers.get("Origin")
        client_host = handler.client_address[0] if handler.client_address else None
        if origin and origin not in settings.http_allowed_origins:
            self.context.metrics["security"]["http_origin_rejections"] += 1
            self._log_security_event(
                "HTTP request rejected because the Origin header is not allowlisted.",
                error_code="origin_not_allowed",
                origin=origin,
                client_host=client_host,
                authenticated=False,
            )
            return HTTPStatus.FORBIDDEN, "Origin not allowed", None, None
        if settings.unsafe_http_enabled:
            return None, None, None, {
                "transport": "http",
                "authenticated": False,
                "role": settings.default_role,
                "origin": origin,
                "client_host": client_host,
                "mode": "unsafe_local_debug",
            }

        auth_header = handler.headers.get("Authorization") or ""
        provided_token: str | None = None
        scheme, _, token_value = auth_header.partition(" ")
        if scheme.lower() == "bearer" and token_value.strip():
            provided_token = token_value.strip()

        expected_token = settings.http_auth_token
        if expected_token is None or provided_token is None or not secrets.compare_digest(provided_token, expected_token):
            self.context.metrics["security"]["http_auth_failures"] += 1
            self._log_security_event(
                "HTTP authentication failed before JSON-RPC dispatch.",
                error_code="authentication_failed",
                origin=origin,
                client_host=client_host,
                authenticated=False,
            )
            return HTTPStatus.UNAUTHORIZED, "Invalid or missing auth token", None, None

        auth_fingerprint = self._auth_fingerprint(provided_token)
        return None, None, settings.http_auth_role, {
            "transport": "http",
            "authenticated": True,
            "role": settings.http_auth_role,
            "origin": origin,
            "client_host": client_host,
            "auth_fingerprint": auth_fingerprint,
        }

    def shutdown_http_server(self) -> None:
        if self._http_server is not None:
            self._http_server.shutdown()

    def _register_family_tools(self) -> None:
        from mcp_server.tools import (
            aaa_orchestrator,
            aaa_workflows,
            animation_rigging,
            asset_io,
            asset_library,
            batch_ops,
            camera,
            collections,
            game_prep,
            geometry,
            geometry_nodes,
            history,
            lighting,
            material,
            model_generation,
            modifiers,
            object,
            parts,
            production_pipeline,
            project,
            qa,
            render,
            repair,
            scene,
            selection_sets,
            texture_uv,
            transforms,
            world,
        )

        for module in (project, object, geometry, material, render, camera, lighting, game_prep, production_pipeline, aaa_orchestrator, aaa_workflows, asset_io, asset_library, batch_ops, qa, repair, modifiers, collections, transforms, selection_sets, parts, model_generation, history, scene, world, geometry_nodes, texture_uv, animation_rigging):
            module.register_tools(self)
        self.register_tool(
            ToolDefinition(
                name="get_runtime_info",
                description="Return controller runtime information and queue metrics.",
                family="system",
                input_model=RuntimeInfoRequest,
                handler=get_runtime_info,
                read_only=True,
                tool_class=ToolClass.QUERY,
            )
        )

    def register_tool(self, definition: ToolDefinition) -> None:
        self.tools[definition.name] = definition

    async def start(self) -> None:
        if self._started:
            return
        self._ensure_infra_started()
        await self.context.bridge.start()
        self._started = True

    async def stop(self) -> None:
        if not self._started:
            return
        await self.context.bridge.stop()
        self._started = False
        self.context.active_project_id = None

    async def initialize(self, _params: dict[str, Any] | None = None) -> dict[str, Any]:
        self._ensure_infra_started()
        return {
            "protocolVersion": SUPPORTED_MCP_PROTOCOL_VERSION,
            "serverInfo": {
                "name": self.context.settings.server_name,
                "version": self.context.settings.server_version,
            },
            "instructions": (
                "Validate all requests before Blender mutation, keep file I/O inside allowlisted roots, "
                "reject caller-supplied roles on unauthenticated transports, and require confirmation for destructive operations."
            ),
            "capabilities": {
                "tools": {"listChanged": False},
            },
        }

    def list_tools(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        for tool in self.tools.values():
            tools.append(
                {
                    "name": tool.name,
                    "description": tool.description,
                    "inputSchema": tool.input_model.model_json_schema(),
                    "annotations": {
                        "family": tool.family,
                        "readOnlyHint": tool.read_only,
                    },
                }
            )
        return tools

    async def execute_tool(
        self,
        name: str,
        arguments: dict[str, Any],
        *,
        role: str | None = None,
        authenticated_role: str | None = None,
        auth_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        started_at = perf_counter()
        arguments = dict(arguments)
        if "safe_mode" not in arguments:
            arguments["safe_mode"] = self.context.settings.safe_mode_default
        request_id = str(arguments.get("request_id", "unknown"))
        project_id_arg = arguments.get("project_id")

        def finalize(payload: dict[str, Any], *, family: str = "system") -> dict[str, Any]:
            duration_ms = max((perf_counter() - started_at) * 1000.0, 0.0)
            self._record_tool_metrics(
                name,
                family,
                str(payload.get("status", "failed")),
                duration_ms,
                arguments=arguments,
                payload=payload,
            )
            self._log_tool_result(
                tool_name=name,
                family=family,
                request_id=str(payload.get("request_id", request_id)),
                project_id=(
                    str(payload.get("project_id"))
                    if payload.get("project_id") is not None
                    else (str(project_id_arg) if project_id_arg is not None else None)
                ),
                status=str(payload.get("status", "failed")),
                duration_ms=duration_ms,
                warnings_count=len(payload.get("warnings", []) or []),
                errors_count=len(payload.get("errors", []) or []),
            )
            return payload

        if role is not None:
            self.context.metrics["security"]["policy_violations"] += 1
            self._log_security_event(
                "Caller-supplied role is rejected before tool dispatch.",
                error_code="validation_error",
                request_id=request_id,
                tool_name=name,
                authenticated=authenticated_role is not None,
                role=role,
                auth_fingerprint=auth_context.get("auth_fingerprint") if auth_context else None,
            )
            result = failed_result(
                request_id=arguments.get("request_id", "unknown"),
                tool_name=name,
                summary="Caller-supplied role is not accepted on unauthenticated transports.",
                errors=["validation_error: caller-supplied role is not accepted"],
            )
            return finalize(result.model_dump())
        if name not in self.tools:
            result = failed_result(
                request_id=arguments.get("request_id", "unknown"),
                tool_name=name,
                summary="Tool was not found.",
                errors=["validation_error: unknown tool"],
            )
            return finalize(result.model_dump())
        definition = self.tools[name]
        try:
            request_model = definition.input_model.model_validate(arguments)
        except ValidationError as exc:
            result = failed_result(
                request_id=arguments.get("request_id", "unknown"),
                tool_name=name,
                summary="Request validation failed.",
                errors=[f"validation_error: {error['msg']}" for error in exc.errors()],
            )
            return finalize(result.model_dump(), family=definition.family)
        self._ensure_infra_started()
        decision = self.context.policy.authorize(
            tool_name=name,
            role=(authenticated_role or self.context.settings.default_role),
            destructive_confirmation=bool(arguments.get("destructive_confirmation", False)),
            blast_radius=len(arguments.get("target_ids", [])) or (1 if arguments.get("target_id") else 0),
            overwrite=bool(arguments.get("overwrite", False)),
        )
        if not decision.allowed:
            self.context.metrics["security"]["policy_violations"] += 1
            self._log_security_event(
                decision.message or "Policy rejected the request.",
                error_code=decision.error_code or "policy_violation",
                tool_name=name,
                request_id=request_model.request_id,
                authenticated=authenticated_role is not None,
                role=authenticated_role,
                auth_fingerprint=auth_context.get("auth_fingerprint") if auth_context else None,
            )
            result = failed_result(
                request_id=request_model.request_id,
                tool_name=name,
                summary=decision.message or "Policy rejected the request.",
                errors=[f"{decision.error_code or 'policy_violation'}: {decision.message}"] if decision.message else [decision.error_code or "policy_violation"],
            )
            return finalize(result.model_dump(), family=definition.family)
        operation_record = None
        history_enabled = definition.family != "system"
        project_id = getattr(request_model, "project_id", None)
        if project_id is not None and self.context.projects.get(project_id) is None:
            result = failed_result(
                request_id=request_model.request_id,
                tool_name=name,
                summary=f"Unknown project_id: {project_id}",
                errors=[f"target_not_found: Unknown project_id: {project_id}"],
            )
            return finalize(result.model_dump(), family=definition.family)
        if project_id is not None and name not in {"create_project", "open_project"}:
            active_project_id = self.context.active_project_id
            if active_project_id is None:
                result = failed_result(
                    request_id=request_model.request_id,
                    tool_name=name,
                    summary="No active project is loaded in the controller.",
                    errors=["validation_error: open or create the requested project before invoking project-scoped tools"],
                )
                return finalize(result.model_dump(), family=definition.family)
            if active_project_id != project_id:
                result = failed_result(
                    request_id=request_model.request_id,
                    tool_name=name,
                    summary="Requested project is not active in the controller.",
                    errors=["validation_error: requested project is not active in the controller"],
                )
                return finalize(result.model_dump(), family=definition.family)
        if not self._started:
            await self.context.bridge.start()
            self._started = True
            self.context.metrics["controller"]["available"] = True
        if history_enabled and project_id is not None:
            logged_input = self._attach_auth_context(arguments, auth_context)
            operation_record = self.context.operations.start(
                operation_id=arguments.get("operation_id") or f"op_{request_model.request_id}",
                project_id=project_id,
                request_id=request_model.request_id,
                tool_name=name,
                target_entity_id=arguments.get("target_id"),
                status="running",
                user_instruction=getattr(request_model, "instruction", None),
                input_json=json_dumps(logged_input),
            )
            if decision.requires_snapshot and name != "create_snapshot":
                project = require_project(self.context, project_id)
                await create_internal_snapshot(
                    self.context,
                    project,
                    operation_record.operation_id,
                    reason="rollback_target" if name == "rollback_to_snapshot" else "pre_destructive_change",
                )
        try:
            result_model = await definition.handler(self.context, request_model)
        except WorkspaceViolationError as exc:
            result = failed_result(
                request_id=request_model.request_id,
                tool_name=name,
                summary=str(exc),
                errors=[f"validation_error: {exc}"],
            )
            if operation_record is not None:
                self.context.operations.complete(
                    operation_record.operation_id,
                    status="failed",
                    output_payload=result.model_dump(),
                    warnings=[],
                    errors=result.errors,
                )
            return finalize(result.model_dump(), family=definition.family)
        except ValueError as exc:
            message = str(exc)
            if message.startswith("Unknown project_id:"):
                result = failed_result(
                    request_id=request_model.request_id,
                    tool_name=name,
                    summary=message,
                    errors=[f"target_not_found: {message}"],
                )
                if operation_record is not None:
                    self.context.operations.complete(
                        operation_record.operation_id,
                        status="failed",
                        output_payload=result.model_dump(),
                        warnings=[],
                        errors=result.errors,
                    )
                return finalize(result.model_dump(), family=definition.family)
            if message.startswith("No matching targets were resolved."):
                result = failed_result(
                    request_id=request_model.request_id,
                    tool_name=name,
                    summary=message,
                    errors=[f"target_not_found: {message}"],
                )
                if operation_record is not None:
                    self.context.operations.complete(
                        operation_record.operation_id,
                        status="failed",
                        output_payload=result.model_dump(),
                        warnings=[],
                        errors=result.errors,
                    )
                return finalize(result.model_dump(), family=definition.family)
            if operation_record is not None:
                self.context.operations.complete(
                    operation_record.operation_id,
                    status="failed",
                    output_payload={"error": str(exc)},
                    warnings=[],
                    errors=[str(exc)],
                )
            raise
        except ControllerBridgeError as exc:
            if exc.code == "controller_timeout":
                self.context.metrics["controller"]["timeouts"] += 1
                self.context.logger.warning(
                    "Controller bridge timed out while handling a tool request.",
                    extra={
                        "request_id": request_model.request_id,
                        "project_id": getattr(request_model, "project_id", None),
                        "tool_name": name,
                        "family": definition.family,
                        "status": "failed",
                        "error_code": exc.code,
                    },
                )
            self.context.metrics["controller"]["available"] = False
            if exc.code in {"validation_error", "target_not_found", "unsupported_feature"}:
                result = failed_result(
                    request_id=request_model.request_id,
                    tool_name=name,
                    summary=exc.message,
                    errors=[f"{exc.code}: {exc.message}"],
                )
                if operation_record is not None:
                    self.context.operations.complete(
                        operation_record.operation_id,
                        status="failed",
                        output_payload=result.model_dump(),
                        warnings=[],
                        errors=result.errors,
                    )
                return finalize(result.model_dump(), family=definition.family)
            if operation_record is not None:
                self.context.operations.complete(
                    operation_record.operation_id,
                    status="failed",
                    output_payload={"error": exc.message},
                    warnings=[],
                    errors=[exc.message],
                )
            raise
        except Exception as exc:
            if operation_record is not None:
                self.context.operations.complete(
                    operation_record.operation_id,
                    status="failed",
                    output_payload={"error": str(exc)},
                    warnings=[],
                    errors=[str(exc)],
                )
            raise
        result_payload = result_model.model_dump()
        if history_enabled and operation_record is None:
            result_project_id = result_payload.get("project_id")
            if result_project_id:
                logged_input = self._attach_auth_context(arguments, auth_context)
                operation_record = self.context.operations.start(
                    operation_id=f"op_{request_model.request_id}",
                    project_id=result_project_id,
                    request_id=request_model.request_id,
                    tool_name=name,
                    target_entity_id=arguments.get("target_id"),
                    status="running",
                    user_instruction=getattr(request_model, "instruction", None),
                    input_json=json_dumps(logged_input),
                )
        if operation_record is not None and name == "create_snapshot" and result_payload.get("snapshot_id"):
            self.context.snapshots.update_provenance(
                result_payload["snapshot_id"],
                source_operation_id=operation_record.operation_id,
            )
        if operation_record is not None:
            self.context.operations.complete(
                operation_record.operation_id,
                status=result_payload["status"],
                output_payload=result_payload,
                warnings=result_payload.get("warnings", []),
                errors=result_payload.get("errors", []),
            )
        return finalize(result_payload, family=definition.family)

    async def handle_jsonrpc(
        self,
        payload: dict[str, Any],
        *,
        authenticated_role: str | None = None,
        auth_context: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        jsonrpc = payload.get("jsonrpc", "2.0")
        request_id = payload.get("id")
        method = payload.get("method")
        params = payload.get("params", {})
        try:
            if method == "initialize":
                result = await self.initialize(params)
            elif method == "tools/list":
                result = {"tools": self.list_tools()}
            elif method == "tools/call":
                result = await self.execute_tool(
                    params["name"],
                    params.get("arguments", {}),
                    role=params.get("role"),
                    authenticated_role=authenticated_role,
                    auth_context=auth_context,
                )
            elif method == "notifications/initialized":
                return None
            else:
                if request_id is None:
                    return None
                return {
                    "jsonrpc": jsonrpc,
                    "id": request_id,
                    "error": {
                        "code": -32601,
                        "message": f"Method not found: {method}",
                    },
                }
            return {"jsonrpc": jsonrpc, "id": request_id, "result": result}
        except Exception as exc:
            if request_id is None:
                return None
            return {
                "jsonrpc": jsonrpc,
                "id": request_id,
                "error": {
                    "code": -32603,
                    "message": str(exc),
                },
            }

    async def serve_stdio(self) -> None:
        try:
            for raw_line in sys.stdin:
                line = raw_line.strip()
                if not line:
                    continue
                response = await self.handle_jsonrpc(json_loads(line))
                if response is not None:
                    sys.stdout.write(json_dumps(response) + "\n")
                    sys.stdout.flush()
        finally:
            await self.stop()

    def serve_http(self) -> None:
        application = self
        settings = self.context.settings

        class MCPRequestHandler(BaseHTTPRequestHandler):
            def _set_cors_headers(self, origin: str | None) -> None:
                if origin and origin in settings.http_allowed_origins:
                    self.send_header("Access-Control-Allow-Origin", origin)
                    self.send_header("Vary", "Origin")
                self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers", "Authorization, Content-Type")
                self.send_header("Access-Control-Max-Age", "600")

            def _send_response_with_body(
                self,
                status: HTTPStatus,
                body: bytes = b"",
                *,
                origin: str | None = None,
                content_type: str = "text/plain; charset=utf-8",
                extra_headers: dict[str, str] | None = None,
            ) -> None:
                self.send_response(status)
                self._set_cors_headers(origin)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                for key, value in (extra_headers or {}).items():
                    self.send_header(key, value)
                self.end_headers()
                if body:
                    self.wfile.write(body)

            def do_OPTIONS(self) -> None:  # noqa: N802
                origin = self.headers.get("Origin")
                if origin and origin not in settings.http_allowed_origins:
                    application.context.metrics["security"]["http_origin_rejections"] += 1
                    application._log_security_event(
                        "HTTP preflight rejected because the Origin header is not allowlisted.",
                        error_code="origin_not_allowed",
                        origin=origin,
                        client_host=self.client_address[0] if self.client_address else None,
                        authenticated=False,
                    )
                    self._send_response_with_body(
                        HTTPStatus.FORBIDDEN,
                        b"Origin not allowed",
                        content_type="text/plain; charset=utf-8",
                    )
                    return
                self._send_response_with_body(HTTPStatus.NO_CONTENT, origin=origin)

            def do_POST(self) -> None:  # noqa: N802
                origin = self.headers.get("Origin")
                status, message, authenticated_role, auth_context = application._authenticate_http_request(self)
                if status is not None:
                    if status == HTTPStatus.UNAUTHORIZED:
                        self._send_response_with_body(
                            status,
                            (message or "Invalid or missing auth token").encode("utf-8"),
                            origin=origin,
                            extra_headers={"WWW-Authenticate": 'Bearer realm="blender-mcp"'},
                        )
                        return
                    self._send_response_with_body(
                        status,
                        (message or "Request rejected").encode("utf-8"),
                        origin=origin,
                    )
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    self._send_response_with_body(
                        HTTPStatus.BAD_REQUEST,
                        b"Invalid Content-Length",
                        origin=origin,
                    )
                    return
                if length > settings.http_max_request_bytes:
                    application.context.metrics["security"]["oversized_request_rejections"] += 1
                    application._log_security_event(
                        "HTTP request body exceeded the configured size limit.",
                        error_code="request_too_large",
                        origin=origin,
                        client_host=self.client_address[0] if self.client_address else None,
                        authenticated=bool(auth_context and auth_context.get("authenticated")),
                        role=authenticated_role,
                        auth_fingerprint=auth_context.get("auth_fingerprint") if auth_context else None,
                    )
                    self._send_response_with_body(
                        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                        b"Request body too large",
                        origin=origin,
                    )
                    return
                raw_body = self.rfile.read(length)
                if len(raw_body) > settings.http_max_request_bytes:
                    application.context.metrics["security"]["oversized_request_rejections"] += 1
                    self._send_response_with_body(
                        HTTPStatus.REQUEST_ENTITY_TOO_LARGE,
                        b"Request body too large",
                        origin=origin,
                    )
                    return
                response = asyncio.run(
                    application.handle_jsonrpc(
                        json_loads(raw_body),
                        authenticated_role=authenticated_role,
                        auth_context=auth_context,
                    )
                )
                body = (json_dumps(response) + "\n").encode("utf-8")
                self._send_response_with_body(
                    HTTPStatus.OK,
                    body,
                    origin=origin,
                    content_type="application/json",
                )

            def log_message(self, _format: str, *_args: object) -> None:
                return

        server = ThreadingHTTPServer((settings.http_host, settings.http_port), MCPRequestHandler)
        self._http_server = server
        try:
            server.serve_forever()
        finally:
            server.server_close()
            self._http_server = None
            asyncio.run(self.stop())
