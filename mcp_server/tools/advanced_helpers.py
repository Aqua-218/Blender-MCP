from __future__ import annotations

from base64 import b64decode
from pathlib import Path
from typing import Any

from mcp_server.models.common import CommonToolResult, failed_result
from mcp_server.serialization import json_loads
from mcp_server.tools.helpers import require_project, sync_named_entity
from mcp_server.tools.object import (
    AssignCollectionRequest,
    TargetedObjectRequest,
    TransformObjectRequest,
    assign_collection,
    duplicate_object,
    transform_object,
)

_BLANK_PNG = b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/w8AAgMBAQEA4q0AAAAASUVORK5CYII="
)


def retag_result(result: CommonToolResult, tool_name: str, *, summary: str | None = None, **extra: Any) -> CommonToolResult:
    payload = result.model_dump()
    payload["tool_name"] = tool_name
    if summary is not None:
        payload["summary"] = summary
    payload.update(extra)
    return type(result).model_validate(payload)


def list_entity_specs(context, project_id: str, entity_type: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    return [json_loads(record.spec_json) for record in context.entities.list_by_type(project_id, entity_type)]


def load_entity_spec(
    context,
    entity_id: str,
    *,
    expected_type: str | None = None,
) -> dict[str, Any] | None:  # type: ignore[no-untyped-def]
    record = context.entities.get(entity_id)
    if record is None:
        return None
    if expected_type is not None and record.entity_type != expected_type:
        return None
    return json_loads(record.spec_json)


def save_metadata_entity(
    context,
    *,
    project_id: str,
    entity_id: str,
    entity_type: str,
    name: str,
    spec: dict[str, Any],
) -> dict[str, Any]:  # type: ignore[no-untyped-def]
    sync_named_entity(
        context,
        project_id,
        entity_id,
        entity_type,
        name,
        spec,
    )
    return spec


async def duplicate_asset_objects(
    context,
    *,
    request_id: str,
    project_id: str,
    tool_name: str,
    asset_id: str,
    location_offset: list[float],
    rotation_offset: list[float] | None = None,
    scale_multiplier: list[float] | None = None,
    collection_name: str | None = None,
) -> dict[str, Any] | CommonToolResult:  # type: ignore[no-untyped-def]
    require_project(context, project_id)
    asset = load_entity_spec(context, asset_id, expected_type="asset")
    if asset is None:
        return failed_result(
            request_id=request_id,
            tool_name=tool_name,
            summary=f"Asset '{asset_id}' was not found.",
            errors=[f"target_not_found: asset '{asset_id}' does not exist"],
        )

    source_object_ids: list[str] = []
    parts: list[dict[str, Any]] = []
    for part in list_entity_specs(context, project_id, "part"):
        if part.get("metadata", {}).get("asset_id") != asset_id:
            continue
        parts.append(part)
        for object_id in part.get("metadata", {}).get("target_ids", []):
            if object_id not in source_object_ids:
                source_object_ids.append(str(object_id))

    if not source_object_ids:
        return failed_result(
            request_id=request_id,
            tool_name=tool_name,
            summary=f"Asset '{asset_id}' has no placeable objects.",
            errors=[f"target_not_found: asset '{asset_id}' has no placeable objects"],
        )

    rotation_delta = rotation_offset or [0.0, 0.0, 0.0]
    scale_factors = scale_multiplier or [1.0, 1.0, 1.0]
    created_object_ids: list[str] = []
    objects: list[dict[str, Any]] = []

    for source_object_id in source_object_ids:
        duplicated = await duplicate_object(
            context,
            TargetedObjectRequest(
                request_id=request_id,
                project_id=project_id,
                target_id=source_object_id,
            ),
        )
        if duplicated.status != "success":
            return retag_result(duplicated, tool_name)

        duplicate_object_id = str(duplicated.created_object_ids[0])
        duplicate_object_spec = duplicated.model_dump().get("objects", [{}])[0]
        updated_location = [
            float(duplicate_object_spec.get("location", [0.0, 0.0, 0.0])[index]) + float(location_offset[index])
            for index in range(3)
        ]
        updated_rotation = [
            float(duplicate_object_spec.get("rotation", [0.0, 0.0, 0.0])[index]) + float(rotation_delta[index])
            for index in range(3)
        ]
        updated_scale = [
            float(duplicate_object_spec.get("scale", [1.0, 1.0, 1.0])[index]) * float(scale_factors[index])
            for index in range(3)
        ]
        transformed = await transform_object(
            context,
            TransformObjectRequest(
                request_id=request_id,
                project_id=project_id,
                target_id=duplicate_object_id,
                location=updated_location,
                rotation=updated_rotation,
                scale=updated_scale,
            ),
        )
        if transformed.status != "success":
            return retag_result(transformed, tool_name)

        final_object = transformed.model_dump()["object"]
        if collection_name is not None:
            assigned = await assign_collection(
                context,
                AssignCollectionRequest(
                    request_id=request_id,
                    project_id=project_id,
                    target_id=duplicate_object_id,
                    collection_name=collection_name,
                ),
            )
            if assigned.status != "success":
                return retag_result(assigned, tool_name)
            final_object = assigned.model_dump()["objects"][0]

        created_object_ids.append(duplicate_object_id)
        objects.append(final_object)

    return {
        "asset": asset,
        "parts": parts,
        "created_object_ids": created_object_ids,
        "objects": objects,
    }


def write_placeholder_png(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(_BLANK_PNG)