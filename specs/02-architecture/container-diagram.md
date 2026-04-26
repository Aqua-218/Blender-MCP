# Container Diagram

## Container View

```mermaid
flowchart TB
    classDef app fill:#dbeafe,stroke:#1d4ed8,color:#111827
    classDef infra fill:#dcfce7,stroke:#15803d,color:#111827
    classDef data fill:#ede9fe,stroke:#6d28d9,color:#111827

    subgraph ClientSide[Client Side]
        Client[MCP Client]:::infra
    end

    subgraph ServerSide[Blender MCP Server Process]
        FastMCP[FastMCP Tool Surface]:::app
        Policy[Schema Validation and Safety Policy]:::app
        Orchestrator[Job Orchestrator and Target Resolver]:::app
        History[History and Snapshot Service]:::app
        BridgeClient[Controller Bridge Client]:::app
    end

    subgraph BlenderSide[Blender Runtime Process]
        BridgeServer[Controller Bridge Server]:::app
        DomainModules[Project / Object / Model / Scene / World / Render / QA / Export Modules]:::app
        Bpy[bpy / bmesh / Geometry Nodes / Render Engines]:::app
    end

    SQLite[(SQLite Metadata)]:::data
    Workspace[(Workspace Artifacts)]:::data

    Client --> FastMCP
    FastMCP --> Policy
    Policy --> Orchestrator
    Orchestrator --> History
    Orchestrator --> BridgeClient
    History --> SQLite
    BridgeClient --> BridgeServer
    BridgeServer --> DomainModules
    DomainModules --> Bpy
    Bpy --> Workspace
    History --> Workspace
```

## Description

The server process is responsible for all protocol-facing behavior and policy decisions. The Blender process is responsible for all scene-stateful work. SQLite stores structured metadata, while the filesystem stores artifacts and snapshot payloads.