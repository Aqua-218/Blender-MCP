from __future__ import annotations

from time import perf_counter
from typing import Literal

from pydantic import Field

from mcp_server.bridge import ControllerBridgeError
from mcp_server.models.common import CommonToolRequest, failed_result, success_result
from mcp_server.tools.helpers import project_paths_for_record, require_project
from mcp_server.utils import new_id


class CreateProjectRequest(CommonToolRequest):
    name: str
    template_name: str = "blank"
    workspace_root: str | None = None
    unit_scale: float = Field(default=1.0, gt=0)
    active_scene_name: str = "Scene"


class OpenProjectRequest(CommonToolRequest):
    blend_file_path: str


class SaveProjectRequest(CommonToolRequest):
    project_id: str


class SaveProjectAsRequest(CommonToolRequest):
    project_id: str
    output_path: str
    overwrite: bool = False
    destructive_confirmation: bool = False


class CreateSnapshotRequest(CommonToolRequest):
    project_id: str
    reason: Literal["manual", "milestone", "pre_destructive_change"] = "manual"


class GetProjectInfoRequest(CommonToolRequest):
    project_id: str


class RollbackSnapshotRequest(CommonToolRequest):
    project_id: str
    snapshot_id: str
    destructive_confirmation: bool = False


def _project_failed_result(request_id: str, tool_name: str, code: str, message: str):  # type: ignore[no-untyped-def]
    return failed_result(
        request_id=request_id,
        tool_name=tool_name,
        summary=message,
        errors=[f"{code}: {message}"],
    )


async def create_project(context, request: CreateProjectRequest):  # type: ignore[no-untyped-def]
    context.active_project_id = None
    try:
        workspace_root = context.workspace.choose_workspace_root(request.workspace_root)
        project_id = new_id("project")
        project_paths = context.workspace.plan_project_paths(project_id, request.name, workspace_root)
        context.workspace.ensure_project_layout(project_paths)
        bridge_result = await context.bridge.invoke(
            "create_project",
            {
                "project_id": project_id,
                "name": request.name,
                "template_type": request.template_name,
                "blend_file_path": str(project_paths.blend_file_path),
                "unit_scale": request.unit_scale,
                "active_scene_name": request.active_scene_name,
            },
        )
        blend_file_path = context.workspace.canonicalize_existing_path(
            bridge_result["blend_file_path"],
            allowed_extensions=[".blend"],
        )
    except ControllerBridgeError as exc:
        return _project_failed_result(request.request_id, "create_project", exc.code, exc.message)
    except ValueError as exc:
        return _project_failed_result(request.request_id, "create_project", "validation_error", str(exc))
    actual_workspace_root = context.workspace.owning_workspace_root(blend_file_path)
    existing_record = context.projects.get_by_blend_path(str(blend_file_path))
    if existing_record is not None:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_project",
            summary="Target .blend path is already managed by another project.",
            errors=["policy_violation: target path is already owned by another project"],
        )
    context.projects.create(
        project_id=project_id,
        name=request.name,
        blend_file_path=str(blend_file_path),
        workspace_root=str(actual_workspace_root),
        template_type=request.template_name,
        unit_scale=request.unit_scale,
        active_scene_name=bridge_result["active_scene_name"],
        status="active",
    )
    context.active_project_id = project_id
    return success_result(
        request_id=request.request_id,
        tool_name="create_project",
        summary=f"Created project {request.name}.",
        file_paths=[str(blend_file_path)],
        project_id=project_id,
        blend_file_path=str(blend_file_path),
        project={
            "project_id": project_id,
            "name": request.name,
            "blend_file_path": str(blend_file_path),
            "workspace_root": str(actual_workspace_root),
        },
    )


async def open_project(context, request: OpenProjectRequest):  # type: ignore[no-untyped-def]
    context.active_project_id = None
    try:
        blend_file_path = context.workspace.canonicalize_existing_path(
            request.blend_file_path,
            allowed_extensions=[".blend"],
        )
        bridge_result = await context.bridge.invoke(
            "open_project",
            {"blend_file_path": str(blend_file_path)},
        )
        opened_blend_file_path = context.workspace.canonicalize_existing_path(
            bridge_result.get("blend_file_path", str(blend_file_path)),
            allowed_extensions=[".blend"],
        )
        workspace_root = context.workspace.owning_workspace_root(opened_blend_file_path)
        runtime_project_id = bridge_result.get("project_id")
        record = context.projects.get_by_blend_path(str(opened_blend_file_path)) or context.projects.get_by_blend_path(str(blend_file_path))
        runtime_record = context.projects.get(str(runtime_project_id)) if runtime_project_id else None
    except ControllerBridgeError as exc:
        context.active_project_id = None
        return failed_result(
            request_id=request.request_id,
            tool_name="open_project",
            summary=exc.message,
            errors=[f"{exc.code}: {exc.message}"],
        )
    except ValueError as exc:
        context.active_project_id = None
        return failed_result(
            request_id=request.request_id,
            tool_name="open_project",
            summary=str(exc),
            errors=[f"validation_error: {exc}"],
        )
    if record is not None and runtime_project_id and record.project_id != str(runtime_project_id):
        context.active_project_id = None
        return failed_result(
            request_id=request.request_id,
            tool_name="open_project",
            summary="Managed project path conflicts with the embedded project identity.",
            errors=["validation_error: managed project path conflicts with embedded project identity"],
        )
    if record is None:
        record = runtime_record
    project_name = str(bridge_result.get("project_name") or opened_blend_file_path.stem)
    template_type = str(bridge_result.get("template_type") or (record.template_type if record is not None else "imported"))
    unit_scale = float(bridge_result.get("unit_scale") or (record.unit_scale if record is not None else 1.0))
    active_scene_name = str(bridge_result.get("active_scene_name") or (record.active_scene_name if record is not None else "Scene"))
    if record is None:
        project_id = runtime_project_id or new_id("project")
        record = context.projects.create(
            project_id=project_id,
            name=project_name,
            blend_file_path=str(opened_blend_file_path),
            workspace_root=str(workspace_root),
            template_type=template_type,
            unit_scale=unit_scale,
            active_scene_name=active_scene_name,
            status="active",
            dirty_flag=bool(bridge_result.get("dirty", False)),
        )
    else:
        context.projects.refresh_metadata(
            record.project_id,
            name=project_name,
            blend_file_path=str(opened_blend_file_path),
            workspace_root=str(workspace_root),
            template_type=template_type,
            unit_scale=unit_scale,
            active_scene_name=active_scene_name,
            dirty_flag=bool(bridge_result.get("dirty", False)),
        )
    context.active_project_id = record.project_id
    return success_result(
        request_id=request.request_id,
        tool_name="open_project",
        summary=f"Opened project {record.name}.",
        file_paths=[str(opened_blend_file_path)],
        project_id=record.project_id,
        project={
            "project_id": record.project_id,
            "name": project_name,
            "blend_file_path": str(opened_blend_file_path),
            "active_scene_name": active_scene_name,
            "object_count": bridge_result["object_count"],
            "dirty": bool(bridge_result.get("dirty", False)),
        },
    )


async def save_project(context, request: SaveProjectRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    try:
        blend_file_path = context.workspace.canonicalize_output_path(
            project.blend_file_path,
            allowed_extensions=[".blend"],
        )
        started = perf_counter()
        bridge_result = await context.bridge.invoke(
            "save_project",
            {
                "project_id": request.project_id,
                "blend_file_path": str(blend_file_path),
            },
        )
        duration_ms = int((perf_counter() - started) * 1000)
        saved_blend_file_path = context.workspace.canonicalize_existing_path(
            bridge_result["blend_file_path"],
            allowed_extensions=[".blend"],
        )
        existing_record = context.projects.get_by_blend_path(str(saved_blend_file_path))
        if existing_record is not None and existing_record.project_id != project.project_id:
            return failed_result(
                request_id=request.request_id,
                tool_name="save_project",
                summary="Returned .blend path is already managed by another project.",
                errors=["policy_violation: returned path is already owned by another project"],
            )
        context.projects.update_storage(
            project.project_id,
            blend_file_path=str(saved_blend_file_path),
            workspace_root=str(context.workspace.owning_workspace_root(saved_blend_file_path)),
        )
    except ControllerBridgeError as exc:
        return _project_failed_result(request.request_id, "save_project", exc.code, exc.message)
    except ValueError as exc:
        return _project_failed_result(request.request_id, "save_project", "validation_error", str(exc))
    context.projects.mark_saved(project.project_id, bridge_result["active_scene_name"])
    return success_result(
        request_id=request.request_id,
        tool_name="save_project",
        summary=f"Saved project {project.name}.",
        file_paths=[str(saved_blend_file_path)],
        project_id=project.project_id,
        blend_file_path=str(saved_blend_file_path),
        duration_ms=duration_ms,
    )


async def save_project_as(context, request: SaveProjectAsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    try:
        output_path = context.workspace.canonicalize_output_path(
            request.output_path,
            allowed_extensions=[".blend"],
        )
    except ValueError as exc:
        return _project_failed_result(request.request_id, "save_project_as", "validation_error", str(exc))
    existing_record = context.projects.get_by_blend_path(str(output_path))
    if existing_record is not None and existing_record.project_id != project.project_id:
        return failed_result(
            request_id=request.request_id,
            tool_name="save_project_as",
            summary="Target .blend path is already managed by another project.",
            errors=["policy_violation: target path is already owned by another project"],
        )
    if output_path.exists() and not request.overwrite:
        return failed_result(
            request_id=request.request_id,
            tool_name="save_project_as",
            summary="Target .blend file already exists.",
            errors=["policy_violation: overwrite was not permitted"],
        )
    try:
        started = perf_counter()
        bridge_result = await context.bridge.invoke(
            "save_project",
            {
                "project_id": request.project_id,
                "blend_file_path": str(output_path),
            },
        )
        duration_ms = int((perf_counter() - started) * 1000)
        saved_blend_file_path = context.workspace.canonicalize_existing_path(
            bridge_result["blend_file_path"],
            allowed_extensions=[".blend"],
        )
        actual_record = context.projects.get_by_blend_path(str(saved_blend_file_path))
        if actual_record is not None and actual_record.project_id != project.project_id:
            return failed_result(
                request_id=request.request_id,
                tool_name="save_project_as",
                summary="Returned .blend path is already managed by another project.",
                errors=["policy_violation: returned path is already owned by another project"],
            )
    except ControllerBridgeError as exc:
        return _project_failed_result(request.request_id, "save_project_as", exc.code, exc.message)
    except ValueError as exc:
        return _project_failed_result(request.request_id, "save_project_as", "validation_error", str(exc))
    context.projects.update_storage(
        project.project_id,
        blend_file_path=str(saved_blend_file_path),
        workspace_root=str(context.workspace.owning_workspace_root(saved_blend_file_path)),
    )
    context.projects.mark_saved(project.project_id, bridge_result["active_scene_name"])
    return success_result(
        request_id=request.request_id,
        tool_name="save_project_as",
        summary=f"Saved project {project.name} as {output_path.name}.",
        file_paths=[str(saved_blend_file_path)],
        project_id=project.project_id,
        blend_file_path=str(saved_blend_file_path),
        duration_ms=duration_ms,
    )


async def create_snapshot(context, request: CreateSnapshotRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    project_paths = project_paths_for_record(context, project)
    context.workspace.ensure_project_layout(project_paths)
    snapshot_id = new_id("snapshot")
    snapshot_path = project_paths.snapshot_dir / f"{snapshot_id}.blend"
    bridge_result = await context.bridge.invoke(
        "create_snapshot",
        {
            "project_id": project.project_id,
            "snapshot_path": str(snapshot_path),
        },
    )
    canonical_snapshot_path = context.workspace.canonicalize_existing_path(
        bridge_result["snapshot_path"],
        allowed_extensions=[".blend"],
    )
    context.snapshots.create(
        snapshot_id=snapshot_id,
        project_id=project.project_id,
        source_operation_id=None,
        reason=request.reason,
        snapshot_path=str(canonical_snapshot_path),
    )
    return success_result(
        request_id=request.request_id,
        tool_name="create_snapshot",
        summary=f"Created snapshot for {project.name}.",
        file_paths=[str(canonical_snapshot_path)],
        project_id=project.project_id,
        snapshot_id=snapshot_id,
        snapshot_path=str(canonical_snapshot_path),
    )


async def get_project_info(context, request: GetProjectInfoRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    bridge_result = await context.bridge.invoke(
        "get_project_info",
        {"project_id": project.project_id},
        read_only=True,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="get_project_info",
        summary=f"Loaded project metadata for {project.name}.",
        project_id=project.project_id,
        project={
            "project_id": project.project_id,
            "name": project.name,
            "blend_file_path": project.blend_file_path,
            "active_scene_name": bridge_result["active_scene_name"],
            "unit_scale": bridge_result["unit_scale"],
            "object_count": bridge_result["object_count"],
            "dirty": bridge_result["dirty"],
        },
    )


async def rollback_to_snapshot(context, request: RollbackSnapshotRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    snapshot = context.snapshots.get(request.snapshot_id)
    if snapshot is None or snapshot.project_id != project.project_id:
        return failed_result(
            request_id=request.request_id,
            tool_name="rollback_to_snapshot",
            summary="Snapshot was not found for the requested project.",
            errors=["target_not_found: snapshot_id"],
        )
    snapshot_path = context.workspace.canonicalize_existing_path(
        snapshot.snapshot_path,
        allowed_extensions=[".blend"],
    )
    target_blend_file_path = context.workspace.canonicalize_output_path(
        project.blend_file_path,
        allowed_extensions=[".blend"],
    )
    bridge_result = await context.bridge.invoke(
        "restore_snapshot",
        {
            "project_id": project.project_id,
            "snapshot_path": str(snapshot_path),
            "target_blend_file_path": str(target_blend_file_path),
        },
    )
    restored_blend_file_path = context.workspace.canonicalize_existing_path(
        bridge_result["blend_file_path"],
        allowed_extensions=[".blend"],
    )
    context.projects.update_storage(
        project.project_id,
        blend_file_path=str(restored_blend_file_path),
        workspace_root=str(context.workspace.owning_workspace_root(restored_blend_file_path)),
    )
    context.projects.mark_saved(project.project_id, bridge_result["active_scene_name"])
    context.active_project_id = project.project_id
    return success_result(
        request_id=request.request_id,
        tool_name="rollback_to_snapshot",
        summary=f"Rolled back project {project.name} to snapshot {request.snapshot_id}.",
        file_paths=[str(restored_blend_file_path)],
        project_id=project.project_id,
        snapshot_id=request.snapshot_id,
        blend_file_path=str(restored_blend_file_path),
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    for definition in (
        ("create_project", "Create a new Blender project inside an allowlisted workspace root.", CreateProjectRequest, create_project, False),
        ("open_project", "Open an existing Blender project from an allowlisted path.", OpenProjectRequest, open_project, False),
        ("save_project", "Save the active Blender project in place.", SaveProjectRequest, save_project, False),
        ("save_project_as", "Save the active Blender project to a new path.", SaveProjectAsRequest, save_project_as, False),
        ("create_snapshot", "Create a reversible project snapshot.", CreateSnapshotRequest, create_snapshot, False),
        ("get_project_info", "Return current project metadata.", GetProjectInfoRequest, get_project_info, True),
        ("rollback_to_snapshot", "Restore the project to a recorded snapshot.", RollbackSnapshotRequest, rollback_to_snapshot, False),
    ):
        name, description, input_model, handler, read_only = definition
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="project",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )
