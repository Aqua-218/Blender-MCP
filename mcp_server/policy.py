from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from mcp_server.config import RoleName, ServerSettings


class ToolClass(StrEnum):
    QUERY = "query"
    SAFE_MUTATION = "safe_mutation"
    DESTRUCTIVE_MUTATION = "destructive_mutation"


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    tool_class: ToolClass
    requires_confirmation: bool = False
    requires_snapshot: bool = False
    error_code: str | None = None
    message: str | None = None


QUERY_TOOLS = {
    "ping_bridge",
    "get_runtime_info",
    "get_server_metrics",
    "get_safe_config",
    "list_objects",
    "find_objects",
    "get_project_info",
    "get_render_settings",
    "inspect_scene",
    "inspect_object",
    "inspect_mesh",
    "inspect_materials",
    "inspect_scale",
    "inspect_naming",
    "check_polycount",
    "check_export_readiness",
    "list_modifiers",
    "list_collections",
    "list_selection_sets",
    "list_parts",
    "list_material_nodes",
    "get_export_formats",
    "list_operations",
    "get_generation_history",
    "list_snapshots",
    "compare_snapshots",
    "generate_diff_summary",
    "inspect_world",
    "validate_world_composition",
    "inspect_uv",
    "list_uv_maps",
    "plan_texture_bake",
    "validate_uv_layout",
    "list_cameras",
    "list_lights",
    "validate_game_export_readiness",
    "validate_lod_chain",
    "plan_game_export_package",
        "validate_engine_export_package",
        "plan_engine_import_checklist",
    "list_asset_library_items",
    "find_asset_library_items",
    "validate_asset_library",
    "preview_batch_targets",
    "list_geometry_nodes_setups",
    "validate_geometry_nodes_setup",
    "list_armatures",
    "list_animation_tracks",
    "validate_animation_rigging",
}

DESTRUCTIVE_TOOLS = {
    "delete_object",
    "delete_objects",
    "rollback_to_snapshot",
}


class PolicyEngine:
    def __init__(self, settings: ServerSettings):
        self.settings = settings

    def classify_tool(self, tool_name: str) -> ToolClass:
        if tool_name in QUERY_TOOLS:
            return ToolClass.QUERY
        if tool_name in DESTRUCTIVE_TOOLS:
            return ToolClass.DESTRUCTIVE_MUTATION
        return ToolClass.SAFE_MUTATION

    def authorize(
        self,
        *,
        tool_name: str,
        role: RoleName,
        destructive_confirmation: bool,
        blast_radius: int = 0,
        overwrite: bool = False,
    ) -> PolicyDecision:
        tool_class = self.classify_tool(tool_name)
        if role == "viewer" and tool_class != ToolClass.QUERY:
            return PolicyDecision(
                allowed=False,
                tool_class=tool_class,
                error_code="policy_violation",
                message="Viewer sessions cannot run mutating tools.",
            )
        if tool_class == ToolClass.DESTRUCTIVE_MUTATION:
            requires_snapshot = True
            requires_confirmation = role != "destructive_editor" and role != "operator"
            if requires_confirmation and not destructive_confirmation:
                return PolicyDecision(
                    allowed=False,
                    tool_class=tool_class,
                    requires_confirmation=True,
                    requires_snapshot=requires_snapshot,
                    error_code="snapshot_required",
                    message="Destructive operation requires explicit confirmation.",
                )
            return PolicyDecision(
                allowed=True,
                tool_class=tool_class,
                requires_snapshot=requires_snapshot,
            )
        if overwrite and role not in {"destructive_editor", "operator"} and not destructive_confirmation:
            return PolicyDecision(
                allowed=False,
                tool_class=tool_class,
                requires_confirmation=True,
                requires_snapshot=True,
                error_code="snapshot_required",
                message="Overwrite requires explicit confirmation.",
            )
        requires_snapshot = overwrite or blast_radius >= self.settings.destructive_snapshot_threshold
        return PolicyDecision(allowed=True, tool_class=tool_class, requires_snapshot=requires_snapshot)
