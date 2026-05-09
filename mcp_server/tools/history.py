from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from presets.rendering import RENDER_PRESETS
from pydantic import Field

from mcp_server.models.common import CommonToolRequest, failed_result, success_result
from mcp_server.persistence import SnapshotRecord
from mcp_server.serialization import json_loads
from mcp_server.tools.helpers import (
    create_internal_snapshot,
    project_paths_for_record,
    require_project,
)
from mcp_server.utils import slugify


class ListOperationsRequest(CommonToolRequest):
    project_id: str
    limit: int = Field(default=20, ge=1, le=200)


class ListSnapshotsRequest(CommonToolRequest):
    project_id: str
    limit: int = Field(default=20, ge=1, le=200)


class CompareSnapshotsRequest(CommonToolRequest):
    project_id: str
    snapshot_id_a: str
    snapshot_id_b: str


class GenerateDiffSummaryRequest(CommonToolRequest):
    project_id: str
    snapshot_id_a: str
    snapshot_id_b: str


class RenderComparisonViewsRequest(CommonToolRequest):
    project_id: str
    snapshot_id_a: str
    snapshot_id_b: str
    output_dir: str | None = None
    camera_id: str | None = None


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _operation_dict(record) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    output_payload = json_loads(record.output_json)
    if not isinstance(output_payload, dict):
        output_payload = {}
    return {
        "operation_id": record.operation_id,
        "tool_name": record.tool_name,
        "status": record.status,
        "started_at": record.started_at,
        "completed_at": record.completed_at,
        "duration_ms": record.duration_ms,
        "target_entity_id": record.target_entity_id,
        "user_instruction": record.user_instruction,
        "output_summary": str(output_payload.get("summary", "")),
        "created_object_ids": _string_list(output_payload.get("created_object_ids")),
        "modified_object_ids": _string_list(output_payload.get("modified_object_ids")),
        "deleted_object_ids": _string_list(output_payload.get("deleted_object_ids")),
        "file_paths": _string_list(output_payload.get("file_paths")),
        "image_paths": _string_list(output_payload.get("image_paths")),
        "warnings": json_loads(record.warnings_json),
        "errors": json_loads(record.errors_json),
    }


def _snapshot_dict(record: SnapshotRecord) -> dict[str, Any]:
    return {
        "snapshot_id": record.snapshot_id,
        "reason": record.reason,
        "snapshot_path": record.snapshot_path,
        "created_at": record.created_at,
        "source_operation_id": record.source_operation_id,
    }


def _load_snapshot_state(snapshot: SnapshotRecord) -> dict[str, Any]:
    return json.loads(snapshot.snapshot_path and open(snapshot.snapshot_path, encoding="utf-8").read())


def _resolve_snapshot_pair(context, project_id: str, snapshot_id_a: str, snapshot_id_b: str):  # type: ignore[no-untyped-def]
    require_project(context, project_id)
    snap_a = context.snapshots.get(snapshot_id_a)
    snap_b = context.snapshots.get(snapshot_id_b)
    missing = []
    if snap_a is None:
        missing.append(snapshot_id_a)
    if snap_b is None:
        missing.append(snapshot_id_b)
    if missing:
        return None, None, failed_result(
            request_id="unknown",
            tool_name="compare_snapshots",
            summary=f"Snapshots not found: {missing}",
            errors=[f"target_not_found: snapshot(s) {missing} do not exist"],
        )
    return snap_a, snap_b, None


def _diff_payload(state_a: dict[str, Any], state_b: dict[str, Any]) -> dict[str, Any]:
    objects_a: dict[str, Any] = {o["object_id"]: o for o in state_a.get("objects", [])}
    objects_b: dict[str, Any] = {o["object_id"]: o for o in state_b.get("objects", [])}

    added = [oid for oid in objects_b if oid not in objects_a]
    removed = [oid for oid in objects_a if oid not in objects_b]
    modified = [
        oid
        for oid in objects_a
        if oid in objects_b and objects_a[oid] != objects_b[oid]
    ]
    return {
        "added_object_ids": added,
        "removed_object_ids": removed,
        "modified_object_ids": modified,
        "added_count": len(added),
        "removed_count": len(removed),
        "modified_count": len(modified),
    }


async def list_operations(context, request: ListOperationsRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    records = context.operations.recent_by_project(request.project_id, limit=request.limit)
    ops = [_operation_dict(r) for r in records]
    return success_result(
        request_id=request.request_id,
        tool_name="list_operations",
        summary=f"Found {len(ops)} operations.",
        project_id=request.project_id,
        operations=ops,
        count=len(ops),
    )


async def get_generation_history(context, request: ListOperationsRequest):  # type: ignore[no-untyped-def]
    result = await list_operations(context, request)
    payload = result.model_dump()
    payload["tool_name"] = "get_generation_history"
    payload["summary"] = f"Retrieved {payload['count']} historical operations."
    return type(result).model_validate(payload)


async def list_snapshots(context, request: ListSnapshotsRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    records = context.snapshots.lookup_by_project(request.project_id, limit=request.limit)
    snaps = [_snapshot_dict(r) for r in records]
    return success_result(
        request_id=request.request_id,
        tool_name="list_snapshots",
        summary=f"Found {len(snaps)} snapshots.",
        project_id=request.project_id,
        snapshots=snaps,
        count=len(snaps),
    )


async def compare_snapshots(context, request: CompareSnapshotsRequest):  # type: ignore[no-untyped-def]
    snap_a, snap_b, error = _resolve_snapshot_pair(context, request.project_id, request.snapshot_id_a, request.snapshot_id_b)
    if error is not None:
        result = error.model_dump()
        result["request_id"] = request.request_id
        result["tool_name"] = "compare_snapshots"
        return type(error).model_validate(result)
    state_a = _load_snapshot_state(snap_a)
    state_b = _load_snapshot_state(snap_b)
    diff = _diff_payload(state_a, state_b)
    return success_result(
        request_id=request.request_id,
        tool_name="compare_snapshots",
        summary=(
            f"Diff: +{diff['added_count']} added, -{diff['removed_count']} removed, ~{diff['modified_count']} modified."
        ),
        project_id=request.project_id,
        snapshot_id_a=request.snapshot_id_a,
        snapshot_id_b=request.snapshot_id_b,
        diff=diff,
    )


async def generate_diff_summary(context, request: GenerateDiffSummaryRequest):  # type: ignore[no-untyped-def]
    comparison = await compare_snapshots(
        context,
        CompareSnapshotsRequest(
            request_id=request.request_id,
            project_id=request.project_id,
            snapshot_id_a=request.snapshot_id_a,
            snapshot_id_b=request.snapshot_id_b,
        ),
    )
    result = comparison.model_dump()
    if result["status"] != "success":
        result["tool_name"] = "generate_diff_summary"
        return type(comparison).model_validate(result)
    diff = result["diff"]
    summary_lines = [
        f"Added: {diff['added_count']}",
        f"Removed: {diff['removed_count']}",
        f"Modified: {diff['modified_count']}",
    ]
    if diff["added_object_ids"]:
        summary_lines.append(f"Added IDs: {', '.join(diff['added_object_ids'])}")
    if diff["removed_object_ids"]:
        summary_lines.append(f"Removed IDs: {', '.join(diff['removed_object_ids'])}")
    if diff["modified_object_ids"]:
        summary_lines.append(f"Modified IDs: {', '.join(diff['modified_object_ids'])}")
    return success_result(
        request_id=request.request_id,
        tool_name="generate_diff_summary",
        summary="Generated snapshot diff summary.",
        project_id=request.project_id,
        snapshot_id_a=request.snapshot_id_a,
        snapshot_id_b=request.snapshot_id_b,
        diff=diff,
        diff_summary="\n".join(summary_lines),
    )


async def render_comparison_views(context, request: RenderComparisonViewsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    snap_a, snap_b, error = _resolve_snapshot_pair(context, request.project_id, request.snapshot_id_a, request.snapshot_id_b)
    if error is not None:
        result = error.model_dump()
        result["request_id"] = request.request_id
        result["tool_name"] = "render_comparison_views"
        return type(error).model_validate(result)

    project_paths = project_paths_for_record(context, project)
    context.workspace.ensure_project_layout(project_paths)
    output_dir = (
        (project_paths.render_dir / slugify(request.request_id)).resolve(strict=False)
        if request.output_dir is None
        else (project_paths.render_dir / Path(request.output_dir)).resolve(strict=False)
    )
    try:
        output_dir.relative_to(project_paths.render_dir.resolve())
    except ValueError as exc:
        raise ValueError("Comparison output path must stay under the project's render directory.") from exc
    output_dir.mkdir(parents=True, exist_ok=True)

    safety_snapshot = await create_internal_snapshot(context, project, f"op_{request.request_id}", reason="manual")
    was_dirty = bool(project.dirty_flag)
    image_paths: list[str] = []
    try:
        for label, snapshot in (("before", snap_a), ("after", snap_b)):
            await context.bridge.invoke(
                "restore_snapshot",
                {
                    "project_id": project.project_id,
                    "snapshot_path": snapshot.snapshot_path,
                    "target_blend_file_path": project.blend_file_path,
                },
            )
            output_path = context.workspace.canonicalize_output_path(output_dir / f"{label}.png", allowed_extensions=[".png"])
            render_result = await context.bridge.invoke(
                "render_preview",
                {
                    "project_id": project.project_id,
                    "output_path": str(output_path),
                    "camera_id": request.camera_id,
                    **RENDER_PRESETS["standard"],
                },
            )
            image_paths.append(str(context.workspace.canonicalize_output_path(render_result["image_path"], allowed_extensions=[".png"])))
    finally:
        await context.bridge.invoke(
            "restore_snapshot",
            {
                "project_id": project.project_id,
                "snapshot_path": safety_snapshot.snapshot_path,
                "target_blend_file_path": project.blend_file_path,
            },
        )
        if was_dirty:
            context.projects.mark_dirty(project.project_id, project.active_scene_name)
        else:
            context.projects.mark_saved(project.project_id, project.active_scene_name)

    return success_result(
        request_id=request.request_id,
        tool_name="render_comparison_views",
        summary="Rendered comparison views for both snapshots.",
        project_id=project.project_id,
        snapshot_id_a=request.snapshot_id_a,
        snapshot_id_b=request.snapshot_id_b,
        image_paths=image_paths,
        output_dir=str(output_dir),
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    for name, description, handler, model, read_only in (
        (
            "list_operations",
            "List recent operations for a project in reverse-chronological order.",
            list_operations,
            ListOperationsRequest,
            True,
        ),
        (
            "get_generation_history",
            "List recent generation and mutation operations for a project.",
            get_generation_history,
            ListOperationsRequest,
            True,
        ),
        (
            "list_snapshots",
            "List snapshots for a project in reverse-chronological order.",
            list_snapshots,
            ListSnapshotsRequest,
            True,
        ),
        (
            "compare_snapshots",
            "Compare two snapshots and report added, removed, and modified objects.",
            compare_snapshots,
            CompareSnapshotsRequest,
            True,
        ),
        (
            "generate_diff_summary",
            "Generate a human-readable diff summary from two snapshots.",
            generate_diff_summary,
            GenerateDiffSummaryRequest,
            True,
        ),
        (
            "render_comparison_views",
            "Render before/after comparison views for two snapshots.",
            render_comparison_views,
            RenderComparisonViewsRequest,
            False,
        ),
    ):
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="history",
                input_model=model,
                handler=handler,
                read_only=read_only,
            )
        )
