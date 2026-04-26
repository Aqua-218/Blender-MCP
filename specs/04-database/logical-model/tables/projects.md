# Table: projects

## Purpose

Stores the active and historical identity of a Blender project.

## Columns

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| project_id | TEXT | PK, NOT NULL | Stable project identifier |
| name | TEXT | NOT NULL | Human-readable project name |
| blend_file_path | TEXT | NOT NULL, UNIQUE | Canonical project file path |
| workspace_root | TEXT | NOT NULL | Allowlisted root for this project |
| template_type | TEXT | NOT NULL | Initial project template |
| unit_scale | REAL | NOT NULL | Blender scene unit scale |
| active_scene_name | TEXT | NOT NULL | Last known active scene |
| status | TEXT | NOT NULL | active, archived, or failed_recovery |
| created_at | TEXT | NOT NULL | UTC timestamp |
| updated_at | TEXT | NOT NULL | UTC timestamp |
| last_saved_at | TEXT | NULL | UTC timestamp |
| dirty_flag | INTEGER | NOT NULL DEFAULT 0 | 0 false, 1 true |

## Indexes

- UNIQUE INDEX on blend_file_path
- INDEX on updated_at DESC

## Integrity Rules

- blend_file_path must remain under workspace_root.
- unit_scale must be greater than 0.