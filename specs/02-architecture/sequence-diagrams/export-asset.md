# Sequence Diagram: Export Asset

```mermaid
sequenceDiagram
    participant C as MCP Client
    participant S as MCP Server
    participant Q as QA Service
    participant B as Blender Controller
    participant R as Blender Runtime
    participant W as Workspace

    C->>S: call export_asset(params)
    S->>Q: Run export-readiness checks
    Q-->>S: Findings and severity
    alt Blocking findings exist
        S-->>C: Failed result with blocking issues
    else Export is allowed
        S->>B: Send export command with preset
        B->>R: Apply export settings and export
        R->>W: Write export files
        R-->>B: Export paths and format warnings
        B-->>S: Structured export result
        S-->>C: Success result with file paths and warnings
    end
```

## Description

Export is gated by target-format validation. The system returns warnings for lossy or partially supported mappings instead of pretending all Blender features survive every format.