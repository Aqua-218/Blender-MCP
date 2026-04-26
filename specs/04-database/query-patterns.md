# Query Patterns

## Critical Queries

### Recent project history

- Query operations by project_id ordered by started_at DESC
- Used for activity views and audit trails

### Latest QA status per entity

- Query qa_reports by entity_id ordered by generated_at DESC limit 1
- Used for review dashboards and export gating

### Snapshot lookup before rollback

- Query snapshots by project_id and created_at DESC or snapshot_id exact match
- Used for reversible change control

### Export history by format

- Query export_records by project_id and format ordered by exported_at DESC
- Used for downstream pipeline verification

## Performance Notes

- SQLite indexes in the logical model are sufficient for the first deployment scale.
- JSON fields should not be the primary filter path for frequent UI lookups; stable relational fields must be indexed separately.