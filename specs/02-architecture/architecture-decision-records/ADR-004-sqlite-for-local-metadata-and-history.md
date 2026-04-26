# ADR-004: SQLite for Local Metadata and History

## Status

Accepted

## Context

The product requires persistent storage for projects, operation logs, snapshots, QA reports, and export history. The dominant deployment target is a single workstation-local application server with low concurrent write pressure.

## Decision

Use SQLite as the metadata store for the first implementation and medium-scale workstation deployments.

## Consequences

### Positive

- Zero-admin local database.
- Good fit for application-local storage.
- Easy backup and portability as a single file.

### Negative

- Only one writer at a time per database file.
- Not suitable for a highly concurrent multi-host control plane.

### Risks

- If future deployments become multi-node with many concurrent writers, migration to a client/server database will be required.

## Alternatives Considered

### Alternative 1: PostgreSQL from Day One

- Description: Use a client/server relational database immediately.
- Pros: Better remote concurrency and scaling headroom.
- Cons: Higher setup and operational cost for a workstation-first product.
- Rejection Reason: Overkill for the initial deployment model.

### Alternative 2: JSON Files Only

- Description: Persist metadata as flat files only.
- Pros: Minimal dependencies.
- Cons: Weak querying, weaker concurrency, weak indexing, and brittle history management.
- Rejection Reason: History, diffing, and QA queries deserve structured storage.