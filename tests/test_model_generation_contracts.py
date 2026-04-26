from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.serialization import json_loads
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port


async def _call(app: MCPServerApplication, name: str, arguments: dict[str, object]) -> dict[str, object]:
    response = await app.handle_jsonrpc(
        {
            "jsonrpc": "2.0",
            "id": name,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        }
    )
    return response["result"]


def _make_settings(tmp_path: Path) -> ServerSettings:
    port = find_free_port()
    return ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_model_generation_tools_are_registered(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tool_names = {tool["name"] for tool in listed["result"]["tools"]}
        assert {
            "create_model",
            "create_hard_surface_model",
            "create_building",
            "create_furniture",
            "increase_detail",
            "reduce_detail",
            "modify_silhouette",
            "restyle_model",
        }.issubset(tool_names)
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_safe_mode_default_setting_controls_generation_budget_guard(
    tmp_path: Path,
) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_MAX_SAFE_MODE_POLYGON_BUDGET": "64",
            "BLENDER_MCP_SAFE_MODE_DEFAULT": "false",
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Budget Default"})
        project_id = str(project["project_id"])

        result = await _call(
            app,
            "create_model",
            {
                "request_id": "req-budget-default",
                "project_id": project_id,
                "category": "furniture",
                "furniture_type": "chair",
                "polygon_budget": 65,
                "name": "Budget Chair",
            },
        )

        assert result["status"] == "success"
        assert result["tool_name"] == "create_model"
        assert result["dispatched_tool"] == "create_furniture"
        assert result["asset"]["category"] == "furniture"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_model_honors_explicit_category_over_keyword_hints(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Explicit Category"})
        project_id = str(project["project_id"])

        generated = await _call(
            app,
            "create_model",
            {
                "request_id": "req-explicit-category",
                "project_id": project_id,
                "instruction": "Create a drone that can carry a chair-shaped cargo pod",
                "category": "vehicle",
                "furniture_type": "chair",
                "constraints": ["modular", "chair-compatible mount"],
            },
        )

        assert generated["status"] == "success"
        assert generated["tool_name"] == "create_model"
        assert generated["dispatched_tool"] == "create_hard_surface_model"
        assert generated["asset"]["category"] == "vehicle"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_model_routes_to_drone_generation_and_persists_asset(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Model Generation"})
        project_id = str(project["project_id"])

        generated = await _call(
            app,
            "create_model",
            {
                "request_id": "req-create-model",
                "project_id": project_id,
                "instruction": "Create a small SF drone with blue emissive accents",
                "category": "vehicle",
                "style": "near-future",
                "constraints": ["symmetry", "four-rotor"],
            },
        )

        assert generated["status"] == "success"
        assert generated["dispatched_tool"] == "create_hard_surface_model"
        assert generated["asset"]["category"] == "vehicle"
        assert generated["asset"]["style"] == "near-future"
        assert len(generated["created_object_ids"]) >= 10
        part_names = {part["name"] for part in generated["parts"]}
        assert {"body", "sensor", "rotor_front_left", "rotor_front_right"}.issubset(part_names)

        stored_asset = app.context.entities.get(str(generated["asset_id"]))
        assert stored_asset is not None
        assert stored_asset.entity_type == "asset"
        stored_spec = json_loads(stored_asset.spec_json)
        assert stored_spec["constraints"][-1] == "four_rotor_layout"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_category_specific_building_and_furniture_generation_succeed(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Category Models"})
        project_id = str(project["project_id"])

        building = await _call(
            app,
            "create_building",
            {
                "request_id": "req-building",
                "project_id": project_id,
                "name": "Review Shell",
                "style": "modern",
                "floors": 3,
            },
        )
        assert building["status"] == "success"
        building_part_names = {part["name"] for part in building["parts"]}
        assert {"shell", "roof", "door"}.issubset(building_part_names)
        assert sum(1 for part in building["parts"] if part["kind"] == "window") >= 4

        furniture = await _call(
            app,
            "create_furniture",
            {
                "request_id": "req-furniture",
                "project_id": project_id,
                "name": "Review Chair",
                "furniture_type": "chair",
                "style": "premium",
            },
        )
        assert furniture["status"] == "success"
        furniture_part_names = {part["name"] for part in furniture["parts"]}
        assert {"seat", "backrest", "leg_front_left", "leg_back_right"}.issubset(furniture_part_names)
        assert furniture["asset"]["category"] == "furniture"
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_safe_mode_rejects_oversized_polygon_budget_before_mutation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
            "BLENDER_MCP_MAX_SAFE_MODE_POLYGON_BUDGET": "64",
        },
        base_dir=tmp_path,
    )
    app = MCPServerApplication(settings)
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Budget Guard"})
        project_id = str(project["project_id"])

        async def fail_invoke(*args, **kwargs):  # type: ignore[no-untyped-def]
            raise AssertionError("bridge.invoke should not run when safe mode rejects the request")

        monkeypatch.setattr(app.context.bridge, "invoke", fail_invoke)

        result = await _call(
            app,
            "create_model",
            {
                "request_id": "req-budget",
                "project_id": project_id,
                "instruction": "Create a premium furniture hero asset",
                "category": "furniture",
                "furniture_type": "chair",
                "safe_mode": True,
                "polygon_budget": 65,
            },
        )

        assert result["status"] == "failed"
        assert result["tool_name"] == "create_model"
        assert "safe-mode limit" in result["errors"][0]
        assert app.context.entities.list_by_type(project_id, "asset") == []
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_increase_and_reduce_detail_are_part_local(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Detail Revisions"})
        project_id = str(project["project_id"])
        furniture = await _call(
            app,
            "create_furniture",
            {
                "request_id": "req-chair",
                "project_id": project_id,
                "name": "Revision Chair",
                "furniture_type": "chair",
            },
        )
        leg_part = next(part for part in furniture["parts"] if part["name"] == "leg_front_left")
        leg_object_id = leg_part["metadata"]["target_ids"][0]
        seat_part = next(part for part in furniture["parts"] if part["name"] == "seat")
        seat_object_id = seat_part["metadata"]["target_ids"][0]

        increased = await _call(
            app,
            "increase_detail",
            {
                "request_id": "req-increase",
                "project_id": project_id,
                "part_id": leg_part["part_id"],
                "detail_strategy": "bevel",
                "amount": 1.5,
            },
        )
        assert increased["status"] == "success"
        assert increased["modified_part_ids"] == [leg_part["part_id"]]
        assert seat_part["part_id"] in increased["untouched_part_ids"]

        leg_modifiers = await _call(
            app,
            "list_modifiers",
            {"request_id": "req-list-leg", "project_id": project_id, "target_id": leg_object_id},
        )
        seat_modifiers = await _call(
            app,
            "list_modifiers",
            {"request_id": "req-list-seat", "project_id": project_id, "target_id": seat_object_id},
        )
        assert any(modifier["name"] == "MCPDetailBevel" for modifier in leg_modifiers["modifiers"])
        assert seat_modifiers["modifiers"] == []

        reduced = await _call(
            app,
            "reduce_detail",
            {
                "request_id": "req-reduce",
                "project_id": project_id,
                "part_id": leg_part["part_id"],
                "ratio": 0.4,
            },
        )
        assert reduced["status"] == "success"
        assert reduced["modified_part_ids"] == [leg_part["part_id"]]

        reduced_leg_modifiers = await _call(
            app,
            "list_modifiers",
            {"request_id": "req-list-leg-2", "project_id": project_id, "target_id": leg_object_id},
        )
        assert any(modifier["name"] == "MCPReduceDetail" for modifier in reduced_leg_modifiers["modifiers"])
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_modify_silhouette_and_restyle_model_stay_localized(tmp_path: Path) -> None:
    app = MCPServerApplication(_make_settings(tmp_path))
    try:
        project = await _call(app, "create_project", {"request_id": "req-project", "name": "Style Revisions"})
        project_id = str(project["project_id"])
        furniture = await _call(
            app,
            "create_furniture",
            {
                "request_id": "req-chair",
                "project_id": project_id,
                "name": "Style Chair",
                "furniture_type": "chair",
            },
        )
        backrest = next(part for part in furniture["parts"] if part["name"] == "backrest")
        backrest_object_id = backrest["metadata"]["target_ids"][0]
        leg = next(part for part in furniture["parts"] if part["name"] == "leg_back_left")
        leg_object_id = leg["metadata"]["target_ids"][0]
        original_backrest = json_loads(app.context.entities.get(backrest_object_id).spec_json)

        modified = await _call(
            app,
            "modify_silhouette",
            {
                "request_id": "req-silhouette",
                "project_id": project_id,
                "part_id": backrest["part_id"],
                "adjustment": "taller",
                "intensity": 0.25,
            },
        )
        assert modified["status"] == "success"
        assert modified["modified_part_ids"] == [backrest["part_id"]]
        assert leg["part_id"] in modified["untouched_part_ids"]

        backrest_entity = app.context.entities.get(backrest_object_id)
        assert backrest_entity is not None
        backrest_spec = json_loads(backrest_entity.spec_json)
        assert backrest_spec["scale"][2] > original_backrest["scale"][2]

        restyled = await _call(
            app,
            "restyle_model",
            {
                "request_id": "req-restyle",
                "project_id": project_id,
                "part_id": backrest["part_id"],
                "style_target": "industrial",
            },
        )
        assert restyled["status"] == "success"
        assert restyled["modified_part_ids"] == [backrest["part_id"]]

        restyled_backrest = json_loads(app.context.entities.get(backrest_object_id).spec_json)
        untouched_leg = json_loads(app.context.entities.get(leg_object_id).spec_json)
        assert restyled_backrest["material_ids"] != untouched_leg["material_ids"]
    finally:
        await app.stop()