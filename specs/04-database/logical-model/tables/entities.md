# Table: entities

## Purpose

Stores metadata for asset, scene, and world entities associated with a project.

## Columns

| Column | Type | Constraints | Notes |
| --- | --- | --- | --- |
| entity_id | TEXT | PK, NOT NULL | Stable entity identifier |
| project_id | TEXT | FK, NOT NULL | Parent project |
| entity_type | TEXT | NOT NULL | asset, scene, or world |
| name | TEXT | NOT NULL | Human-readable name |
| category | TEXT | NULL | Prop, furniture, building, world, and similar classes |
| status | TEXT | NOT NULL | draft, active, exported, archived |
| spec_json | TEXT | NOT NULL | Validated AssetSpec, SceneSpec, or WorldSpec payload |
| primary_object_ids_json | TEXT | NOT NULL | Bound Blender object IDs |
| created_at | TEXT | NOT NULL | UTC timestamp |
| updated_at | TEXT | NOT NULL | UTC timestamp |

## Indexes

- INDEX on project_id, entity_type
- INDEX on project_id, name
- INDEX on project_id, status

## Integrity Rules

- spec_json must match the schema for the declared entity_type.
- primary_object_ids_json must contain at least one object identifier for asset and scene entities after generation.