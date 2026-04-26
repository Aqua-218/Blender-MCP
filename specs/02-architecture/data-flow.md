# Data Flow

## Main Data Flow

```mermaid
flowchart TD
    classDef req fill:#dbeafe,stroke:#1d4ed8,color:#111827
    classDef data fill:#ede9fe,stroke:#6d28d9,color:#111827
    classDef exec fill:#dcfce7,stroke:#15803d,color:#111827

    Request[Tool Request]:::req
    Normalize[Normalize and Validate]:::req
    Policy[Apply Policy and Budgets]:::req
    Resolve[Resolve Targets and Paths]:::req
    Snapshot[Optional Pre-Change Snapshot]:::data
    Command[Controller Command Envelope]:::req
    Execute[Blender Execution]:::exec
    Artifacts[Artifacts Written to Workspace]:::data
    History[Operation and QA Metadata]:::data
    Result[Structured Tool Result]:::req

    Request --> Normalize --> Policy --> Resolve --> Snapshot --> Command --> Execute
    Execute --> Artifacts
    Execute --> History
    Artifacts --> Result
    History --> Result
```

## Data Classes

- Request data: request_id, tool_name, user instruction, structured parameters, target identifiers, policy mode
- Execution data: resolved controller command, runtime session id, progress events, controller warnings
- Artifact data: blend files, preview images, final renders, exports, logs, snapshot payloads
- Metadata data: project rows, operation logs, QA findings, snapshot indices, export records

## Data Integrity Rules

- Artifact paths are generated centrally by the server, never from raw model input alone.
- History is written even for partial failures.
- Snapshot metadata is committed before destructive controller commands run.
- Tool results always include both human-readable summary and machine-readable changed-object data.