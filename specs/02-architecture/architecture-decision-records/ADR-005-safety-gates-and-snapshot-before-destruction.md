# ADR-005: Safety Gates and Snapshot-Before-Destruction

## Status

Accepted

## Context

The system allows model-controlled tool execution against a local creative workspace. High-impact operations such as delete, overwrite, rollback, batch replace, heavy optimization, and export-preparation apply irreversible or costly changes.

## Decision

Introduce two mandatory safety mechanisms:

1. Policy-based confirmation gates for destructive actions
2. Automatic snapshot creation before configured destructive or high-blast-radius actions

## Consequences

### Positive

- Reduces irreversible AI mistakes.
- Improves auditability and rollback reliability.
- Makes local repair loops safer for human-directed use.

### Negative

- Adds latency and storage overhead.
- Requires careful operation classification and policy tuning.

### Risks

- Too many forced confirmations can hurt UX.
- Too many snapshots can inflate disk usage.

## Alternatives Considered

### Alternative 1: Confirmation Only

- Description: Ask for confirmation but do not snapshot automatically.
- Pros: Less storage overhead.
- Cons: Rollback depends on human discipline.
- Rejection Reason: The product explicitly values safe iterative correction.

### Alternative 2: Snapshot Everything

- Description: Snapshot before every mutation.
- Pros: Maximum recoverability.
- Cons: Excessive storage and latency cost.
- Rejection Reason: Too expensive for routine low-risk edits.