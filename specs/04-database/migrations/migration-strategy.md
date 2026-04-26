# Migration Strategy

## Tooling

- Alembic for versioned migrations
- SQLAlchemy metadata as the canonical schema definition

## Rules

- Every schema change must be forward-migratable without manual SQL edits in production environments.
- Destructive schema changes require an explicit compatibility plan.
- The server checks migration state at startup and refuses unsafe mixed-schema execution.

## Zero-Downtime Guidance

For the local-first product, strict zero-downtime is not a hard requirement, but migrations must still be safe:

1. Add new columns as nullable or with defaults.
2. Backfill application-visible data.
3. Switch application reads and writes.
4. Remove obsolete fields only in a later version.