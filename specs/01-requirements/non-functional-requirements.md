# Non-Functional Requirements

## Operational NFRs

- NFR-001 Stability: Across the MVP regression suite, at least 99% of tool calls shall complete without crashing the MCP server or Blender runtime, and controller disconnect recovery shall succeed within 10 seconds for restartable failures.
- NFR-002 Responsiveness: Lightweight tools such as project info, object listing, selection, and metadata fetch shall complete with p95 latency below 2 seconds on the reference workstation; long-running tools shall acknowledge the request within 500 milliseconds and emit progress at least every 5 seconds.
- NFR-003 Extensibility: New tool families shall be addable without breaking existing tool names, input schemas, or result envelopes, and capability discovery shall expose additions without requiring client-specific custom code.
- NFR-004 Reproducibility: For seedable generation paths, rerunning the same tool with the same seed, template, and controller version shall produce materially equivalent topology, placement, or deterministic procedural setup unless the request explicitly opts into stochastic variation.
- NFR-005 Observability: Every significant tool execution shall emit request_id, tool_name, start_time, end_time, status, warnings, errors, and changed-resource references into durable logs and metadata records.
- NFR-006 Locality of Repair: Targeted revision operations shall modify only the declared target set plus explicitly declared dependencies, and QA diff summaries shall identify any collateral changes.
- NFR-007 Quality Improvement Loop: The system shall preserve enough metadata to support iterative generate-review-fix cycles across at least 20 successive revisions of one project without losing history or snapshot lineage.
- NFR-008 Scale Headroom: The architecture shall support instance-heavy scenes and geometry-node-driven scatter workloads without redesign of the control plane, using batch execution and budget enforcement as the scaling mechanism.

## Safety and Security Requirements

- SFR-001 Allowed directory restriction: All project, import, export, render, snapshot, and log paths shall be resolved under operator-approved workspace roots and rejected otherwise.
- SFR-002 No arbitrary shell execution: No MCP tool shall expose arbitrary shell, subprocess, or operating-system command execution initiated from model input.
- SFR-003 Destructive-operation control: Delete, overwrite, rollback, batch replace, and high-impact optimization operations shall require an explicit confirmation flag or a pre-approved policy mode.
- SFR-004 Timeouts and cancellation: Long-running operations shall have configurable soft timeouts, hard timeouts, and cancellation handling, and the controller shall report partial completion where safe.
- SFR-005 Resource limits: The server shall enforce operator-configurable ceilings for polygon budget, object count, render resolution, sample count, scatter density, bake size, and concurrent job count.
- SFR-006 External file restriction: Imported assets, textures, and references shall be validated against both extension allowlists and directory allowlists before Blender loads them.
- SFR-007 Copyright and trademark safeguards: The server shall support policy hooks that reject or flag requests aimed at faithful recreation of protected characters, logos, or trademarked product likenesses.

## Performance Requirements

- PERF-001 Quick preview: For a small-to-medium asset scene under the MVP budget, the quick preview path shall produce at least one image within 15 seconds on the reference workstation.
- PERF-002 Large scene strategy: When placing high-count repeated assets such as trees, rocks, or props, the system shall prefer instancing or Geometry Nodes rather than unique-mesh duplication.
- PERF-003 Polygon budget management: The system shall track requested and actual polygon usage per asset and shall warn within the tool result when actual counts exceed the declared budget by more than 10%.
- PERF-004 Quality presets: The system shall provide preview, standard, and final render presets with documented defaults for engine, samples, resolution, and post-process toggles.

## Quality Requirements

- QR-001 Style consistency: Assets and scenes generated under a shared style directive shall maintain consistent proportions, material language, color palette, and detail density unless the request explicitly introduces contrast.
- QR-002 Semantic structure: Supported assets shall be represented as meaningful semantic parts rather than an undifferentiated mesh whenever local revision is expected.
- QR-003 Editability: Generated outputs shall remain editable at the levels of part, material, collection, and modifier stack unless an explicit bake or destructive apply step has been requested.
- QR-004 Reviewability: Every create or revise flow that changes visible output shall be able to produce preview renders adequate for human review.
- QR-005 Inspectability: The system shall expose inspection outputs for mesh quality, materials, scale, naming, and export readiness in machine-readable form.
- QR-006 Iterative improvement: The system shall support local improvement without mandatory full regeneration and shall preserve comparison artifacts between iterations.

## Reference Workstation for Measurement

Unless otherwise negotiated, latency and render expectations in this document assume:

- Apple Silicon Mac with 32 GB RAM or better
- Local SSD workspace
- Blender 5.1 baseline runtime
- No competing heavy GPU or CPU workloads during performance validation