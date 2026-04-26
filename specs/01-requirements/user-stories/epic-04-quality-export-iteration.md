# Epic 04: Quality, Export, and Iteration

## Outcome

The system must support structured QA, auto-repair, optimization, export, and repeatable change tracking.

## User Stories

### US-QE-001

As a QA reviewer, I want machine-readable inspection data so that I can reason about geometry, material quality, scale, naming, and export readiness without manual viewport inspection only.

Acceptance criteria:

- Scene, object, mesh, material, scale, naming, and export-readiness inspections return structured JSON-compatible content.
- Reports include severity, finding code, target object references, and recommended remediation.
- Reports can be attached to history records and compared between revisions.

### US-QE-002

As a human director, I want the AI to repair common mesh issues automatically so that small technical defects do not block the creative loop.

Acceptance criteria:

- The system can remove duplicate vertices, recalculate normals, apply transforms, and clean unused data.
- Auto-repair actions are logged and reversible through snapshots.
- The system distinguishes between safe repairs and operations that may alter silhouette or UV layout.

### US-QE-003

As an integrator, I want target-specific export presets so that web, game, render, print, and archive outputs can be generated consistently.

Acceptance criteria:

- Export tools support format-specific presets for glTF/GLB, FBX, OBJ, USD/USDZ, STL, and .blend packaging where supported.
- The system records export settings, output paths, and validation warnings.
- Unsupported feature mappings are reported explicitly instead of being silently dropped.

### US-QE-004

As an operator, I want complete history and rollback so that every AI action is auditable and recoverable.

Acceptance criteria:

- Every significant tool call records input parameters, output summary, warnings, errors, and changed object references.
- The history view can filter by project, tool family, time range, and severity.
- Rollback restores a prior snapshot and records a rollback operation event.