# Deployment Diagram

## Primary Local Deployment

```mermaid
flowchart LR
    classDef host fill:#dbeafe,stroke:#1d4ed8,color:#111827
    classDef proc fill:#dcfce7,stroke:#15803d,color:#111827
    classDef data fill:#ede9fe,stroke:#6d28d9,color:#111827

    subgraph Workstation[Artist or Developer Workstation]
        Client[MCP Client]:::proc
        Server[MCP Server Process]:::proc
        Blender[Blender Runtime Process]:::proc
        DB[(SQLite DB)]:::data
        Files[(Workspace Files)]:::data
    end

    Client -->|stdio or localhost HTTP| Server
    Server -->|localhost bridge| Blender
    Server --> DB
    Server --> Files
    Blender --> Files
```

## Optional Hosted Deployment

```mermaid
flowchart LR
    classDef host fill:#dbeafe,stroke:#1d4ed8,color:#111827
    classDef proc fill:#dcfce7,stroke:#15803d,color:#111827
    classDef data fill:#ede9fe,stroke:#6d28d9,color:#111827

    BrowserClient[Browser or Remote MCP Client]:::proc
    HostedMCP[Hosted MCP Server]:::proc
    BlenderNode[Dedicated Blender Worker Node]:::proc
    Meta[(Post-MVP Shared Metadata)]:::data
    Artifact[(Shared Artifact Store)]:::data

    BrowserClient -->|Streamable HTTP| HostedMCP
    HostedMCP -->|Authenticated worker bridge| BlenderNode
    HostedMCP --> Meta
    HostedMCP --> Artifact
    BlenderNode --> Artifact
```

## Description

The primary architecture is local-first. A future hosted mode is possible, but it is not the first deployment target and would likely replace SQLite with a client/server metadata store.