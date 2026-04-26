from __future__ import annotations

from typing import Any, Literal

from pydantic import Field

from mcp_server.models.common import (
    CommonToolRequest,
    failed_result,
    success_result,
)
from mcp_server.serialization import json_dumps, json_loads
from mcp_server.tools.helpers import require_project
from mcp_server.utils import new_id

DetailLevel = Literal["draft", "base", "refined", "hero"]


class GeneratePartsRequest(CommonToolRequest):
    project_id: str
    target_ids: list[str] = Field(default_factory=list)
    part_hints: list[str] = Field(default_factory=list)


class AddPartRequest(CommonToolRequest):
    project_id: str
    name: str
    kind: str
    tags: list[str] = Field(default_factory=list)
    detail_level: DetailLevel = "base"
    parent_part_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RemovePartRequest(CommonToolRequest):
    project_id: str
    part_id: str


class UpdatePartDetailRequest(CommonToolRequest):
    project_id: str
    part_id: str
    detail_level: DetailLevel


class ListPartsRequest(CommonToolRequest):
    project_id: str


class ReplacePartRequest(CommonToolRequest):
    project_id: str
    part_id: str
    new_target_ids: list[str] = Field(default_factory=list)
    new_kind: str | None = None
    new_tags: list[str] | None = None
    new_detail_level: DetailLevel | None = None
    new_metadata: dict[str, Any] | None = None


def _parts_from_records(context, project_id: str) -> list[dict[str, Any]]:
    records = context.entities.list_by_type(project_id, "part")
    return [json_loads(r.spec_json) for r in records]


def _save_part(context, project_id: str, part: dict[str, Any]) -> None:
    existing = context.entities.get(part["part_id"])
    if existing is not None:
        context.entities.update_spec(part["part_id"], json_dumps(part))
    else:
        context.entities.create(
            entity_id=part["part_id"],
            project_id=project_id,
            entity_type="part",
            name=part["name"],
            spec_json=json_dumps(part),
        )


async def generate_parts(context, request: GeneratePartsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    parts: list[dict[str, Any]] = []
    hints = request.part_hints or ["body", "head", "limbs"]
    for hint in hints:
        part: dict[str, Any] = {
            "part_id": new_id("part"),
            "name": hint,
            "kind": hint,
            "parent_part_id": None,
            "tags": [],
            "detail_level": "base",
            "symmetrical_with": None,
            "metadata": {},
        }
        _save_part(context, project.project_id, part)
        parts.append(part)
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name="generate_parts",
        summary=f"Generated {len(parts)} semantic parts.",
        project_id=project.project_id,
        parts=parts,
    )


async def add_part(context, request: AddPartRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    part: dict[str, Any] = {
        "part_id": new_id("part"),
        "name": request.name,
        "kind": request.kind,
        "parent_part_id": request.parent_part_id,
        "tags": request.tags,
        "detail_level": request.detail_level,
        "symmetrical_with": None,
        "metadata": request.metadata,
    }
    _save_part(context, project.project_id, part)
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name="add_part",
        summary=f"Added part '{request.name}'.",
        project_id=project.project_id,
        part=part,
    )


async def remove_part(context, request: RemovePartRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    existing = context.entities.get(request.part_id)
    if existing is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="remove_part",
            summary=f"Part '{request.part_id}' not found.",
            errors=[f"target_not_found: part '{request.part_id}' does not exist"],
        )
    context.entities.delete(request.part_id)
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name="remove_part",
        summary=f"Removed part '{request.part_id}'.",
        project_id=project.project_id,
        removed_part_id=request.part_id,
    )


async def replace_part(context, request: ReplacePartRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    existing = context.entities.get(request.part_id)
    if existing is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="replace_part",
            summary=f"Part '{request.part_id}' not found.",
            errors=[f"target_not_found: part '{request.part_id}' does not exist"],
        )
    part = json_loads(existing.spec_json)
    if request.new_kind is not None:
        part["kind"] = request.new_kind
    if request.new_tags is not None:
        part["tags"] = request.new_tags
    if request.new_detail_level is not None:
        part["detail_level"] = request.new_detail_level
    if request.new_metadata is not None:
        part["metadata"] = request.new_metadata
    _save_part(context, project.project_id, part)
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name="replace_part",
        summary=f"Replaced part '{request.part_id}'.",
        project_id=project.project_id,
        part=part,
    )


async def update_part_detail(context, request: UpdatePartDetailRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    existing = context.entities.get(request.part_id)
    if existing is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="update_part_detail",
            summary=f"Part '{request.part_id}' not found.",
            errors=[f"target_not_found: part '{request.part_id}' does not exist"],
        )
    part = json_loads(existing.spec_json)
    previous_level = part.get("detail_level", "base")
    part["detail_level"] = request.detail_level
    _save_part(context, project.project_id, part)
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    return success_result(
        request_id=request.request_id,
        tool_name="update_part_detail",
        summary=f"Updated detail level from '{previous_level}' to '{request.detail_level}'.",
        project_id=project.project_id,
        part=part,
        previous_detail_level=previous_level,
    )


async def list_parts(context, request: ListPartsRequest):  # type: ignore[no-untyped-def]
    require_project(context, request.project_id)
    parts = _parts_from_records(context, request.project_id)
    return success_result(
        request_id=request.request_id,
        tool_name="list_parts",
        summary=f"Found {len(parts)} parts.",
        project_id=request.project_id,
        parts=parts,
        count=len(parts),
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    for name, description, handler, model, read_only in (
        (
            "generate_parts",
            "Auto-generate semantic part definitions for a project from mesh topology and hints.",
            generate_parts,
            GeneratePartsRequest,
            False,
        ),
        (
            "add_part",
            "Add a named semantic part to a project.",
            add_part,
            AddPartRequest,
            False,
        ),
        (
            "remove_part",
            "Remove a semantic part by part_id.",
            remove_part,
            RemovePartRequest,
            False,
        ),
        (
            "replace_part",
            "Replace or update a semantic part definition.",
            replace_part,
            ReplacePartRequest,
            False,
        ),
        (
            "update_part_detail",
            "Change the detail level of a semantic part (draft / base / refined / hero).",
            update_part_detail,
            UpdatePartDetailRequest,
            False,
        ),
        (
            "list_parts",
            "List all semantic parts registered for a project.",
            list_parts,
            ListPartsRequest,
            True,
        ),
    ):
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="parts",
                input_model=model,
                handler=handler,
                read_only=read_only,
            )
        )
