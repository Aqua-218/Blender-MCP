"""initial metadata schema

Revision ID: 0001_initial
Revises:
Create Date: 2026-04-24 00:00:00
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op

revision = "0001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("blend_file_path", sa.String(), nullable=False),
        sa.Column("workspace_root", sa.String(), nullable=False),
        sa.Column("template_type", sa.String(), nullable=False),
        sa.Column("unit_scale", sa.Float(), nullable=False),
        sa.Column("active_scene_name", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("last_saved_at", sa.String(), nullable=True),
        sa.Column("dirty_flag", sa.Integer(), nullable=False, server_default="0"),
        sa.PrimaryKeyConstraint("project_id"),
        sa.UniqueConstraint("blend_file_path"),
    )
    op.create_index("ix_projects_updated_at_desc", "projects", ["updated_at"], unique=False)

    op.create_table(
        "entities",
        sa.Column("entity_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("spec_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("entity_id"),
    )
    op.create_index("ix_entities_project_id_name", "entities", ["project_id", "name"], unique=False)

    op.create_table(
        "operations",
        sa.Column("operation_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("request_id", sa.String(), nullable=False),
        sa.Column("tool_name", sa.String(), nullable=False),
        sa.Column("target_entity_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("user_instruction", sa.Text(), nullable=True),
        sa.Column("input_json", sa.Text(), nullable=False),
        sa.Column("output_json", sa.Text(), nullable=False),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("errors_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("started_at", sa.String(), nullable=False),
        sa.Column("completed_at", sa.String(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("operation_id"),
        sa.UniqueConstraint("request_id"),
    )
    op.create_index(
        "ix_operations_project_started",
        "operations",
        ["project_id", "started_at"],
        unique=False,
    )
    op.create_index(
        "ix_operations_project_tool_started",
        "operations",
        ["project_id", "tool_name", "started_at"],
        unique=False,
    )

    op.create_table(
        "snapshots",
        sa.Column("snapshot_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("source_operation_id", sa.String(), nullable=True),
        sa.Column("reason", sa.String(), nullable=False),
        sa.Column("snapshot_path", sa.String(), nullable=False),
        sa.Column("diff_summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.ForeignKeyConstraint(["source_operation_id"], ["operations.operation_id"]),
        sa.PrimaryKeyConstraint("snapshot_id"),
    )
    op.create_index(
        "ix_snapshots_project_created",
        "snapshots",
        ["project_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_snapshots_source_operation",
        "snapshots",
        ["source_operation_id"],
        unique=False,
    )

    op.create_table(
        "qa_reports",
        sa.Column("qa_report_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("source_operation_id", sa.String(), nullable=True),
        sa.Column("severity_summary_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.entity_id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.ForeignKeyConstraint(["source_operation_id"], ["operations.operation_id"]),
        sa.PrimaryKeyConstraint("qa_report_id"),
    )
    op.create_index(
        "ix_qa_reports_entity_created",
        "qa_reports",
        ["entity_id", "created_at"],
        unique=False,
    )

    op.create_table(
        "export_records",
        sa.Column("export_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(), nullable=True),
        sa.Column("format", sa.String(), nullable=False),
        sa.Column("output_path", sa.String(), nullable=False),
        sa.Column("metadata_json", sa.Text(), nullable=False, server_default="{}"),
        sa.Column("warnings_json", sa.Text(), nullable=False, server_default="[]"),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.ForeignKeyConstraint(["entity_id"], ["entities.entity_id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.project_id"]),
        sa.PrimaryKeyConstraint("export_id"),
    )
    op.create_index(
        "ix_export_records_entity_format",
        "export_records",
        ["entity_id", "format"],
        unique=False,
    )
    op.create_index(
        "ix_export_records_project_created",
        "export_records",
        ["project_id", "created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_export_records_project_created", table_name="export_records")
    op.drop_index("ix_export_records_entity_format", table_name="export_records")
    op.drop_table("export_records")
    op.drop_index("ix_qa_reports_entity_created", table_name="qa_reports")
    op.drop_table("qa_reports")
    op.drop_index("ix_snapshots_source_operation", table_name="snapshots")
    op.drop_index("ix_snapshots_project_created", table_name="snapshots")
    op.drop_table("snapshots")
    op.drop_index("ix_operations_project_tool_started", table_name="operations")
    op.drop_index("ix_operations_project_started", table_name="operations")
    op.drop_table("operations")
    op.drop_index("ix_entities_project_id_name", table_name="entities")
    op.drop_table("entities")
    op.drop_index("ix_projects_updated_at_desc", table_name="projects")
    op.drop_table("projects")
