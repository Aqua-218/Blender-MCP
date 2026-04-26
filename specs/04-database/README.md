# Database Design Overview

## Scope

This database stores metadata, not primary 3D geometry. Geometry remains inside .blend files and export artifacts.

The database stores:

- project identities and paths
- asset, scene, and world metadata records
- operation history
- snapshots
- QA reports
- export records

## Storage Model

- Engine: SQLite
- File location: inside the operator-approved workspace root
- Mode: WAL enabled
- Foreign keys: enabled
- JSON fields: used for schema-rich metadata payloads such as AssetSpec, SceneSpec, and WorldSpec

## Design Goals

- Fast local reads for recent project history and QA lookups
- Strong traceability across operations and snapshots
- Minimal operational overhead
- Easy future migration to PostgreSQL if multi-node hosted deployments become necessary

## Document Map

- [conceptual-model.md](conceptual-model.md)
- [logical-model/README.md](logical-model/README.md)
- [physical-model.md](physical-model.md)
- [migrations/migration-strategy.md](migrations/migration-strategy.md)
- [migrations/migration-runbook.md](migrations/migration-runbook.md)
- [query-patterns.md](query-patterns.md)
- [backup-recovery.md](backup-recovery.md)