# MCP Server Components

## Component Diagram

```mermaid
flowchart LR
    classDef app fill:#dbeafe,stroke:#1d4ed8,color:#111827
    classDef data fill:#ede9fe,stroke:#6d28d9,color:#111827

    FastMCP[FastMCP Server]:::app
    Catalog[Tool Catalog]:::app
    Validator[Input Schema Validator]:::app
    Policy[Safety Policy Engine]:::app
    Resolver[Target Resolver]:::app
    Planner[Execution Planner]:::app
    Bridge[Bridge Adapter]:::app
    History[History Service]:::app
    Snapshot[Snapshot Service]:::app
    Artifact[Artifact Manager]:::app
    DB[(SQLite Repository)]:::data

    FastMCP --> Catalog
    Catalog --> Validator
    Validator --> Policy
    Policy --> Resolver
    Resolver --> Planner
    Planner --> Bridge
    Planner --> History
    Policy --> Snapshot
    Snapshot --> Artifact
    History --> DB
    Snapshot --> DB
    Artifact --> DB
```

## Responsibilities

- FastMCP Server: protocol lifecycle, tool exposure, progress forwarding, and transport handling
- Tool Catalog: tool descriptions, input schemas, output schemas, titles, and capability discovery
- Input Schema Validator: request-shape validation and normalization
- Safety Policy Engine: directory checks, budget checks, destructive-operation gates, and format allowlists
- Target Resolver: object, part, collection, and region resolution
- Execution Planner: converts validated tool intent into controller commands and pre/post hooks
- Bridge Adapter: local RPC to Blender controller with correlation IDs, retries, and heartbeat checks
- History Service: operation records, warnings, errors, and result summaries
- Snapshot Service: policy-driven capture and restoration support
- Artifact Manager: canonical path generation for renders, exports, and snapshot payloads

## Failure Modes and Handling

- Validation failure: reject request before Blender call
- Policy violation: reject request with structured error and remediation
- Bridge timeout: mark operation partial or failed, preserve request record, and attempt controller health probe
- Blender execution error: capture traceback, map to structured tool error, and preserve rollback path if available