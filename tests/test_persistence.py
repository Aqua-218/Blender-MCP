from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest
from mcp_server.persistence import (
    DatabaseManager,
    ExportRecordRepository,
    OperationRepository,
    ProjectRepository,
    QAReportRepository,
    SnapshotRepository,
)


def test_database_initialization_and_repositories(tmp_path: Path) -> None:
    repo_root = Path.cwd()
    db_path = tmp_path / "workspace" / "metadata" / "metadata.sqlite3"
    manager = DatabaseManager(repo_root, db_path)
    manager.initialize()

    assert db_path.exists()
    assert manager.backup_database() is not None

    projects = ProjectRepository(manager)
    operations = OperationRepository(manager)
    snapshots = SnapshotRepository(manager)
    qa_reports = QAReportRepository(manager)
    exports = ExportRecordRepository(manager)

    project = projects.create(
        project_id="project-1",
        name="Demo",
        blend_file_path=str(tmp_path / "workspace" / "projects" / "demo.blend"),
        workspace_root=str(tmp_path / "workspace"),
        template_type="blank",
        unit_scale=1.0,
        active_scene_name="Scene",
        status="active",
    )
    assert project.project_id == "project-1"
    assert projects.get("project-1") is not None

    operation = operations.start(
        operation_id="op-1",
        project_id="project-1",
        request_id="req-1",
        tool_name="create_project",
        target_entity_id=None,
        status="running",
        user_instruction="create demo project",
        input_json="{}",
    )
    operations.complete(
        "op-1",
        status="success",
        output_payload={"ok": True},
        warnings=[],
        errors=[],
    )
    assert operations.recent_by_project("project-1")[0].operation_id == operation.operation_id

    snapshot = snapshots.create(
        snapshot_id="snap-1",
        project_id="project-1",
        source_operation_id="op-1",
        reason="manual",
        snapshot_path=str(tmp_path / "workspace" / "snapshots" / "snap-1.blend"),
    )
    assert snapshots.get(snapshot.snapshot_id) is not None
    assert snapshots.lookup_by_project("project-1")[0].snapshot_id == "snap-1"

    qa_reports.create(
        qa_report_id="qa-1",
        project_id="project-1",
        entity_id=None,
        source_operation_id="op-1",
        severity_summary={"info": 1},
        report={"summary": "ok"},
    )
    exports.create(
        export_id="exp-1",
        project_id="project-1",
        entity_id=None,
        format="glb",
        output_path=str(tmp_path / "workspace" / "exports" / "demo.glb"),
        metadata={"preset": "game"},
        warnings=[],
    )
    assert projects.recent_history()[0].project_id == "project-1"
    assert exports.history_by_format("project-1", "glb")[0].export_id == "exp-1"


def test_backup_database_captures_committed_wal_state(tmp_path: Path) -> None:
    repo_root = Path.cwd()
    db_path = tmp_path / "workspace" / "metadata" / "metadata.sqlite3"
    manager = DatabaseManager(repo_root, db_path)
    manager.initialize()

    with sqlite3.connect(db_path) as connection:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("CREATE TABLE wal_probe (value TEXT)")
        connection.execute("INSERT INTO wal_probe (value) VALUES ('visible-from-backup')")
        connection.commit()
        backup_path = manager.backup_database()

    assert backup_path is not None
    with sqlite3.connect(backup_path) as backup_connection:
        row = backup_connection.execute("SELECT value FROM wal_probe").fetchone()
    assert row == ("visible-from-backup",)


def test_initialize_rejects_unversioned_existing_database(tmp_path: Path) -> None:
    repo_root = Path.cwd()
    db_path = tmp_path / "workspace" / "metadata" / "metadata.sqlite3"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as connection:
        connection.execute("CREATE TABLE stray_table (id INTEGER PRIMARY KEY)")
        connection.commit()

    manager = DatabaseManager(repo_root, db_path)

    with pytest.raises(RuntimeError, match="missing alembic_version"):
        manager.initialize()
