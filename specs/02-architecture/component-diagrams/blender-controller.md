# Blender Controller Components

## Component Diagram

```mermaid
flowchart LR
    classDef app fill:#dbeafe,stroke:#1d4ed8,color:#111827
    classDef engine fill:#dcfce7,stroke:#15803d,color:#111827

    Bridge[Bridge Server]:::app
    Queue[Serialized Job Queue]:::app
    Session[Project Session Manager]:::app
    Project[Project Module]:::app
    Objects[Object Module]:::app
    Models[Model Generation Module]:::app
    Scenes[Scene and World Module]:::app
    Materials[Material and Texture Module]:::app
    Render[Render Module]:::app
    QA[Inspection and Optimization Module]:::app
    Export[Import and Export Module]:::app
    BlenderAPI[Blender Python API]:::engine

    Bridge --> Queue
    Queue --> Session
    Session --> Project
    Session --> Objects
    Session --> Models
    Session --> Scenes
    Session --> Materials
    Session --> Render
    Session --> QA
    Session --> Export
    Project --> BlenderAPI
    Objects --> BlenderAPI
    Models --> BlenderAPI
    Scenes --> BlenderAPI
    Materials --> BlenderAPI
    Render --> BlenderAPI
    QA --> BlenderAPI
    Export --> BlenderAPI
```

## Responsibilities

- Bridge Server: authenticate local RPC, parse requests, emit progress, and return structured results
- Serialized Job Queue: ensure Blender mutations execute in a predictable sequence per runtime
- Project Session Manager: open, save, snapshot hooks, active project lifecycle, and scene context tracking
- Domain Modules: encapsulate modeling, materials, lighting, render, QA, and export operations as reusable functions

## Execution Rules

- All mutating bpy work executes through one serialized job queue per Blender runtime.
- Long-running tasks periodically emit progress and heartbeat events.
- Controller responses include created, modified, and deleted object references whenever practical.
- Domain modules must remain pure at the planning level and Blender-specific only at the final execution layer.