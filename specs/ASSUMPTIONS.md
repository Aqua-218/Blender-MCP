# Assumptions

| ID | Assumption | Rationale | Validation Status |
| --- | --- | --- | --- |
| A-001 | The primary deployment target is a local workstation running Blender and an MCP-capable desktop client. | The target client list is dominated by desktop tools such as VS Code, Cursor, Claude Desktop, and ChatGPT desktop-style integrations. | Assumed |
| A-002 | Blender 5.1 is the baseline compatibility target for the first implementation wave. | The latest official API and manual pages referenced in this design are for Blender 5.1. | Assumed |
| A-003 | The MCP server must support stdio from day one. | The MCP specification recommends stdio whenever possible, and desktop clients commonly rely on subprocess-based server launch. | Validated by source |
| A-004 | Streamable HTTP is optional but required for hosted and browser-based integrations. | The official MCP transport specification defines Streamable HTTP as the production-grade network transport. | Validated by source |
| A-005 | A single Blender runtime manages one active .blend editing context at a time. | Blender-as-application and Blender-as-module both retain a single active blend restriction per runtime. | Validated by source |
| A-006 | The system may launch multiple Blender runtimes if true concurrency is required, but each runtime remains isolated to one active project. | This is the safest scaling model that respects Blender state isolation. | Assumed |
| A-007 | Local SQLite is sufficient for metadata, history, and QA storage in the initial and medium-scale phases. | Metadata writes are serialized by the MCP server and remain application-local. | Validated by source |
| A-008 | The server must never execute arbitrary shell commands on behalf of the LLM. | This is a non-negotiable safety boundary and is explicitly required by the product brief. | Accepted constraint |
| A-009 | All file reads and writes occur inside allowlisted workspace roots configured by the operator. | This is necessary to constrain destructive and exfiltration-capable behaviors. | Accepted constraint |
| A-010 | Character, cloth, hair, rigging, and advanced animation remain experimental capability families until dedicated validation exists. | The product brief explicitly marks them as phased and lower-confidence. | Accepted constraint |
| A-011 | Export correctness is format-specific; the system will provide export-readiness checks and per-format warnings rather than universal lossless guarantees. | glTF triangulates meshes and has material constraints; FBX has instancing and material limitations. | Validated by source |
| A-012 | Asset library editing across multiple blend files must respect Blender’s current-file write limitation. | Blender documentation states Blender itself cannot write arbitrary external blend files in-place without opening them. | Validated by source |
| A-013 | The controller bridge must expose progress events for long-running tasks such as rendering, terrain generation, geometry-node scattering, and bulk export. | The product requires partial completion, progress visibility, and timeout handling. | Accepted requirement |
| A-014 | The first production implementation will prioritize hard-surface props, furniture, exterior building shells, and small display scenes. | This aligns with the requested MVP boundary. | Accepted requirement |
| A-015 | The system will prefer reusable procedural templates, modifiers, and geometry nodes over destructive mesh baking until export or explicit apply operations require baking. | This preserves editability for iterative direction changes. | Accepted design choice |

## Validation Notes

- Assumptions marked “Validated by source” are supported by the evidence list in [README.md](README.md).
- Assumptions marked “Assumed” should be confirmed during project kickoff, but they are safe defaults for implementation planning.