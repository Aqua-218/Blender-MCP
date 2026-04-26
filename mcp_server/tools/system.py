from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from mcp_server.models.common import CommonToolRequest, failed_result, success_result


class BridgePingRequest(CommonToolRequest):
    pass


class RuntimeInfoRequest(CommonToolRequest):
    pass


class ServerMetricsRequest(CommonToolRequest):
    pass


class SafeConfigRequest(CommonToolRequest):
    pass


def _sanitize_metrics(payload: Any) -> Any:
    if isinstance(payload, dict):
        return {
            key: _sanitize_metrics(value)
            for key, value in payload.items()
            if not str(key).startswith("_")
        }
    if isinstance(payload, list):
        return [_sanitize_metrics(item) for item in payload]
    return payload


async def ping_bridge(context, request: BaseModel):  # type: ignore[no-untyped-def]
    try:
        bridge_result = await context.bridge.ping()
    except Exception as exc:
        return failed_result(
            request_id=request.request_id,
            tool_name="ping_bridge",
            summary="Bridge ping failed.",
            errors=[f"controller_unavailable: {exc}"],
        )
    return success_result(
        request_id=request.request_id,
        tool_name="ping_bridge",
        summary="Bridge ping succeeded.",
        bridge=bridge_result,
    )


async def get_runtime_info(context, request: BaseModel):  # type: ignore[no-untyped-def]
    try:
        runtime_info = await context.bridge.get_runtime_info()
        context.metrics["controller"]["available"] = True
    except Exception as exc:
        context.metrics["controller"]["available"] = False
        return failed_result(
            request_id=request.request_id,
            tool_name="get_runtime_info",
            summary="Could not retrieve runtime information.",
            errors=[f"controller_unavailable: {exc}"],
        )
    return success_result(
        request_id=request.request_id,
        tool_name="get_runtime_info",
        summary="Runtime information retrieved.",
        runtime=runtime_info,
    )


async def get_server_metrics(context, request: BaseModel):  # type: ignore[no-untyped-def]
    return success_result(
        request_id=request.request_id,
        tool_name="get_server_metrics",
        summary="Server metrics retrieved.",
        metrics=_sanitize_metrics(context.metrics),
    )


async def get_safe_config(context, request: BaseModel):  # type: ignore[no-untyped-def]
    settings = context.settings
    safe_config = {
        "server_name": settings.server_name,
        "server_version": settings.server_version,
        "transport": settings.transport,
        "workspace_roots": [str(root) for root in settings.workspace_roots],
        "artifact_directories": settings.artifact_directories.model_dump(),
        "safe_mode_default": settings.safe_mode_default,
        "default_role": settings.default_role,
        "log_level": settings.log_level,
        "controller_mode": settings.controller_mode,
        "controller_host": settings.controller_host,
        "controller_port": settings.controller_port,
        "controller_attach_timeout_seconds": settings.controller_attach_timeout_seconds,
        "controller_start_timeout_seconds": settings.controller_start_timeout_seconds,
        "controller_heartbeat_seconds": settings.controller_heartbeat_seconds,
        "blender_binary": str(settings.blender_binary) if settings.blender_binary is not None else None,
        "destructive_snapshot_threshold": settings.destructive_snapshot_threshold,
        "max_safe_mode_polygon_budget": settings.max_safe_mode_polygon_budget,
        "metrics_latency_window": settings.metrics_latency_window,
        "allowed_import_extensions": settings.allowed_import_extensions,
        "allowed_export_extensions": settings.allowed_export_extensions,
        "unsafe_http_enabled": settings.unsafe_http_enabled,
        "http_host": settings.http_host,
        "http_port": settings.http_port,
        "http_allowed_origins": settings.http_allowed_origins,
        "http_auth_enabled": settings.http_auth_token is not None,
        "http_auth_role": settings.http_auth_role,
        "http_max_request_bytes": settings.http_max_request_bytes,
    }
    return success_result(
        request_id=request.request_id,
        tool_name="get_safe_config",
        summary="Safe server configuration retrieved.",
        config=safe_config,
    )
