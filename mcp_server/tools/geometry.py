from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.bridge import ControllerBridgeError
from mcp_server.models.common import CommonToolRequest, failed_result, success_result
from mcp_server.tools.helpers import require_project, sync_entities


class CreatePrimitiveRequest(CommonToolRequest):
    project_id: str
    primitive_type: Literal[
        "cube",
        "uv_sphere",
        "ico_sphere",
        "cylinder",
        "cone",
        "torus",
        "plane",
        "grid",
        "circle",
    ]
    name: str | None = None
    location: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    scale: list[float] = Field(default_factory=lambda: [1.0, 1.0, 1.0])
    collection_name: str = "Scene Collection"
    tags: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


class CreateCustomMeshRequest(CommonToolRequest):
    project_id: str
    name: str
    vertices: list[list[float]]
    edges: list[list[int]] = Field(default_factory=list)
    faces: list[list[int]] = Field(default_factory=list)
    collection_name: str = "Scene Collection"
    tags: list[str] = Field(default_factory=list)


class CreateCurveRequest(CommonToolRequest):
    project_id: str
    name: str
    curve_type: Literal["bezier", "path", "polyline"]
    points: list[list[float]]
    resolution: int = 12
    location: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    collection_name: str = "Scene Collection"
    tags: list[str] = Field(default_factory=list)


class CreateTextRequest(CommonToolRequest):
    project_id: str
    name: str
    text: str
    font_size: float = 1.0
    extrusion: float = 0.0
    bevel_depth: float = 0.0
    location: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    rotation: list[float] = Field(default_factory=lambda: [0.0, 0.0, 0.0])
    collection_name: str = "Scene Collection"
    tags: list[str] = Field(default_factory=list)


class MeshEditRequest(CommonToolRequest):
    project_id: str
    target_id: str
    vertices: list[list[float]] | None = None
    edges: list[list[int]] | None = None
    faces: list[list[int]] | None = None


def _validate_vertices(vertices: list[list[float]]) -> list[str]:
    errors: list[str] = []
    for index, vertex in enumerate(vertices):
        if len(vertex) != 3:
            errors.append(f"validation_error: vertex {index} must contain exactly 3 coordinates")
    return errors


def _validate_mesh_topology(
    vertices: list[list[float]],
    edges: list[list[int]],
    faces: list[list[int]],
) -> list[str]:
    errors = _validate_vertices(vertices)
    vertex_count = len(vertices)
    for index, edge in enumerate(edges):
        if len(edge) != 2:
            errors.append(f"validation_error: edge {index} must reference exactly 2 vertices")
            continue
        if len(set(edge)) != 2:
            errors.append(f"validation_error: edge {index} must reference 2 distinct vertices")
        if any(vertex_index < 0 or vertex_index >= vertex_count for vertex_index in edge):
            errors.append(f"validation_error: edge {index} references an out-of-range vertex")
    for index, face in enumerate(faces):
        if len(face) < 3:
            errors.append(f"validation_error: face {index} must reference at least 3 vertices")
            continue
        if len(set(face)) != len(face):
            errors.append(f"validation_error: face {index} contains duplicate vertex references")
        if any(vertex_index < 0 or vertex_index >= vertex_count for vertex_index in face):
            errors.append(f"validation_error: face {index} references an out-of-range vertex")
    return errors


class ExtrudeMeshRequest(CommonToolRequest):
    project_id: str
    target_id: str
    distance: float = 0.1


class BevelEdgesRequest(CommonToolRequest):
    project_id: str
    target_id: str
    width: float = 0.05
    segments: int = 1


class MergeVerticesRequest(CommonToolRequest):
    project_id: str
    target_id: str
    threshold: float = 0.0001


class RecalculateNormalsRequest(CommonToolRequest):
    project_id: str
    target_id: str


async def _mutation(context, request: BaseModel, command: str, *, summary: str, created: bool = False):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    try:
        result = await context.bridge.invoke(command, request.model_dump(exclude_none=True))
    except ControllerBridgeError as exc:
        if exc.code in {"validation_error", "target_not_found", "unsupported_feature"}:
            return failed_result(
                request_id=request.request_id,
                tool_name=command,
                summary=exc.message,
                errors=[f"{exc.code}: {exc.message}"],
            )
        raise
    context.projects.mark_dirty(project.project_id, project.active_scene_name)
    objects = result.get("objects") or ([result["object"]] if "object" in result else [])
    if objects:
        sync_entities(context, project.project_id, objects)
    return success_result(
        request_id=request.request_id,
        tool_name=command,
        summary=summary,
        project_id=project.project_id,
        created_object_ids=result.get("created_object_ids", []) if created else [],
        modified_object_ids=result.get("modified_object_ids", []) if not created else [],
        objects=objects,
    )


async def create_primitive(context, request: CreatePrimitiveRequest):  # type: ignore[no-untyped-def]
    return await _mutation(context, request, "create_primitive", summary="Created primitive geometry.", created=True)


async def create_custom_mesh(context, request: CreateCustomMeshRequest):  # type: ignore[no-untyped-def]
    errors = _validate_mesh_topology(request.vertices, request.edges, request.faces)
    if errors:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_custom_mesh",
            summary="Custom mesh topology validation failed.",
            errors=errors,
        )
    return await _mutation(context, request, "create_custom_mesh", summary="Created custom mesh.", created=True)


async def create_curve(context, request: CreateCurveRequest):  # type: ignore[no-untyped-def]
    if len(request.points) < 2:
        return failed_result(
            request_id=request.request_id,
            tool_name="create_curve",
            summary="Curve creation requires at least two points.",
            errors=["validation_error: at least two points are required"],
        )
    if any(len(point) != 3 for point in request.points):
        return failed_result(
            request_id=request.request_id,
            tool_name="create_curve",
            summary="Curve creation requires 3D points.",
            errors=["validation_error: every curve point must contain exactly 3 coordinates"],
        )
    return await _mutation(context, request, "create_curve", summary="Created curve object.", created=True)


async def create_text(context, request: CreateTextRequest):  # type: ignore[no-untyped-def]
    return await _mutation(context, request, "create_text", summary="Created text object.", created=True)


async def edit_mesh(context, request: MeshEditRequest):  # type: ignore[no-untyped-def]
    if request.vertices is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="edit_mesh",
            summary="edit_mesh requires vertices so topology can be validated consistently.",
            errors=["validation_error: vertices are required for edit_mesh"],
        )
    edges = request.edges or []
    faces = request.faces or []
    errors = _validate_mesh_topology(request.vertices, edges, faces)
    if errors:
        return failed_result(
            request_id=request.request_id,
            tool_name="edit_mesh",
            summary="Mesh edit topology validation failed.",
            errors=errors,
        )
    normalized_request = request.model_copy(update={"edges": edges, "faces": faces})
    return await _mutation(context, normalized_request, "edit_mesh", summary="Edited mesh geometry.")


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool, bool]] = [
        ("create_primitive", "Create supported primitive geometry.", CreatePrimitiveRequest, create_primitive, False, False),
        ("create_custom_mesh", "Create a mesh from explicit vertices, edges, and faces.", CreateCustomMeshRequest, create_custom_mesh, False, False),
        ("create_curve", "Create a Bezier, path, or polyline curve.", CreateCurveRequest, create_curve, False, False),
        ("create_text", "Create a 3D text object.", CreateTextRequest, create_text, False, False),
        ("edit_mesh", "Replace mesh geometry data with validated topology.", MeshEditRequest, edit_mesh, False, False),
        ("extrude_mesh", "Extrude mesh geometry on the target object.", ExtrudeMeshRequest, lambda c, r: _mutation(c, r, "extrude_mesh", summary="Extruded mesh geometry."), False, False),
        ("bevel_edges", "Apply a non-destructive bevel configuration to the target mesh.", BevelEdgesRequest, lambda c, r: _mutation(c, r, "bevel_edges", summary="Applied bevel settings."), False, False),
        ("merge_vertices", "Merge duplicate or near-duplicate vertices.", MergeVerticesRequest, lambda c, r: _mutation(c, r, "merge_vertices", summary="Merged vertices."), False, False),
        ("recalculate_normals", "Recalculate mesh normals consistently.", RecalculateNormalsRequest, lambda c, r: _mutation(c, r, "recalculate_normals", summary="Recalculated normals."), False, False),
    ]
    for name, description, input_model, handler, read_only, _created in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="geometry",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )
