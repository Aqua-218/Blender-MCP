# Epic 01: Project Lifecycle

## Outcome

The system must let an LLM client create, open, save, snapshot, compare, and restore Blender projects while preserving safety and auditability.

## User Stories

### US-PL-001

As a human director, I want the AI to create a clean project from a named template so that every session starts with the correct units, folder layout, and baseline settings.

Acceptance criteria:

- The system creates a new project only within an allowlisted workspace root.
- The response returns a project identifier, primary .blend path, and initial status.
- The project metadata store records template type, units, and creation timestamp.

### US-PL-002

As an LLM client, I want to open an existing project deterministically so that follow-up revisions use the right blend file and metadata state.

Acceptance criteria:

- The system verifies that the requested file exists and is inside an allowlisted workspace.
- The controller loads the project and rehydrates metadata state.
- The response reports the active scene, object count, dirty flag, and warnings if the file version differs from the baseline.

### US-PL-003

As a human director, I want destructive revisions to create snapshots first so that I can roll back failed or over-aggressive changes.

Acceptance criteria:

- Snapshot creation can be explicit or policy-driven before high-risk operations.
- Each snapshot stores project metadata, operation provenance, and artifact references.
- Rollback can restore a selected snapshot without writing outside the project workspace.

### US-PL-004

As a QA reviewer, I want before/after comparison renders and change summaries so that I can verify local revisions without manually hunting differences.

Acceptance criteria:

- The system can render comparison views from matching cameras.
- The system can produce a diff summary of created, modified, and deleted objects.
- The result can be attached to an operation record and QA report.

### US-PL-005

As an operator, I want save and save-as behavior to be explicit and validated so that the AI cannot accidentally overwrite important work.

Acceptance criteria:

- Overwrite requires explicit policy or confirmation.
- Save-as validates the target extension and output directory.
- Each save operation records duration, output path, and failure details if applicable.