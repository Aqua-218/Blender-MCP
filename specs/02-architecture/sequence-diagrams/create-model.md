# Sequence Diagram: Create Model

```mermaid
sequenceDiagram
    participant U as Human Director
    participant C as MCP Client
    participant S as MCP Server
    participant H as History/Snapshot Service
    participant B as Blender Controller
    participant R as Blender Runtime

    U->>C: Request "Create a small SF drone"
    C->>S: call create_model(params)
    S->>S: Validate schema, policy, budgets
    S->>H: Record pending operation
    S->>H: Create snapshot if policy requires
    S->>B: Send controller command envelope
    B->>R: Execute generation modules
    R-->>B: Progress events
    B-->>S: Progress events
    S-->>C: Progress notifications
    R-->>B: Created objects, materials, warnings
    B-->>S: Structured controller result
    S->>H: Persist operation result and object references
    S-->>C: Structured tool result with preview suggestion
```

## Description

The server owns validation, policy, and history. Blender owns geometry creation. Progress is emitted back to the client without exposing Blender internals directly.