# Logical Model Overview

## Tables

- [tables/projects.md](tables/projects.md)
- [tables/entities.md](tables/entities.md)
- [tables/operations.md](tables/operations.md)
- [tables/snapshots.md](tables/snapshots.md)
- [tables/qa_reports.md](tables/qa_reports.md)
- [tables/export_records.md](tables/export_records.md)

## Conventions

- Primary keys use text UUID-style identifiers.
- All timestamps are stored in UTC ISO 8601 string format.
- JSON columns store typed metadata envelopes validated at the application layer.
- Soft deletion is avoided for core history tables; history is append-oriented.