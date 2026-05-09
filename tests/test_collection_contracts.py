from __future__ import annotations

from pathlib import Path

import pytest
from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication
from tests.port_utils import find_free_port

COLLECTION_TOOLS = {
    "list_collections",
    "create_collection",
    "rename_collection",
    "delete_collection",
    "link_objects_to_collection",
    "unlink_objects_from_collection",
    "set_collection_visibility",
}


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


def _build_app(tmp_path: Path) -> MCPServerApplication:
    port = find_free_port()
    settings = ServerSettings.from_env(
        {
            "BLENDER_MCP_WORKSPACE_ROOTS": "workspace",
            "BLENDER_MCP_CONTROLLER_MODE": "mock",
            "BLENDER_MCP_CONTROLLER_PORT": str(port),
        },
        base_dir=tmp_path,
    )
    return MCPServerApplication(settings)


def _collection_named(collections: list[dict[str, object]], name: str) -> dict[str, object]:
    return next(collection for collection in collections if collection["name"] == name)


@pytest.mark.integration
@pytest.mark.asyncio
async def test_collection_tools_are_registered(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        listed = await app.handle_jsonrpc({"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
        tools = {tool["name"]: tool for tool in listed["result"]["tools"]}

        assert COLLECTION_TOOLS.issubset(tools)
        for tool_name in COLLECTION_TOOLS:
            assert tools[tool_name]["annotations"]["family"] == "collections"
        assert tools["list_collections"]["annotations"]["readOnlyHint"] is True
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_mock_runtime_collection_lifecycle_and_links(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-coll-project", "name": "Collections"})
        project_id = str(project["project_id"])
        hero = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-coll-hero",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "HeroCube",
            },
        )
        prop = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-coll-prop",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "PropCube",
            },
        )
        hero_id = str(hero["created_object_ids"][0])
        prop_id = str(prop["created_object_ids"][0])

        created_parent = await _call(
            app,
            "create_collection",
            {"request_id": "req-coll-create-parent", "project_id": project_id, "collection_name": "Environment"},
        )
        created_child = await _call(
            app,
            "create_collection",
            {
                "request_id": "req-coll-create-child",
                "project_id": project_id,
                "collection_name": "Rocks",
                "parent_collection_name": "Environment",
            },
        )
        assert created_parent["status"] == "success"
        assert created_child["collection"]["parent_name"] == "Environment"

        linked = await _call(
            app,
            "link_objects_to_collection",
            {
                "request_id": "req-coll-link",
                "project_id": project_id,
                "collection_name": "Rocks",
                "target_ids": [hero_id],
                "names": ["PropCube"],
            },
        )
        assert linked["status"] == "success"
        assert set(linked["modified_object_ids"]) == {hero_id, prop_id}
        assert set(linked["collection"]["object_ids"]) == {hero_id, prop_id}

        hidden = await _call(
            app,
            "set_collection_visibility",
            {
                "request_id": "req-coll-hide",
                "project_id": project_id,
                "collection_name": "Rocks",
                "visible": False,
            },
        )
        assert hidden["collection"]["visible"] is False
        assert hidden["collection"]["hide_viewport"] is True
        assert hidden["collection"]["hide_render"] is True

        renamed = await _call(
            app,
            "rename_collection",
            {
                "request_id": "req-coll-rename",
                "project_id": project_id,
                "collection_name": "Rocks",
                "new_collection_name": "HeroRocks",
            },
        )
        assert renamed["status"] == "success"
        assert renamed["collection"]["name"] == "HeroRocks"
        assert set(renamed["modified_object_ids"]) == {hero_id, prop_id}

        unlinked = await _call(
            app,
            "unlink_objects_from_collection",
            {
                "request_id": "req-coll-unlink",
                "project_id": project_id,
                "collection_name": "HeroRocks",
                "target_id": hero_id,
            },
        )
        assert unlinked["status"] == "success"
        assert hero_id not in unlinked["collection"]["object_ids"]

        listed = await _call(app, "list_collections", {"request_id": "req-coll-list", "project_id": project_id})
        collections = listed["collections"]
        hero_rocks = _collection_named(collections, "HeroRocks")
        assert hero_rocks["parent_name"] == "Environment"
        assert hero_rocks["object_ids"] == [prop_id]
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_delete_collection_requires_empty_unless_forced_without_deleting_objects(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-coll-del-project", "name": "Delete"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-coll-del-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "KeepMe",
            },
        )
        object_id = str(cube["created_object_ids"][0])
        await _call(
            app,
            "create_collection",
            {"request_id": "req-coll-del-create", "project_id": project_id, "collection_name": "ToDelete"},
        )
        await _call(
            app,
            "link_objects_to_collection",
            {
                "request_id": "req-coll-del-link",
                "project_id": project_id,
                "collection_name": "ToDelete",
                "target_id": object_id,
            },
        )

        refused = await _call(
            app,
            "delete_collection",
            {
                "request_id": "req-coll-del-refuse",
                "project_id": project_id,
                "collection_name": "ToDelete",
            },
        )
        assert refused["status"] == "failed"
        assert "not empty" in refused["summary"]

        forced = await _call(
            app,
            "delete_collection",
            {
                "request_id": "req-coll-del-force",
                "project_id": project_id,
                "collection_name": "ToDelete",
                "force": True,
            },
        )
        assert forced["status"] == "success"
        assert forced["deleted_collection_name"] == "ToDelete"
        assert forced["deleted_object_ids"] == []
        assert forced["unlinked_object_ids"] == [object_id]
        assert "without deleting scene objects" in forced["summary"]

        objects = await _call(app, "list_objects", {"request_id": "req-coll-del-objects", "project_id": project_id})
        assert [obj["object_id"] for obj in objects["objects"]] == [object_id]
        listed = await _call(app, "list_collections", {"request_id": "req-coll-del-list", "project_id": project_id})
        assert "ToDelete" not in {collection["name"] for collection in listed["collections"]}
    finally:
        await app.stop()


@pytest.mark.integration
@pytest.mark.asyncio
async def test_collection_tools_return_structured_failures_and_history(tmp_path: Path) -> None:
    app = _build_app(tmp_path)
    try:
        project = await _call(app, "create_project", {"request_id": "req-coll-fail-project", "name": "Failures"})
        project_id = str(project["project_id"])
        cube = await _call(
            app,
            "create_primitive",
            {
                "request_id": "req-coll-fail-cube",
                "project_id": project_id,
                "primitive_type": "cube",
                "name": "KnownCube",
            },
        )
        object_id = str(cube["created_object_ids"][0])
        await _call(
            app,
            "create_collection",
            {"request_id": "req-coll-fail-create", "project_id": project_id, "collection_name": "Valid"},
        )

        missing_collection = await _call(
            app,
            "link_objects_to_collection",
            {
                "request_id": "req-coll-fail-missing-coll",
                "project_id": project_id,
                "collection_name": "Missing",
                "target_id": object_id,
            },
        )
        missing_object = await _call(
            app,
            "link_objects_to_collection",
            {
                "request_id": "req-coll-fail-missing-object",
                "project_id": project_id,
                "collection_name": "Valid",
                "names": ["MissingCube"],
            },
        )
        linked = await _call(
            app,
            "link_objects_to_collection",
            {
                "request_id": "req-coll-fail-link",
                "project_id": project_id,
                "collection_name": "Valid",
                "names": ["KnownCube"],
            },
        )
        history = await _call(
            app,
            "list_operations",
            {"request_id": "req-coll-fail-history", "project_id": project_id, "limit": 20},
        )

        assert missing_collection["status"] == "failed"
        assert missing_collection["tool_name"] == "link_objects_to_collection"
        assert "target_not_found" in missing_collection["errors"][0]
        assert missing_object["status"] == "failed"
        assert "target_not_found" in missing_object["errors"][0]
        assert linked["status"] == "success"
        assert "link_objects_to_collection" in [operation["tool_name"] for operation in history["operations"]]
    finally:
        await app.stop()