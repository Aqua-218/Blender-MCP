from __future__ import annotations

from typing import Any

from mcp_server.persistence import ProjectRecord
from mcp_server.utils import new_id


def require_project(context, project_id: str) -> ProjectRecord:  # type: ignore[no-untyped-def]
    project = context.projects.get(project_id)
    if project is None:
        raise ValueError(f"Unknown project_id: {project_id}")
    return project


def project_paths_for_record(context, project: ProjectRecord):  # type: ignore[no-untyped-def]
    workspace_root = context.workspace.owning_workspace_root(project.blend_file_path)
    return context.workspace.plan_project_paths(
        project.project_id,
        project.name,
        workspace_root,
    )


async def create_internal_snapshot(  # type: ignore[no-untyped-def]
    context,
    project: ProjectRecord,
    source_operation_id: str,
    *,
    reason: str = "pre_destructive_change",
):
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
    snapshot = context.snapshots.create(
        snapshot_id=snapshot_id,
        project_id=project.project_id,
        source_operation_id=source_operation_id,
        reason=reason,
        snapshot_path=bridge_result["snapshot_path"],
    )
    return snapshot


async def resolve_target_ids(  # type: ignore[no-untyped-def]
    context,
    *,
    project_id: str,
    target_ids: list[str] | None = None,
    names: list[str] | None = None,
    tag: str | None = None,
    collection_name: str | None = None,
    spatial_range: dict[str, list[float]] | None = None,
) -> list[str]:
    if target_ids:
        return list(dict.fromkeys(target_ids))
    result = await context.bridge.invoke(
        "find_objects",
        {
            "project_id": project_id,
            "names": names or [],
            "tag": tag,
            "collection_name": collection_name,
            "spatial_range": spatial_range,
        },
        read_only=True,
    )
    resolved = [item["object_id"] for item in result.get("objects", [])]
    if not resolved:
        raise ValueError("No matching targets were resolved.")
    return resolved


def sync_entities(context, project_id: str, items: list[dict[str, Any]], *, entity_type_key: str = "type") -> None:  # type: ignore[no-untyped-def]
    for item in items:
        context.entities.upsert(
            entity_id=item["object_id"],
            project_id=project_id,
            entity_type=str(item.get(entity_type_key, "object")).lower(),
            name=item["name"],
            spec=item,
        )


def sync_named_entity(  # type: ignore[no-untyped-def]
    context,
    project_id: str,
    entity_id: str,
    entity_type: str,
    name: str,
    spec: dict[str, Any],
) -> None:
    context.entities.upsert(
        entity_id=entity_id,
        project_id=project_id,
        entity_type=entity_type,
        name=name,
        spec=spec,
    )
