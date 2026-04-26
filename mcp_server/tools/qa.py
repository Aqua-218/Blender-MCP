from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from mcp_server.models.common import CommonToolRequest, failed_result, success_result
from mcp_server.tools.helpers import require_project, resolve_target_ids
from mcp_server.utils import new_id

Severity = Literal["info", "warning", "error"]


class InspectSceneRequest(CommonToolRequest):
    project_id: str


class InspectMeshRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None


class InspectObjectRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None


class InspectMaterialsRequest(CommonToolRequest):
    project_id: str


class InspectScaleRequest(CommonToolRequest):
    project_id: str
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None
    min_scale: float = 0.01
    max_scale: float = 100.0


class InspectNamingRequest(CommonToolRequest):
    project_id: str
    allowed_prefixes: list[str] = Field(default_factory=list)


class CheckPolycountRequest(CommonToolRequest):
    project_id: str
    max_triangles: int = Field(default=100_000, ge=1)


class CheckExportReadinessRequest(CommonToolRequest):
    project_id: str


class GenerateQAReportRequest(CommonToolRequest):
    project_id: str
    scope: Literal["scene", "mesh", "export"] = "scene"
    target_id: str | None = None
    target_ids: list[str] = Field(default_factory=list)
    names: list[str] = Field(default_factory=list)
    tag: str | None = None
    match_collection_name: str | None = None


def _summarize_severity(findings: list[dict[str, Any]]) -> dict[str, int]:
    summary = {"info": 0, "warning": 0, "error": 0}
    for finding in findings:
        severity = str(finding.get("severity", "info"))
        if severity in summary:
            summary[severity] += 1
    return summary


def _scene_findings(objects: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_type: dict[str, int] = {}
    total_vertices = 0
    total_faces = 0
    for item in objects:
        object_type = str(item.get("type", "UNKNOWN"))
        by_type[object_type] = by_type.get(object_type, 0) + 1
        if object_type == "MESH":
            data = item.get("data", {}) or {}
            total_vertices += len(data.get("vertices", []))
            total_faces += len(data.get("faces", []))

    findings: list[dict[str, Any]] = []
    if by_type.get("CAMERA", 0) == 0:
        findings.append(
            {
                "severity": "warning",
                "code": "missing_camera",
                "message": "Scene has no camera; render preview may fail or use an unintended viewpoint.",
            }
        )
    if by_type.get("LIGHT", 0) == 0:
        findings.append(
            {
                "severity": "warning",
                "code": "missing_light",
                "message": "Scene has no light; outputs may be underexposed depending on render settings.",
            }
        )
    if by_type.get("MESH", 0) == 0:
        findings.append(
            {
                "severity": "error",
                "code": "no_mesh_objects",
                "message": "Scene contains no mesh objects.",
            }
        )
    metrics = {
        "object_count": len(objects),
        "objects_by_type": by_type,
        "mesh_vertex_count": total_vertices,
        "mesh_face_count": total_faces,
    }
    return findings, metrics


def _mesh_findings(mesh_object: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    data = mesh_object.get("data", {}) or {}
    vertices = list(data.get("vertices", []))
    faces = list(data.get("faces", []))
    non_manifold_candidate_edges = len(data.get("edges", [])) == 0 and len(faces) > 0
    ngons = [face for face in faces if len(face) > 4]
    triangles = [face for face in faces if len(face) == 3]

    findings: list[dict[str, Any]] = []
    if len(vertices) == 0:
        findings.append({"severity": "error", "code": "empty_mesh", "message": "Mesh has no vertices."})
    if len(faces) == 0:
        findings.append({"severity": "warning", "code": "open_surface", "message": "Mesh has no faces."})
    if ngons:
        findings.append(
            {
                "severity": "warning",
                "code": "ngons_detected",
                "message": f"Mesh contains {len(ngons)} n-gons; consider triangulation for export safety.",
            }
        )
    if non_manifold_candidate_edges:
        findings.append(
            {
                "severity": "info",
                "code": "sparse_edge_data",
                "message": "Mesh edge data is sparse; verify topology before final export.",
            }
        )
    metrics = {
        "object_id": mesh_object["object_id"],
        "name": mesh_object.get("name"),
        "vertex_count": len(vertices),
        "face_count": len(faces),
        "triangle_count": len(triangles),
        "ngon_count": len(ngons),
    }
    return findings, metrics


def _object_findings(runtime_object: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    object_type = str(runtime_object.get("type", "UNKNOWN"))
    name = str(runtime_object.get("name", ""))
    if not name.strip():
        findings.append({"severity": "warning", "code": "unnamed_object", "message": "Object has an empty name."})
    if object_type == "MESH":
        mesh_findings, mesh_metrics = _mesh_findings(runtime_object)
        findings.extend(mesh_findings)
        metrics = {
            "object_id": runtime_object["object_id"],
            "name": name,
            "type": object_type,
            **mesh_metrics,
        }
        return findings, metrics
    metrics = {
        "object_id": runtime_object["object_id"],
        "name": name,
        "type": object_type,
        "material_count": len(runtime_object.get("material_ids", [])),
    }
    return findings, metrics


def _polycount_metrics(objects: list[dict[str, Any]]) -> dict[str, int]:
    mesh_objects = [obj for obj in objects if obj.get("type") == "MESH"]
    vertices = sum(len((obj.get("data", {}) or {}).get("vertices", [])) for obj in mesh_objects)
    faces = sum(len((obj.get("data", {}) or {}).get("faces", [])) for obj in mesh_objects)
    triangles = sum(
        sum((max(len(face), 3) - 2) for face in ((obj.get("data", {}) or {}).get("faces", [])))
        for obj in mesh_objects
    )
    return {
        "mesh_object_count": len(mesh_objects),
        "vertex_count": vertices,
        "face_count": faces,
        "triangle_count": triangles,
    }


async def _list_project_objects(context, project_id: str) -> list[dict[str, Any]]:  # type: ignore[no-untyped-def]
    listed = await context.bridge.invoke("list_objects", {"project_id": project_id}, read_only=True)
    return list(listed.get("objects", []))


async def inspect_scene(context, request: InspectSceneRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    objects = await _list_project_objects(context, project.project_id)
    findings, metrics = _scene_findings(objects)
    return success_result(
        request_id=request.request_id,
        tool_name="inspect_scene",
        summary="Scene inspection completed.",
        project_id=project.project_id,
        findings=findings,
        severity_summary=_summarize_severity(findings),
        metrics=metrics,
    )


async def inspect_mesh(context, request: InspectMeshRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await resolve_target_ids(
        context,
        project_id=project.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
        tag=request.tag,
        collection_name=request.match_collection_name,
    )
    if len(target_ids) != 1:
        return failed_result(
            request_id=request.request_id,
            tool_name="inspect_mesh",
            summary="inspect_mesh requires exactly one resolved target.",
            errors=["validation_error: exactly one target is required"],
        )
    objects = {item["object_id"]: item for item in await _list_project_objects(context, project.project_id)}
    target = objects.get(target_ids[0])
    if target is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="inspect_mesh",
            summary="Requested target could not be resolved in runtime object listing.",
            errors=[f"target_not_found: Unknown object_id: {target_ids[0]}"],
        )
    if target.get("type") != "MESH":
        return failed_result(
            request_id=request.request_id,
            tool_name="inspect_mesh",
            summary="inspect_mesh target must be a mesh object.",
            errors=[f"validation_error: target is not a mesh object: {target_ids[0]}"],
        )
    findings, metrics = _mesh_findings(target)
    return success_result(
        request_id=request.request_id,
        tool_name="inspect_mesh",
        summary=f"Mesh inspection completed for {target.get('name', target_ids[0])}.",
        project_id=project.project_id,
        findings=findings,
        severity_summary=_summarize_severity(findings),
        metrics=metrics,
        inspected_object_id=target_ids[0],
    )


async def inspect_object(context, request: InspectObjectRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    target_ids = await resolve_target_ids(
        context,
        project_id=project.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
        tag=request.tag,
        collection_name=request.match_collection_name,
    )
    if len(target_ids) != 1:
        return failed_result(
            request_id=request.request_id,
            tool_name="inspect_object",
            summary="inspect_object requires exactly one resolved target.",
            errors=["validation_error: exactly one target is required"],
        )
    objects = {item["object_id"]: item for item in await _list_project_objects(context, project.project_id)}
    target = objects.get(target_ids[0])
    if target is None:
        return failed_result(
            request_id=request.request_id,
            tool_name="inspect_object",
            summary="Requested target could not be resolved in runtime object listing.",
            errors=[f"target_not_found: Unknown object_id: {target_ids[0]}"],
        )
    findings, metrics = _object_findings(target)
    return success_result(
        request_id=request.request_id,
        tool_name="inspect_object",
        summary=f"Object inspection completed for {target.get('name', target_ids[0])}.",
        project_id=project.project_id,
        findings=findings,
        severity_summary=_summarize_severity(findings),
        metrics=metrics,
        inspected_object_id=target_ids[0],
    )


async def inspect_materials(context, request: InspectMaterialsRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    objects = await _list_project_objects(context, project.project_id)
    mesh_objects = [obj for obj in objects if obj.get("type") == "MESH"]
    without_materials = [obj["object_id"] for obj in mesh_objects if not obj.get("material_ids")]
    findings: list[dict[str, Any]] = []
    if without_materials:
        findings.append(
            {
                "severity": "warning",
                "code": "mesh_without_material",
                "message": f"{len(without_materials)} mesh objects have no assigned material.",
                "object_ids": without_materials,
            }
        )
    return success_result(
        request_id=request.request_id,
        tool_name="inspect_materials",
        summary="Material inspection completed.",
        project_id=project.project_id,
        findings=findings,
        severity_summary=_summarize_severity(findings),
        metrics={
            "mesh_object_count": len(mesh_objects),
            "objects_without_material_count": len(without_materials),
        },
    )


async def inspect_scale(context, request: InspectScaleRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    selected_ids = await resolve_target_ids(
        context,
        project_id=project.project_id,
        target_ids=request.target_ids or ([request.target_id] if request.target_id else []),
        names=request.names,
        tag=request.tag,
        collection_name=request.match_collection_name,
    ) if (request.target_id or request.target_ids or request.names or request.tag or request.match_collection_name) else None
    objects = await _list_project_objects(context, project.project_id)
    if selected_ids is not None:
        selected_set = set(selected_ids)
        objects = [obj for obj in objects if obj.get("object_id") in selected_set]
    findings: list[dict[str, Any]] = []
    too_small: list[str] = []
    too_large: list[str] = []
    for obj in objects:
        scale = list(obj.get("scale", [1.0, 1.0, 1.0]))
        if any(component < request.min_scale for component in scale):
            too_small.append(obj["object_id"])
        if any(component > request.max_scale for component in scale):
            too_large.append(obj["object_id"])
    if too_small:
        findings.append({
            "severity": "warning",
            "code": "scale_too_small",
            "message": f"{len(too_small)} objects are below min_scale {request.min_scale}.",
            "object_ids": too_small,
        })
    if too_large:
        findings.append({
            "severity": "warning",
            "code": "scale_too_large",
            "message": f"{len(too_large)} objects exceed max_scale {request.max_scale}.",
            "object_ids": too_large,
        })
    return success_result(
        request_id=request.request_id,
        tool_name="inspect_scale",
        summary="Scale inspection completed.",
        project_id=project.project_id,
        findings=findings,
        severity_summary=_summarize_severity(findings),
        metrics={"inspected_object_count": len(objects), "too_small_count": len(too_small), "too_large_count": len(too_large)},
    )


async def inspect_naming(context, request: InspectNamingRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    objects = await _list_project_objects(context, project.project_id)
    findings: list[dict[str, Any]] = []
    name_counts: dict[str, int] = {}
    for obj in objects:
        name = str(obj.get("name", ""))
        name_counts[name] = name_counts.get(name, 0) + 1
    duplicated_names = sorted([name for name, count in name_counts.items() if name and count > 1])
    if duplicated_names:
        findings.append(
            {
                "severity": "warning",
                "code": "duplicate_names",
                "message": f"Found {len(duplicated_names)} duplicated object names.",
                "names": duplicated_names,
            }
        )
    if request.allowed_prefixes:
        invalid = [str(obj.get("name", "")) for obj in objects if not any(str(obj.get("name", "")).startswith(prefix) for prefix in request.allowed_prefixes)]
        if invalid:
            findings.append(
                {
                    "severity": "info",
                    "code": "name_prefix_mismatch",
                    "message": f"{len(invalid)} object names do not match allowed prefixes.",
                    "names": invalid,
                }
            )
    return success_result(
        request_id=request.request_id,
        tool_name="inspect_naming",
        summary="Naming inspection completed.",
        project_id=project.project_id,
        findings=findings,
        severity_summary=_summarize_severity(findings),
        metrics={"object_count": len(objects), "duplicate_name_count": len(duplicated_names)},
    )


async def check_polycount(context, request: CheckPolycountRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    objects = await _list_project_objects(context, project.project_id)
    metrics = _polycount_metrics(objects)
    findings: list[dict[str, Any]] = []
    if metrics["triangle_count"] > request.max_triangles:
        findings.append(
            {
                "severity": "warning",
                "code": "polycount_budget_exceeded",
                "message": f"Triangle count {metrics['triangle_count']} exceeds budget {request.max_triangles}.",
            }
        )
    return success_result(
        request_id=request.request_id,
        tool_name="check_polycount",
        summary="Polycount check completed.",
        project_id=project.project_id,
        findings=findings,
        severity_summary=_summarize_severity(findings),
        metrics={**metrics, "max_triangles": request.max_triangles},
    )


async def check_export_readiness(context, request: CheckExportReadinessRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    scene_inspection = await inspect_scene(context, InspectSceneRequest(request_id=request.request_id, project_id=project.project_id))
    objects = await _list_project_objects(context, project.project_id)
    mesh_objects = [obj for obj in objects if obj.get("type") == "MESH"]
    findings = list(getattr(scene_inspection, "findings", []))
    for mesh in mesh_objects:
        mesh_findings, _ = _mesh_findings(mesh)
        findings.extend(mesh_findings)
    severity_summary = _summarize_severity(findings)
    blocked_export_formats = ["glb", "gltf", "fbx"] if severity_summary.get("error", 0) else []
    return success_result(
        request_id=request.request_id,
        tool_name="check_export_readiness",
        summary="Export readiness check completed.",
        project_id=project.project_id,
        findings=findings,
        severity_summary=severity_summary,
        blocked_export_formats=blocked_export_formats,
        metrics={
            "mesh_object_count": len(mesh_objects),
            "blocking_issue_count": int(severity_summary.get("error", 0)),
            "warning_issue_count": int(severity_summary.get("warning", 0)),
        },
    )


async def generate_qa_report(context, request: GenerateQAReportRequest):  # type: ignore[no-untyped-def]
    project = require_project(context, request.project_id)
    if request.scope == "scene":
        inspected = await inspect_scene(context, InspectSceneRequest(request_id=request.request_id, project_id=project.project_id))
        findings = list(getattr(inspected, "findings", []))
        severity_summary = dict(getattr(inspected, "severity_summary", {}))
        metrics = dict(getattr(inspected, "metrics", {}))
        entity_id = None
    elif request.scope == "mesh":
        inspected = await inspect_mesh(
            context,
            InspectMeshRequest(
                request_id=request.request_id,
                project_id=project.project_id,
                target_id=request.target_id,
                target_ids=request.target_ids,
                names=request.names,
                tag=request.tag,
                match_collection_name=request.match_collection_name,
            ),
        )
        if inspected.status == "failed":
            return inspected
        findings = list(getattr(inspected, "findings", []))
        severity_summary = dict(getattr(inspected, "severity_summary", {}))
        metrics = dict(getattr(inspected, "metrics", {}))
        entity_id = getattr(inspected, "inspected_object_id", None)
    else:
        inspected = await check_export_readiness(
            context,
            CheckExportReadinessRequest(request_id=request.request_id, project_id=project.project_id),
        )
        findings = list(getattr(inspected, "findings", []))
        severity_summary = dict(getattr(inspected, "severity_summary", {}))
        metrics = dict(getattr(inspected, "metrics", {}))
        entity_id = None

    blocked_export_formats = ["glb", "gltf", "fbx"] if int(severity_summary.get("error", 0)) > 0 else []
    qa_report_id = new_id("qa")
    summary = f"QA report generated for {request.scope} scope with {sum(severity_summary.values())} findings."
    report_payload = {
        "findings": findings,
        "blocked_export_formats": blocked_export_formats,
        "summary": summary,
        "metrics": metrics,
        "scope": request.scope,
    }
    record = context.qa_reports.create(
        qa_report_id=qa_report_id,
        project_id=project.project_id,
        entity_id=entity_id,
        source_operation_id=None,
        severity_summary=severity_summary,
        report=report_payload,
    )
    return success_result(
        request_id=request.request_id,
        tool_name="generate_qa_report",
        summary=summary,
        project_id=project.project_id,
        qa_report_id=record.qa_report_id,
        report=report_payload,
        severity_summary=severity_summary,
        blocked_export_formats=blocked_export_formats,
    )


def register_tools(app) -> None:  # type: ignore[no-untyped-def]
    registrations: list[tuple[str, str, type[BaseModel], Any, bool]] = [
        ("inspect_scene", "Inspect scene-level quality and readiness signals.", InspectSceneRequest, inspect_scene, True),
        ("inspect_object", "Inspect one target object and report quality signals.", InspectObjectRequest, inspect_object, True),
        ("inspect_mesh", "Inspect one mesh object for topology/export readiness.", InspectMeshRequest, inspect_mesh, True),
        ("inspect_materials", "Inspect scene material assignments and missing materials.", InspectMaterialsRequest, inspect_materials, True),
        ("inspect_scale", "Inspect object scales against configurable min/max thresholds.", InspectScaleRequest, inspect_scale, True),
        ("inspect_naming", "Inspect object naming consistency and duplicates.", InspectNamingRequest, inspect_naming, True),
        ("check_polycount", "Check scene polycount against a triangle budget.", CheckPolycountRequest, check_polycount, True),
        ("check_export_readiness", "Check if scene topology and setup are ready for export.", CheckExportReadinessRequest, check_export_readiness, True),
        ("generate_qa_report", "Generate and persist a QA report for scene or mesh scope.", GenerateQAReportRequest, generate_qa_report, False),
    ]
    for name, description, input_model, handler, read_only in registrations:
        app.register_tool(
            app.tool_definition(
                name=name,
                description=description,
                family="qa",
                input_model=input_model,
                handler=handler,
                read_only=read_only,
            )
        )