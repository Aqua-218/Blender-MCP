from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.common import CommonToolRequest, failed_result, success_result
from mcp_server.serialization import json_loads
from mcp_server.tools.helpers import (
    project_paths_for_record,
    require_project,
    resolve_target_ids,
    sync_entities,
)
from mcp_server.tools.qa import CheckExportReadinessRequest, check_export_readiness
from mcp_server.utils import new_id, slugify
from mcp_server.workspace import WorkspaceViolationError

ExportFormat = Literal["glb", "gltf", "fbx", "obj", "usd", "usdz", "stl"]
ExportProfileName = Literal["game", "web", "render", "concept", "print", "archive"]

_EXPORT_PROFILES: dict[str, dict[str, Any]] = {
    "game": {
        "default_format": "glb",
        "include_cameras": False,
        "include_lights": False,
        "axis_forward": "-Z",
        "axis_up": "Y",
        "apply_scale": 1.0,
    },
    "web": {
        "default_format": "glb",
        "include_cameras": False,
        "include_lights": False,
        "axis_forward": "-Z",
        "axis_up": "Y",
        "apply_scale": 1.0,
    },
    "render": {
        "default_format": "fbx",
        "include_cameras": True,
        "include_lights": True,
        "axis_forward": "-Z",
        "axis_up": "Y",
        "apply_scale": 1.0,
    },
    "concept": {
        "default_format": "gltf",
        "include_cameras": True,
        "include_lights": True,
        "axis_forward": "-Z",
        "axis_up": "Y",
        "apply_scale": 1.0,
    },
    "print": {
        "default_format": "stl",
        "include_cameras": False,
        "include_lights": False,
        "axis_forward": "Y",
        "axis_up": "Z",
        "apply_scale": 1.0,
    },
    "archive": {
        "default_format": "usd",
        "include_cameras": True,
        "include_lights": True,
        "axis_forward": "-Z",
        "axis_up": "Y",
        "apply_scale": 1.0,
    },
}

_FORMAT_WARNINGS: dict[str, list[str]] = {
    "gltf": ["glTF separate export may emit external sidecar files for textures and buffers."],
    "fbx": ["FBX export uses default axis and scale conversion; material and instancing fidelity may vary by importer."],
    "obj": ["OBJ export omits modern material graphs and does not preserve cameras or punctual lights."],
    "usd": ["USD export support varies by Blender runtime version and downstream importer capabilities."],
    "usdz": ["USDZ export support varies by Blender runtime version and may flatten advanced shader graphs."],
    "stl": ["STL export drops materials, cameras, and lights and is intended for geometry-only interchange."],
}


class ExportSceneRequest(CommonToolRequest):
    project_id: str
    output_path: str | None = None
    export_format: ExportFormat | None = None


class ExportAssetRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None
    output_path: str | None = None
    export_format: ExportFormat | None = None


class ExportWorldRequest(CommonToolRequest):
    project_id: str
    output_path: str | None = None
    export_format: ExportFormat | None = None


class SetExportProfileRequest(CommonToolRequest):
    project_id: str
    profile_name: ExportProfileName
    default_format: ExportFormat | None = None
    include_cameras: bool | None = None
    include_lights: bool | None = None
    axis_forward: str | None = None
    axis_up: str | None = None
    apply_scale: float | None = Field(default=None, gt=0)


class GetExportFormatsRequest(CommonToolRequest):
    project_id: str


class ImportAssetRequest(CommonToolRequest):
    project_id: str
    input_path: str
    name_prefix: str | None = None


def _export_extension(export_format: ExportFormat) -> str:
    if export_format == "gltf":
        return ".gltf"
    return f".{export_format}"


def _export_profile_entity_id(project_id: str) -> str:
    return f"export_profile_{project_id}"


def _load_export_profile(context, project_id: str) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    record = context.entities.get(_export_profile_entity_id(project_id))
    if record is None:
        profile = deepcopy(_EXPORT_PROFILES["game"])
        profile["profile_name"] = "game"
        return profile
    return json_loads(record.spec_json)


def _save_export_profile(context, project_id: str, profile: dict[str, Any]) -> None:  # type: ignore[no-untyped-def]
    context.entities.upsert(
        entity_id=_export_profile_entity_id(project_id),
        project_id=project_id,
        entity_type="export_profile",
        name=str(profile["profile_name"]),
        spec=profile,
    )


def _resolve_export_profile(context, project_id: str, requested_format: ExportFormat | None) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    profile = _load_export_profile(context, project_id)
    resolved = deepcopy(profile)
    resolved["export_format"] = requested_format or profile["default_format"]
    return resolved


def _lossy_mapping_warnings(export_settings: dict[str, Any]) -> list[str]:
    warnings = list(_FORMAT_WARNINGS.get(str(export_settings["export_format"]), []))
    if not export_settings.get("include_cameras", False):
        warnings.append("Camera export is disabled by the active export profile.")
    if not export_settings.get("include_lights", False):
        warnings.append("Light export is disabled by the active export profile.")
    return list(dict.fromkeys(warnings))


def _export_bridge_payload(project_id: str, output_path: Path, export_settings: dict[str, Any], *, target_ids: list[str] | None = None) -> dict[str, Any]:
    payload = {
        "project_id": project_id,
        "output_path": str(output_path),
        "export_format": export_settings["export_format"],
        "include_cameras": export_settings["include_cameras"],
        "include_lights": export_settings["include_lights"],
        "axis_forward": export_settings["axis_forward"],
        "axis_up": export_settings["axis_up"],
        "apply_scale": export_settings["apply_scale"],
    }
    if target_ids:
        payload["target_ids"] = target_ids
    return payload


def _project_scoped_output_path(export_dir: Path, raw_output_path: Path) -> Path:
    resolved_root = export_dir.resolve()
    relative_output_path = raw_output_path
    artifact_root_name = export_dir.parent.name
    if not raw_output_path.is_absolute() and raw_output_path.parts[:1] == (artifact_root_name,):
        relative_output_path = Path(*raw_output_path.parts[1:]) if len(raw_output_path.parts) > 1 else Path()
    candidate = raw_output_path.resolve(strict=False) if raw_output_path.is_absolute() else (export_dir / relative_output_path).resolve(strict=False)
    try:
        candidate.relative_to(resolved_root)
    except ValueError as exc:
        raise WorkspaceViolationError("Export output path must stay under the project's export directory.") from exc
    return candidate


async def export_scene(context, request: ExportSceneRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    readiness = await check_export_readiness(
        context,
        CheckExportReadinessRequest(request_id=request.request_id, project_id=project.project_id),
    )
    export_settings = _resolve_export_profile(context, project.project_id, request.export_format)
    export_format = export_settings["export_format"]
    blocked_formats = list(getattr(readiness, "blocked_export_formats", []))
    if export_format in blocked_formats:
        findings = list(getattr(readiness, "findings", []))
        return failed_result(
            request_id=request.request_id,
            tool_name="export_scene",
            summary="Export readiness check reported blocking issues.",
            errors=["validation_error: export readiness check reported blocking issues"],
            blocked_export_formats=blocked_formats,
            findings=findings,
        )
    project_paths = project_paths_for_record(context, project)
    context.workspace.ensure_project_layout(project_paths)
    extension = _export_extension(export_format)
    explicit_output_path: str | Path | None = request.output_path
    if request.output_path:
        explicit_output_path = _project_scoped_output_path(project_paths.export_dir, Path(request.output_path))
    output_path = (
        context.workspace.canonicalize_output_path(explicit_output_path, allowed_extensions=[extension])
        if explicit_output_path is not None
        else context.workspace.canonicalize_output_path(
            project_paths.export_dir / f"{slugify(request.request_id)}{extension}",
            allowed_extensions=[extension],
        )
    )
    result = await context.bridge.invoke(
        "export_scene",
        _export_bridge_payload(project.project_id, output_path, export_settings),
    )
    returned_output_path = context.workspace.canonicalize_output_path(result["output_path"], allowed_extensions=[extension])
    if returned_output_path != output_path:
        return failed_result(
            request_id=request.request_id,
            tool_name="export_scene",
            summary="Controller returned an unexpected export output path.",
            errors=["validation_error: controller returned an unexpected export output path"],
        )
    warnings = list(dict.fromkeys([*_lossy_mapping_warnings(export_settings), *list(result.get("warnings", []))]))
    export_record = context.export_records.create(
        export_id=new_id("export"),
        project_id=project.project_id,
        entity_id=None,
        format=export_format,
        output_path=str(returned_output_path),
        metadata={
            "scope": "scene",
            "object_count": int(result.get("object_count", 0)),
            "export_profile": export_settings["profile_name"],
            "include_cameras": export_settings["include_cameras"],
            "include_lights": export_settings["include_lights"],
        },
        warnings=warnings,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="export_scene",
        summary=f"Exported scene to {returned_output_path.name}.",
        file_paths=[str(returned_output_path)],
        project_id=project.project_id,
        export_id=export_record.export_id,
        export_format=export_format,
        export_profile=export_settings["profile_name"],
        object_count=int(result.get("object_count", 0)),
        warnings=warnings,
    )


async def export_asset(context, request: ExportAssetRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    readiness = await check_export_readiness(
        context,
        CheckExportReadinessRequest(request_id=request.request_id, project_id=project.project_id),
    )
    export_settings = _resolve_export_profile(context, project.project_id, request.export_format)
    export_format = export_settings["export_format"]
    blocked_formats = list(getattr(readiness, "blocked_export_formats", []))
    if export_format in blocked_formats:
        findings = list(getattr(readiness, "findings", []))
        return failed_result(
            request_id=request.request_id,
            tool_name="export_asset",
            summary="Export readiness check reported blocking issues.",
            errors=["validation_error: export readiness check reported blocking issues"],
            blocked_export_formats=blocked_formats,
            findings=findings,
        )
    project_paths = project_paths_for_record(context, project)
    context.workspace.ensure_project_layout(project_paths)
    extension = _export_extension(export_format)
    target_ids = await resolve_target_ids(
        context,
        project_id=project.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
        tag=request.tag,
        collection_name=request.match_collection_name,
    )
    explicit_output_path: str | Path | None = request.output_path
    if request.output_path:
        explicit_output_path = _project_scoped_output_path(project_paths.export_dir, Path(request.output_path))
    output_path = (
        context.workspace.canonicalize_output_path(explicit_output_path, allowed_extensions=[extension])
        if explicit_output_path is not None
        else context.workspace.canonicalize_output_path(
            project_paths.export_dir / f"{slugify(request.request_id)}{extension}",
            allowed_extensions=[extension],
        )
    )
    result = await context.bridge.invoke(
        "export_scene",
        _export_bridge_payload(project.project_id, output_path, export_settings, target_ids=target_ids),
    )
    returned_output_path = context.workspace.canonicalize_output_path(result["output_path"], allowed_extensions=[extension])
    if returned_output_path != output_path:
        return failed_result(
            request_id=request.request_id,
            tool_name="export_asset",
            summary="Controller returned an unexpected export output path.",
            errors=["validation_error: controller returned an unexpected export output path"],
        )
    warnings = list(dict.fromkeys([*_lossy_mapping_warnings(export_settings), *list(result.get("warnings", []))]))
    export_record = context.export_records.create(
        export_id=new_id("export"),
        project_id=project.project_id,
        entity_id=target_ids[0] if len(target_ids) == 1 else None,
        format=export_format,
        output_path=str(returned_output_path),
        metadata={
            "scope": "asset",
            "target_ids": target_ids,
            "object_count": int(result.get("object_count", len(target_ids))),
            "export_profile": export_settings["profile_name"],
        },
        warnings=warnings,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="export_asset",
        summary=f"Exported {len(target_ids)} target objects to {returned_output_path.name}.",
        file_paths=[str(returned_output_path)],
        project_id=project.project_id,
        export_id=export_record.export_id,
        export_format=export_format,
        export_profile=export_settings["profile_name"],
        object_count=int(result.get("object_count", len(target_ids))),
        exported_object_ids=target_ids,
        warnings=warnings,
    )


async def export_world(context, request: ExportWorldRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    export = await export_scene(
        context,
        ExportSceneRequest(
            request_id=request.request_id,
            project_id=project.project_id,
            output_path=request.output_path,
            export_format=request.export_format,
        ),
    )
    result = export.model_dump()
    if result["status"] != "success":
        return export
    result["tool_name"] = "export_world"
    result["summary"] = f"Exported world to {Path(result['file_paths'][0]).name}."
    result["world_export"] = True
    return type(export).model_validate(result)


async def set_export_profile(context, request: SetExportProfileRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    profile = deepcopy(_EXPORT_PROFILES[request.profile_name])
    profile["profile_name"] = request.profile_name
    for key in ("default_format", "include_cameras", "include_lights", "axis_forward", "axis_up", "apply_scale"):
        value = getattr(request, key)
        if value is not None:
            profile[key] = value
    _save_export_profile(context, project.project_id, profile)
    return success_result(
        request_id=request.request_id,
        tool_name="set_export_profile",
        summary=f"Set export profile to {request.profile_name}.",
        project_id=project.project_id,
        export_profile=profile,
    )


async def get_export_formats(context, request: GetExportFormatsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    active_profile = _load_export_profile(context, project.project_id)
    return success_result(
        request_id=request.request_id,
        tool_name="get_export_formats",
        summary="Retrieved supported export formats and profile defaults.",
        project_id=project.project_id,
        supported_formats=["glb", "gltf", "fbx", "obj", "usd", "usdz", "stl"],
        export_profiles={name: deepcopy(settings) for name, settings in _EXPORT_PROFILES.items()},
        active_profile=active_profile,
    )


async def import_asset(context, request: ImportAssetRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    input_path = context.workspace.canonicalize_existing_path(
        request.input_path,
        allowed_extensions=context.settings.allowed_import_extensions,
    )
    result = await context.bridge.invoke(
        "import_asset",
        {
            "project_id": project.project_id,
            "input_path": str(input_path),
            "name_prefix": request.name_prefix,
        },
    )
    objects = list(result.get("objects", []))
    if not objects:
        return failed_result(
            request_id=request.request_id,
            tool_name="import_asset",
            summary="Import operation did not create any objects.",
            errors=["validation_error: import operation did not create any objects"],
        )
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    sync_entities(context, project.project_id, objects)
    return success_result(
        request_id=request.request_id,
        tool_name="import_asset",
        summary=f"Imported {len(objects)} objects from {input_path.name}.",
        project_id=project.project_id,
        created_object_ids=[item["object_id"] for item in objects],
        file_paths=[str(input_path)],
        objects=objects,
        imported_count=len(objects),
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("export_scene", "Export the full scene to a project-scoped output path.", ExportSceneRequest, export_scene, False),
        ("export_asset", "Export selected target objects to a project-scoped output path.", ExportAssetRequest, export_asset, False),
        ("export_world", "Export the current world payload to a project-scoped output path.", ExportWorldRequest, export_world, False),
        ("import_asset", "Import an external asset file into the active scene.", ImportAssetRequest, import_asset, False),
        ("set_export_profile", "Set the active export profile and default format behavior.", SetExportProfileRequest, set_export_profile, False),
        ("get_export_formats", "List supported export formats and export profile defaults.", GetExportFormatsRequest, get_export_formats, True),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="asset_io",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )