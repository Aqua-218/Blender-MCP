from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from importlib import resources
from pathlib import Path
from typing import Any

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    event,
    inspect,
    select,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker

from mcp_server.serialization import json_dumps, json_loads
from mcp_server.utils import utc_now, utc_now_iso

_PACKAGED_ALEMBIC_RUNTIME = "_alembic_runtime"


class Base(DeclarativeBase):
    pass


class ProjectRecord(Base):
    __tablename__ = "projects"

    project_id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    blend_file_path: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    workspace_root: Mapped[str] = mapped_column(String, nullable=False)
    template_type: Mapped[str] = mapped_column(String, nullable=False)
    unit_scale: Mapped[float] = mapped_column(nullable=False)
    active_scene_name: Mapped[str] = mapped_column(String, nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)
    last_saved_at: Mapped[str | None] = mapped_column(String, nullable=True)
    dirty_flag: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


Index("ix_projects_updated_at_desc", ProjectRecord.updated_at.desc())


class EntityRecord(Base):
    __tablename__ = "entities"

    entity_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    entity_type: Mapped[str] = mapped_column(String, nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    spec_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)
    updated_at: Mapped[str] = mapped_column(String, nullable=False)


Index("ix_entities_project_id_name", EntityRecord.project_id, EntityRecord.name)


class OperationRecord(Base):
    __tablename__ = "operations"

    operation_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    request_id: Mapped[str] = mapped_column(String, nullable=False, unique=True)
    tool_name: Mapped[str] = mapped_column(String, nullable=False)
    target_entity_id: Mapped[str | None] = mapped_column(String, nullable=True)
    status: Mapped[str] = mapped_column(String, nullable=False)
    user_instruction: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_json: Mapped[str] = mapped_column(Text, nullable=False)
    output_json: Mapped[str] = mapped_column(Text, nullable=False)
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    errors_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    started_at: Mapped[str] = mapped_column(String, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(String, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)


Index("ix_operations_project_started", OperationRecord.project_id, OperationRecord.started_at.desc())
Index(
    "ix_operations_project_tool_started",
    OperationRecord.project_id,
    OperationRecord.tool_name,
    OperationRecord.started_at.desc(),
)


class SnapshotRecord(Base):
    __tablename__ = "snapshots"

    snapshot_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    source_operation_id: Mapped[str | None] = mapped_column(
        ForeignKey("operations.operation_id"), nullable=True
    )
    reason: Mapped[str] = mapped_column(String, nullable=False)
    snapshot_path: Mapped[str] = mapped_column(String, nullable=False)
    diff_summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    created_at: Mapped[str] = mapped_column(String, nullable=False)


Index("ix_snapshots_project_created", SnapshotRecord.project_id, SnapshotRecord.created_at.desc())
Index("ix_snapshots_source_operation", SnapshotRecord.source_operation_id)


class QAReportRecord(Base):
    __tablename__ = "qa_reports"

    qa_report_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.entity_id"), nullable=True)
    source_operation_id: Mapped[str | None] = mapped_column(
        ForeignKey("operations.operation_id"), nullable=True
    )
    severity_summary_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    report_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(String, nullable=False)


Index("ix_qa_reports_entity_created", QAReportRecord.entity_id, QAReportRecord.created_at.desc())


class ExportRecordRow(Base):
    __tablename__ = "export_records"

    export_id: Mapped[str] = mapped_column(String, primary_key=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.project_id"), nullable=False)
    entity_id: Mapped[str | None] = mapped_column(ForeignKey("entities.entity_id"), nullable=True)
    format: Mapped[str] = mapped_column(String, nullable=False)
    output_path: Mapped[str] = mapped_column(String, nullable=False)
    metadata_json: Mapped[str] = mapped_column(Text, nullable=False, default="{}")
    warnings_json: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    created_at: Mapped[str] = mapped_column(String, nullable=False)


Index("ix_export_records_entity_format", ExportRecordRow.entity_id, ExportRecordRow.format)
Index("ix_export_records_project_created", ExportRecordRow.project_id, ExportRecordRow.created_at.desc())


def _sqlite_url(db_path: Path) -> str:
    return f"sqlite+pysqlite:///{db_path}"


def create_database_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(_sqlite_url(db_path), future=True)

    @event.listens_for(engine, "connect")
    def _configure_sqlite(connection, _record) -> None:  # type: ignore[no-untyped-def]
        cursor = connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA foreign_keys=ON;")
        cursor.execute("PRAGMA busy_timeout=5000;")
        cursor.close()

    return engine


class DatabaseManager:
    def __init__(self, repo_root: Path, db_path: Path):
        self.repo_root = repo_root.resolve()
        self.db_path = db_path.resolve()
        self.engine = create_database_engine(self.db_path)
        self.session_factory = sessionmaker(self.engine, class_=Session, expire_on_commit=False)

    @contextmanager
    def session(self) -> Any:
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    def backup_database(self) -> Path | None:
        if not self.db_path.exists():
            return None
        backup_path = self.db_path.with_name(
            f"{self.db_path.stem}.backup-{utc_now().strftime('%Y%m%d%H%M%S')}{self.db_path.suffix}"
        )
        with sqlite3.connect(self.db_path) as source, sqlite3.connect(backup_path) as target:
            source.backup(target)
        return backup_path

    @contextmanager
    def _alembic_assets(self) -> Iterator[tuple[Path, Path]]:
        repo_config_path = self.repo_root / "alembic.ini"
        repo_script_location = self.repo_root / "alembic"
        if repo_config_path.is_file() and repo_script_location.is_dir():
            yield repo_config_path, repo_script_location
            return

        packaged_root = resources.files("mcp_server").joinpath(_PACKAGED_ALEMBIC_RUNTIME)
        with resources.as_file(packaged_root) as asset_root:
            config_path = asset_root / "alembic.ini"
            script_location = asset_root / "alembic"
            if not config_path.is_file() or not script_location.is_dir():
                raise RuntimeError(
                    "Alembic runtime assets are missing from the installed package."
                )
            yield config_path, script_location

    @contextmanager
    def _alembic_config(self) -> Iterator[Config]:
        with self._alembic_assets() as (config_path, script_location):
            config = Config(str(config_path))
            config.set_main_option("script_location", str(script_location))
            config.set_main_option("sqlalchemy.url", _sqlite_url(self.db_path))
            yield config

    def _migration_head(self) -> str:
        with self._alembic_config() as config:
            script = ScriptDirectory.from_config(config)
            heads = script.get_heads()
        if len(heads) != 1:
            raise RuntimeError("Expected exactly one alembic migration head")
        return heads[0]

    def _current_revision(self) -> str | None:
        if not self.db_path.exists():
            return None
        with self.engine.connect() as connection:
            table_names = set(inspect(connection).get_table_names())
            if "alembic_version" not in table_names:
                if table_names:
                    raise RuntimeError(
                        "Existing metadata database has tables but is missing alembic_version"
                    )
                return None
            rows = connection.exec_driver_sql("SELECT version_num FROM alembic_version").fetchall()
            if len(rows) != 1:
                raise RuntimeError("Expected exactly one alembic_version row")
            return str(rows[0][0])

    def _validate_migration_state(self) -> tuple[str | None, str]:
        current_revision = self._current_revision()
        with self._alembic_config() as config:
            script = ScriptDirectory.from_config(config)
            heads = script.get_heads()
            if len(heads) != 1:
                raise RuntimeError("Expected exactly one alembic migration head")
            head_revision = heads[0]
            if current_revision is None:
                return None, head_revision
            if script.get_revision(current_revision) is None:
                raise RuntimeError(f"Database revision is unknown to alembic: {current_revision}")
            return current_revision, head_revision

    def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        current_revision, head_revision = self._validate_migration_state()
        if self.db_path.exists() and current_revision != head_revision:
            self.backup_database()
        with self._alembic_config() as config:
            command.upgrade(config, "head")


class ProjectRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def create(self, **data: Any) -> ProjectRecord:
        timestamp = utc_now_iso()
        dirty_flag = 1 if bool(data.pop("dirty_flag", False)) else 0
        record = ProjectRecord(created_at=timestamp, updated_at=timestamp, dirty_flag=dirty_flag, **data)
        with self.db.session() as session:
            session.add(record)
        return record

    def get(self, project_id: str) -> ProjectRecord | None:
        with self.db.session() as session:
            return session.get(ProjectRecord, project_id)

    def get_by_blend_path(self, blend_file_path: str) -> ProjectRecord | None:
        with self.db.session() as session:
            stmt = select(ProjectRecord).where(ProjectRecord.blend_file_path == blend_file_path)
            return session.execute(stmt).scalar_one_or_none()

    def mark_saved(self, project_id: str, active_scene_name: str) -> None:
        with self.db.session() as session:
            record = session.get(ProjectRecord, project_id)
            if record is None:
                raise KeyError(project_id)
            timestamp = utc_now_iso()
            record.updated_at = timestamp
            record.last_saved_at = timestamp
            record.active_scene_name = active_scene_name
            record.dirty_flag = 0

    def update_blend_file_path(self, project_id: str, blend_file_path: str) -> None:
        with self.db.session() as session:
            record = session.get(ProjectRecord, project_id)
            if record is None:
                raise KeyError(project_id)
            record.blend_file_path = blend_file_path
            record.updated_at = utc_now_iso()

    def update_storage(self, project_id: str, *, blend_file_path: str, workspace_root: str) -> None:
        with self.db.session() as session:
            record = session.get(ProjectRecord, project_id)
            if record is None:
                raise KeyError(project_id)
            record.blend_file_path = blend_file_path
            record.workspace_root = workspace_root
            record.updated_at = utc_now_iso()

    def refresh_metadata(
        self,
        project_id: str,
        *,
        name: str,
        blend_file_path: str,
        workspace_root: str,
        template_type: str,
        unit_scale: float,
        active_scene_name: str,
        dirty_flag: bool | None = None,
    ) -> None:
        with self.db.session() as session:
            record = session.get(ProjectRecord, project_id)
            if record is None:
                raise KeyError(project_id)
            record.name = name
            record.blend_file_path = blend_file_path
            record.workspace_root = workspace_root
            record.template_type = template_type
            record.unit_scale = unit_scale
            record.active_scene_name = active_scene_name
            if dirty_flag is not None:
                record.dirty_flag = 1 if dirty_flag else 0
            record.updated_at = utc_now_iso()

    def mark_dirty(self, project_id: str, active_scene_name: str) -> None:
        with self.db.session() as session:
            record = session.get(ProjectRecord, project_id)
            if record is None:
                raise KeyError(project_id)
            record.updated_at = utc_now_iso()
            record.active_scene_name = active_scene_name
            record.dirty_flag = 1

    def set_status(self, project_id: str, status: str) -> None:
        with self.db.session() as session:
            record = session.get(ProjectRecord, project_id)
            if record is None:
                raise KeyError(project_id)
            record.status = status
            record.updated_at = utc_now_iso()

    def recent_history(self, limit: int = 20) -> list[ProjectRecord]:
        with self.db.session() as session:
            stmt = select(ProjectRecord).order_by(ProjectRecord.updated_at.desc()).limit(limit)
            return list(session.execute(stmt).scalars())


class EntityRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def upsert(self, *, entity_id: str, project_id: str, entity_type: str, name: str, spec: dict[str, Any]) -> None:
        with self.db.session() as session:
            record = session.get(EntityRecord, entity_id)
            timestamp = utc_now_iso()
            if record is None:
                record = EntityRecord(
                    entity_id=entity_id,
                    project_id=project_id,
                    entity_type=entity_type,
                    name=name,
                    spec_json=json_dumps(spec),
                    created_at=timestamp,
                    updated_at=timestamp,
                )
                session.add(record)
            else:
                record.project_id = project_id
                record.entity_type = entity_type
                record.name = name
                record.spec_json = json_dumps(spec)
                record.updated_at = timestamp

    def get(self, entity_id: str) -> EntityRecord | None:
        with self.db.session() as session:
            return session.get(EntityRecord, entity_id)

    def create(self, *, entity_id: str, project_id: str, entity_type: str, name: str, spec_json: str) -> EntityRecord:
        timestamp = utc_now_iso()
        record = EntityRecord(
            entity_id=entity_id,
            project_id=project_id,
            entity_type=entity_type,
            name=name,
            spec_json=spec_json,
            created_at=timestamp,
            updated_at=timestamp,
        )
        with self.db.session() as session:
            session.add(record)
        return record

    def update_spec(self, entity_id: str, spec_json: str) -> None:
        with self.db.session() as session:
            record = session.get(EntityRecord, entity_id)
            if record is None:
                raise KeyError(entity_id)
            record.spec_json = spec_json
            record.updated_at = utc_now_iso()

    def delete(self, entity_id: str) -> None:
        with self.db.session() as session:
            record = session.get(EntityRecord, entity_id)
            if record is not None:
                session.delete(record)

    def list_by_type(self, project_id: str, entity_type: str) -> list[EntityRecord]:
        with self.db.session() as session:
            stmt = (
                select(EntityRecord)
                .where(EntityRecord.project_id == project_id)
                .where(EntityRecord.entity_type == entity_type)
                .order_by(EntityRecord.created_at)
            )
            return list(session.execute(stmt).scalars())


class OperationRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def start(self, **data: Any) -> OperationRecord:
        record = OperationRecord(
            warnings_json="[]",
            errors_json="[]",
            output_json="{}",
            started_at=utc_now_iso(),
            **data,
        )
        with self.db.session() as session:
            session.add(record)
        return record

    def complete(
        self,
        operation_id: str,
        *,
        status: str,
        output_payload: dict[str, Any],
        warnings: list[str],
        errors: list[str],
    ) -> None:
        with self.db.session() as session:
            record = session.get(OperationRecord, operation_id)
            if record is None:
                raise KeyError(operation_id)
            completed_at = utc_now_iso()
            record.status = status
            record.output_json = json_dumps(output_payload)
            record.warnings_json = json_dumps(warnings)
            record.errors_json = json_dumps(errors)
            record.completed_at = completed_at
            started = utc_now().fromisoformat(record.started_at)
            ended = utc_now().fromisoformat(completed_at)
            record.duration_ms = int((ended - started).total_seconds() * 1000)

    def recent_by_project(self, project_id: str, limit: int = 20) -> list[OperationRecord]:
        with self.db.session() as session:
            stmt = (
                select(OperationRecord)
                .where(OperationRecord.project_id == project_id)
                .order_by(OperationRecord.started_at.desc())
                .limit(limit)
            )
            return list(session.execute(stmt).scalars())


class SnapshotRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def create(self, **data: Any) -> SnapshotRecord:
        record = SnapshotRecord(created_at=utc_now_iso(), diff_summary_json="{}", **data)
        with self.db.session() as session:
            session.add(record)
        return record

    def get(self, snapshot_id: str) -> SnapshotRecord | None:
        with self.db.session() as session:
            return session.get(SnapshotRecord, snapshot_id)

    def lookup_by_project(self, project_id: str, limit: int = 20) -> list[SnapshotRecord]:
        with self.db.session() as session:
            stmt = (
                select(SnapshotRecord)
                .where(SnapshotRecord.project_id == project_id)
                .order_by(SnapshotRecord.created_at.desc())
                .limit(limit)
            )
            return list(session.execute(stmt).scalars())

    def update_provenance(
        self,
        snapshot_id: str,
        *,
        source_operation_id: str | None = None,
        reason: str | None = None,
    ) -> None:
        with self.db.session() as session:
            record = session.get(SnapshotRecord, snapshot_id)
            if record is None:
                raise KeyError(snapshot_id)
            if source_operation_id is not None:
                record.source_operation_id = source_operation_id
            if reason is not None:
                record.reason = reason


class QAReportRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def create(self, **data: Any) -> QAReportRecord:
        payload = dict(data)
        payload["severity_summary_json"] = json_dumps(payload.pop("severity_summary", {}))
        payload["report_json"] = json_dumps(payload.pop("report", {}))
        record = QAReportRecord(created_at=utc_now_iso(), **payload)
        with self.db.session() as session:
            session.add(record)
        return record

    def latest_for_entity(self, entity_id: str) -> QAReportRecord | None:
        with self.db.session() as session:
            stmt = (
                select(QAReportRecord)
                .where(QAReportRecord.entity_id == entity_id)
                .order_by(QAReportRecord.created_at.desc())
                .limit(1)
            )
            return session.execute(stmt).scalar_one_or_none()


class ExportRecordRepository:
    def __init__(self, db: DatabaseManager):
        self.db = db

    def create(self, **data: Any) -> ExportRecordRow:
        payload = dict(data)
        payload["metadata_json"] = json_dumps(payload.pop("metadata", {}))
        payload["warnings_json"] = json_dumps(payload.pop("warnings", []))
        record = ExportRecordRow(created_at=utc_now_iso(), **payload)
        with self.db.session() as session:
            session.add(record)
        return record

    def history_by_format(self, project_id: str, export_format: str) -> list[ExportRecordRow]:
        with self.db.session() as session:
            stmt = (
                select(ExportRecordRow)
                .where(
                    ExportRecordRow.project_id == project_id,
                    ExportRecordRow.format == export_format,
                )
                .order_by(ExportRecordRow.created_at.desc())
            )
            return list(session.execute(stmt).scalars())


def decode_json_column(value: str) -> Any:
    return json_loads(value)
