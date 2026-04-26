# Glossary

| Term | Definition |
| --- | --- |
| Asset | A reusable 3D deliverable or intermediate object such as a prop, furniture item, building shell, material set, scene, or world fragment. |
| AssetSpec | The structured metadata contract that describes an asset’s category, purpose, quality target, constraints, and semantic part structure. |
| Blender Controller | The component that translates validated server requests into Blender Python API calls and workflow modules. |
| Blender Runtime | The running Blender process that owns scene state, evaluates geometry, renders outputs, and performs import/export operations. |
| Confirmation Gate | A mandatory acknowledgment requirement for destructive or high-impact operations such as delete, overwrite, rollback, or mass replacement. |
| Director Workflow | The operating model in which the human user reviews results and gives intent, while the LLM performs execution through MCP tools. |
| Generation Module | A domain-specific controller module that creates or revises assets, scenes, worlds, materials, lighting, or QA artifacts. |
| Geometry Nodes | Blender’s node-based procedural geometry system used for scattering, terrain generation, modular construction, and high-volume placement tasks. |
| MCP | Model Context Protocol, the protocol used by LLM clients to discover and invoke tools, resources, and prompts. |
| PartSpec | The structured description of a semantic part inside an asset, including role, symmetry, detail level, and object bindings. |
| Preview Render | A fast render intended for iterative review rather than final delivery. |
| QA Report | A structured machine-readable inspection output covering mesh quality, naming, scale, export readiness, and optimization findings. |
| Safe Mode | A server-side execution mode that tightens validation, applies lower resource ceilings, and blocks ambiguous destructive operations. |
| SceneSpec | The structured definition of a composed scene containing assets, environment, cameras, and lighting. |
| Snapshot | A point-in-time capture of a project state used for rollback, comparison, and auditability. |
| Streamable HTTP | The MCP network transport that uses HTTP POST and optional SSE-based streaming. |
| Tool Call | A model-initiated action invocation against the MCP server with typed input and structured output. |
| WorldSpec | The structured definition of a larger environment or world region including terrain, biomes, landmarks, roads, and region hierarchy. |