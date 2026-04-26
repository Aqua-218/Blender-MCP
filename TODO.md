# Blender AI MCP Implementation TODO

> Status note (2026-04-26): this document started as a pre-implementation execution backlog. The detailed workstream checklists below are preserved as historical planning notes and are not the authoritative live status for the current repository.
>
> Current verified repository status:
>
> - Core and advanced server families are implemented through model generation, scene/world workflows, geometry nodes, texture/UV, animation/rigging, repair helpers, and observability support tools.
> - The repository exposes safe stdio transport, mock runtime testing, and Blender-backed runtime attach or launch paths.
> - The current automated regression suite is green at 148 passing tests.
> - Blender-backed launch validation has passed locally against Blender 5.1.1, and the repository now includes a reproducible `make test-blender-smoke` entry point for that path.
> - The repository also defines a Blender-backed CI smoke lane and a release validation runbook.
> - The repository now includes package-build validation and ready-to-edit desktop client config examples.
> - Remaining work, if any, is external to the repository implementation itself: publishing or downstream client packaging decisions.

## Document Purpose

This file is the execution backlog for turning the specification suite in `specs/` into a working Blender MCP product.

It is intentionally detailed and implementation-facing.

Use this file to:

- track the actual build order
- keep scope disciplined around the MVP
- make dependencies explicit
- define exit criteria for each phase
- avoid starting large feature families before the foundation is stable

## Current State Snapshot

- [x] Specification suite created under `specs/`
- [x] Architecture baseline selected: external Python MCP server plus persistent Blender controller
- [x] Stdio-first transport selected
- [x] SQLite selected for local metadata and history
- [x] Core capability families and phased roadmap defined
- [x] Implementation repository scaffolded
- [x] Blender controller running
- [x] MCP server running
- [x] First end-to-end asset generation flow working

## Priority Legend

- `P0`: required for MVP or critical safety baseline
- `P1`: needed immediately after MVP to stabilize iterative authoring
- `P2`: advanced capability after the revision loop is stable
- `P3`: experimental or long-tail capability

## Status Legend

- `[ ]` not started
- `[~]` in progress
- `[x]` completed
- `[!]` blocked

## Non-Negotiable Implementation Rules

- [ ] Do not implement arbitrary shell execution in any tool path.
- [ ] Keep all file IO inside allowlisted workspace roots.
- [ ] Keep validation and policy enforcement outside Blender mutation code.
- [ ] Create snapshots before destructive operations that meet the configured blast-radius threshold.
- [ ] Keep tool result envelopes consistent across all tool families.
- [ ] Preserve semantic parts and editability unless a destructive bake is explicitly required.
- [ ] Prefer preview-first workflows for heavy operations.
- [ ] Record history for every meaningful mutation.

## Global Done Definition

The repository is not considered “done” until all of the following are true:

- [x] A desktop MCP client can launch the server over stdio.
- [x] The server can attach to or launch a Blender runtime safely.
- [x] The MVP asset families can be created, reviewed, revised, saved, and exported end to end.
- [x] Snapshots, history, and QA reports are persisted.
- [x] Export-readiness checks gate lossy or invalid exports.
- [x] The security baseline is enforced by code, not documentation only.
- [x] The regression suite passes on the baseline Blender version.

## Recommended Initial Repository Layout

- [ ] Create `pyproject.toml` with Python 3.12, package metadata, dependencies, dev dependencies, and tool configuration.
- [ ] Create `.python-version` or equivalent version pinning mechanism if desired.
- [ ] Create `.gitignore` for Python, Blender temp files, renders, exports, logs, and local environments.
- [ ] Create `README.md` with local development quickstart.
- [ ] Create `.env.example` with workspace, Blender binary, safe-mode, and logging configuration.
- [ ] Create package roots:
  - [ ] `mcp_server/`
  - [ ] `blender_controller/`
  - [ ] `presets/`
  - [ ] `tests/`
  - [ ] `workspace/`
- [ ] Create internal system-data directory plan for metadata DB and controller session state.

## Workstream 00: Repository Bootstrap and Tooling

### P0 Package and Dependency Setup

- [ ] Add runtime dependencies:
  - [ ] `mcp`
  - [ ] `pydantic`
  - [ ] `sqlalchemy`
  - [ ] `alembic`
  - [ ] `typing-extensions` if needed by selected Python features
  - [ ] `orjson` if structured logging or serialization performance justifies it
- [ ] Add development dependencies:
  - [ ] `pytest`
  - [ ] `pytest-asyncio`
  - [ ] `ruff`
  - [ ] `mypy` or `pyright` depending on preferred type-check path
  - [ ] `pre-commit`

### P0 Base Configuration

- [ ] Define server settings model in `mcp_server/config.py`.
- [ ] Define controller settings model in `blender_controller/config.py` or a shared config module.
- [ ] Implement environment loading with explicit defaults.
- [ ] Define allowed workspace roots.
- [ ] Define artifact subdirectories:
  - [ ] projects
  - [ ] renders
  - [ ] exports
  - [ ] logs
  - [ ] snapshots
  - [ ] metadata

### P0 Logging and Diagnostics

- [ ] Create structured logger bootstrap in `mcp_server/logger.py`.
- [ ] Create controller-side logger bootstrap in `blender_controller/logger.py`.
- [ ] Define a shared log schema including request_id, project_id, tool_name, status, duration_ms, warnings_count, errors_count.
- [ ] Add log redaction for secrets and auth tokens.

### P0 Developer Experience

- [ ] Add a dev command for running the MCP server over stdio.
- [ ] Add a dev command for running the server in Streamable HTTP mode for local inspection.
- [ ] Add a dev command for Blender controller smoke tests.
- [ ] Add scripts or Makefile-equivalent commands for:
  - [ ] lint
  - [ ] typecheck
  - [ ] test
  - [ ] test-integration
  - [ ] schema-export

### Exit Criteria

- [ ] A new developer can install dependencies and run lint plus unit tests locally.
- [ ] The repo has a clean and repeatable local bootstrap path.

## Workstream 01: Core Domain Models and Schemas

### P0 Shared Request and Result Models

- [ ] Implement `CommonToolRequest` model matching `specs/05-api/schemas/common-request.schema.json`.
- [ ] Implement `CommonToolResult` model matching `specs/05-api/schemas/common-result.schema.json`.
- [ ] Add helpers for consistent result creation:
  - [ ] `success_result()`
  - [ ] `partial_success_result()`
  - [ ] `failed_result()`

### P0 Spec Models

- [ ] Implement `AssetSpec` model.
- [ ] Implement `PartSpec` model.
- [ ] Implement `SceneSpec` model.
- [ ] Implement `WorldSpec` model.
- [ ] Implement `OperationLog` model.
- [ ] Implement QA report models.
- [ ] Implement snapshot metadata models.
- [ ] Implement export record models.

### P0 Schema Publication

- [ ] Generate JSON Schemas from code models.
- [ ] Diff generated schemas against `specs/05-api/schemas/`.
- [ ] Decide whether `specs/05-api/schemas/` remains the source of truth or becomes generated output.
- [ ] Add CI check preventing accidental schema drift.

### Exit Criteria

- [ ] All shared request and result models validate correctly.
- [ ] JSON Schema generation is deterministic.

## Workstream 02: Metadata Database and Persistence

### P0 SQLAlchemy Models

- [ ] Implement tables for:
  - [ ] `projects`
  - [ ] `entities`
  - [ ] `operations`
  - [ ] `snapshots`
  - [ ] `qa_reports`
  - [ ] `export_records`

### P0 Database Bootstrap

- [ ] Create database engine factory.
- [ ] Enable SQLite WAL mode.
- [ ] Enable foreign keys.
- [ ] Configure busy timeout.
- [ ] Add startup migration check.

### P0 Repositories

- [ ] Create `ProjectRepository`.
- [ ] Create `EntityRepository`.
- [ ] Create `OperationRepository`.
- [ ] Create `SnapshotRepository`.
- [ ] Create `QAReportRepository`.
- [ ] Create `ExportRecordRepository`.

### P0 Migration Tooling

- [ ] Initialize Alembic.
- [ ] Create initial migration.
- [ ] Add migration smoke test.
- [ ] Add backup-before-migration helper.

### P1 Query Utilities

- [ ] Implement recent project history query.
- [ ] Implement latest QA per entity query.
- [ ] Implement export history by format query.
- [ ] Implement snapshot lookup query.

### Exit Criteria

- [ ] The metadata DB is created automatically on first run.
- [ ] Core writes and reads work under tests.
- [ ] Migration and rollback procedures are reproducible.

## Workstream 03: Workspace and Path Safety

### P0 Path Management

- [ ] Implement canonical path resolver.
- [ ] Reject paths outside allowlisted roots.
- [ ] Reject unsupported extensions for import and export.
- [ ] Normalize all output paths through a single artifact manager.

### P0 Workspace Manager

- [ ] Create workspace directory bootstrap on startup.
- [ ] Create per-project project path plan.
- [ ] Create per-project snapshot path plan.
- [ ] Create per-project render path plan.
- [ ] Create per-project export path plan.

### P0 Safety Tests

- [ ] Test path traversal attempts.
- [ ] Test symlink escape behavior if symlinks are allowed on the platform.
- [ ] Test invalid extension rejection.

### Exit Criteria

- [ ] No filesystem write occurs outside approved roots.
- [ ] All imports and exports use centrally generated paths.

## Workstream 04: Controller Bridge and Blender Runtime Lifecycle

### P0 Bridge Protocol

- [ ] Define request envelope format.
- [ ] Define progress event format.
- [ ] Define success result format.
- [ ] Define error result format.
- [ ] Define heartbeat format.
- [ ] Define cancellation format.

### P0 Authentication and Session Management

- [ ] Generate per-session controller secret.
- [ ] Pass secret securely to controller startup.
- [ ] Reject requests with missing or invalid secret.
- [ ] Rotate secret on controller restart.

### P0 Runtime Lifecycle

- [ ] Implement controller launch path using configured Blender binary.
- [ ] Implement controller attach path if a runtime is already running.
- [ ] Implement heartbeat monitoring.
- [ ] Detect controller disconnect.
- [ ] Implement safe reconnect or restart behavior.

### P0 Serialized Job Queue

- [ ] Create one mutation queue per Blender runtime.
- [ ] Prevent concurrent mutating jobs.
- [ ] Allow bounded concurrent read-only inspections only if proven safe.
- [ ] Add queue metrics.

### P0 Blender Bootstrap Script

- [ ] Create Blender startup script or bootstrap module.
- [ ] Ensure startup initializes an empty or controlled scene state.
- [ ] Ensure logging from Blender is routed back to server logs or files.
- [ ] Ensure controller can process commands without UI assumptions.

### P0 Health Checks

- [ ] Implement `ping` bridge command.
- [ ] Implement `get_runtime_info` bridge command.
- [ ] Implement version and capability reporting.

### Exit Criteria

- [ ] The server can start Blender.
- [ ] The controller accepts authenticated local requests.
- [ ] A no-op command and a simple object query succeed.
- [ ] Disconnect detection works.

## Workstream 05: MCP Server Skeleton and Transport Layer

### P0 FastMCP Server Bootstrap

- [ ] Implement `mcp_server/server.py`.
- [ ] Register server name, version, and instructions.
- [ ] Add lifespan context for config, DB, workspace manager, bridge client, and repositories.

### P0 Stdio Support

- [ ] Make stdio the default runtime mode.
- [ ] Verify clean subprocess behavior with no stdout pollution.
- [ ] Route all logs to stderr or file output only.

### P1 Streamable HTTP Support

- [ ] Add optional Streamable HTTP mode.
- [ ] Bind to localhost by default.
- [ ] Support authenticated hosted configuration later.
- [ ] Validate Origin headers in browser-facing mode.

### P0 Tool Registration Strategy

- [ ] Split tool registration by family:
  - [ ] project
  - [ ] object
  - [ ] geometry
  - [ ] model
  - [ ] material
  - [ ] render
  - [ ] inspection
  - [ ] export
- [ ] Keep initial registration focused on Core tools only.

### P0 Shared Request Pipeline

- [ ] Validate request schema.
- [ ] Resolve project context.
- [ ] Check role and destructive-operation policy.
- [ ] Resolve targets.
- [ ] Create operation history stub.
- [ ] Dispatch to controller or repository-only path.
- [ ] Finalize history record.

### Exit Criteria

- [ ] A desktop MCP client can initialize and list tools.
- [ ] A simple tool call returns a structured result.

## Workstream 06: Project Tools

### P0 Implement Core Project Tools

- [ ] `create_project`
- [ ] `open_project`
- [ ] `save_project`
- [ ] `save_project_as`
- [ ] `create_snapshot`
- [ ] `get_project_info`

### P0 `create_project` Task Breakdown

- [ ] Validate template name.
- [ ] Validate workspace root.
- [ ] Create project directory structure.
- [ ] Bootstrap new blend file path.
- [ ] Initialize Blender scene with requested units.
- [ ] Persist project metadata row.
- [ ] Return project_id and blend path.

### P0 `open_project` Task Breakdown

- [ ] Validate existing blend file path.
- [ ] Load file in Blender runtime.
- [ ] Rehydrate project metadata if present.
- [ ] Create metadata row if opening an unmanaged project is allowed.
- [ ] Return active scene and object count.

### P0 `save_project` and `save_project_as`

- [ ] Handle overwrite policy.
- [ ] Update dirty flag and last_saved_at.
- [ ] Record operation result.

### P0 Snapshot Support

- [ ] Create snapshot payload path.
- [ ] Decide snapshot payload format.
- [ ] Persist snapshot metadata.
- [ ] Link snapshot to source operation.

### P1 Rollback Support

- [ ] Implement `restore_snapshot` or `rollback_to_snapshot` bridge flow.
- [ ] Record rollback operation.
- [ ] Validate post-restore project integrity.

### Exit Criteria

- [ ] Project lifecycle tools work end to end.
- [ ] Saving and reopening the same project preserves metadata.

## Workstream 07: Object Tools

### P0 Implement Core Object Tools

- [ ] `list_objects`
- [ ] `find_objects`
- [ ] `select_object`
- [ ] `select_objects`
- [ ] `delete_object`
- [ ] `delete_objects`
- [ ] `duplicate_object`
- [ ] `rename_object`
- [ ] `transform_object`
- [ ] `set_object_visibility`
- [ ] `assign_collection`
- [ ] `tag_object`

### P0 Target Resolution

- [ ] Define stable object identifier strategy.
- [ ] Implement lookup by object name.
- [ ] Implement lookup by tag.
- [ ] Implement lookup by collection.
- [ ] Implement spatial-range filtering.

### P0 Destructive Safety

- [ ] Require confirmation for delete operations.
- [ ] Optionally auto-snapshot before bulk deletes.

### Exit Criteria

- [ ] Object queries and mutations work reliably on test scenes.
- [ ] Delete operations are gated correctly.

## Workstream 08: Geometry Tools and Blender Controller Primitives

### P0 Implement Core Geometry Tools

- [ ] `create_primitive`
- [ ] `create_custom_mesh`
- [ ] `create_curve`
- [ ] `create_text`
- [ ] `edit_mesh`
- [ ] `extrude_mesh`
- [ ] `bevel_edges`
- [ ] `merge_vertices`
- [ ] `recalculate_normals`

### P0 Controller Geometry Helpers

- [ ] Implement primitive factory helpers.
- [ ] Implement mesh construction helper from explicit arrays.
- [ ] Implement object naming and tagging after creation.
- [ ] Implement geometry helper-object creation for booleans.

### Exit Criteria

- [ ] Core geometry operations can build and modify a simple test asset.

## Workstream 09: Material, Lighting, Camera, and Preview Foundation

### P0 Materials

- [ ] `create_material`
- [ ] `apply_material`
- [ ] `set_material_property`
- [ ] `create_pbr_material`

### P0 Lighting

- [ ] `create_light`
- [ ] `set_light`
- [ ] `apply_lighting_preset`
- [ ] `auto_light_subject`

### P0 Camera

- [ ] `create_camera`
- [ ] `set_camera`
- [ ] `frame_object`
- [ ] `set_active_camera`

### P0 Render Preview

- [ ] `set_render_settings`
- [ ] `get_render_settings`
- [ ] `render_preview`
- [ ] `render_thumbnail`

### P0 Preset System

- [ ] Create material preset definitions.
- [ ] Create lighting preset definitions.
- [ ] Create render preset definitions for preview, standard, and final.

### Exit Criteria

- [ ] A primitive can be materialized, lit, framed, and preview-rendered automatically.

## Workstream 10: Phase 0 Acceptance Flow

### P0 Technical Validation Flow

- [ ] Start server.
- [ ] Start or attach Blender.
- [ ] Create project.
- [ ] Create cube.
- [ ] Create material.
- [ ] Apply material.
- [ ] Create camera.
- [ ] Create light.
- [ ] Render preview.
- [ ] Save project.

### P0 Exit Criteria

- [ ] This entire flow is automated by tests.
- [ ] This flow works from an MCP client, not just internal scripts.

## Workstream 11: MVP Core Tool Surface

### P0 Implement MVP Tools Exactly

- [ ] `create_project`
- [ ] `create_model`
- [ ] `add_detail`
- [ ] `apply_materials` or equivalent `apply_material` flow consistent with final naming
- [ ] `setup_camera` or equivalent camera tool composition consistent with final API
- [ ] `generate_lighting` or equivalent lighting preset flow consistent with final API
- [ ] `render_preview`
- [ ] `inspect_scene`
- [ ] `save_project`
- [ ] `export_asset`

### P0 Naming Reconciliation

- [ ] Reconcile user brief tool names against spec tool names where they differ.
- [ ] Decide canonical public tool names.
- [ ] Add aliases only if necessary for client compatibility.

### Exit Criteria

- [ ] Tool list exposed to clients matches the intended MVP contract.

## Workstream 12: High-Level Model Generation for MVP Asset Families

### P0 Category 1: Small SF Drone

- [ ] Implement hard-surface drone template.
- [ ] Generate body.
- [ ] Generate arms.
- [ ] Generate rotors.
- [ ] Generate landing gear.
- [ ] Generate sensor or emissive detail points.
- [ ] Support symmetry constraint.
- [ ] Support four-rotor constraint.
- [ ] Support white, black, and blue-emission palette hints.

### P0 Category 2: Premium Furniture

- [ ] Implement one premium furniture family first, likely chair or table.
- [ ] Support silhouette refinement.
- [ ] Support premium material presets.
- [ ] Preserve editable parts.

### P0 Category 3: Building Exterior

- [ ] Implement building shell template.
- [ ] Generate walls.
- [ ] Generate roof.
- [ ] Generate windows.
- [ ] Generate doors.
- [ ] Support at least modern and near-future styles in MVP.

### P0 Category 4: Small Display Scene

- [ ] Create display floor or platform.
- [ ] Place hero asset.
- [ ] Add background treatment.
- [ ] Add review camera framing.
- [ ] Add lighting preset.

### P0 Shared Generation Infrastructure

- [ ] Create generation context abstraction.
- [ ] Implement seed handling.
- [ ] Implement polygon budget checks.
- [ ] Implement warnings when budgets are exceeded.

### Exit Criteria

- [ ] One drone, one furniture item, one building shell, and one small display scene can be generated and previewed end to end.

## Workstream 13: Semantic Parts and Local Revision Loop

### P1 Part Metadata

- [ ] Implement PartSpec persistence.
- [ ] Bind parts to Blender object IDs.
- [ ] Support parent-child part relationships.
- [ ] Track symmetry metadata.
- [ ] Track part detail level.

### P1 Part Operations

- [ ] `generate_parts`
- [ ] `add_part`
- [ ] `replace_part`
- [ ] `remove_part`
- [ ] `increase_detail`
- [ ] `reduce_detail`
- [ ] `modify_silhouette`
- [ ] `restyle_model`

### P1 Locality Safety

- [ ] Implement target resolution by part_id.
- [ ] Implement blast-radius reporting.
- [ ] Verify only target parts changed when expected.
- [ ] Auto-snapshot before high-impact local revisions.

### P1 Human Review Support

- [ ] Return modified part IDs in results.
- [ ] Produce suggested next views after revision.
- [ ] Generate before/after thumbnails for revised assets.

### Exit Criteria

- [ ] The user can say “make the legs thicker” or “add detail around the rotors” and only the intended region changes.

## Workstream 14: Inspection, QA, and Diff Infrastructure

### P1 Core QA Tools

- [ ] `inspect_scene`
- [ ] `inspect_object`
- [ ] `inspect_mesh`
- [ ] `inspect_materials`
- [ ] `inspect_scale`
- [ ] `inspect_naming`
- [ ] `check_polycount`
- [ ] `check_export_readiness`
- [ ] `generate_qa_report`

### P1 Mesh QA Findings

- [ ] Vertex count
- [ ] Face count
- [ ] Triangle count
- [ ] Non-manifold detection
- [ ] Duplicate vertex detection
- [ ] Normal issue detection
- [ ] Internal face detection
- [ ] Extreme aspect-ratio face detection
- [ ] Extreme scale detection

### P1 Scene QA Findings

- [ ] Object counts
- [ ] Mesh counts
- [ ] Camera counts
- [ ] Light counts
- [ ] Material counts
- [ ] Collection counts
- [ ] Total vertices and faces

### P1 Diff and Comparison

- [ ] `compare_snapshots`
- [ ] `generate_diff_summary`
- [ ] `render_comparison_views`

### Exit Criteria

- [ ] Every major mutation can be followed by machine-readable QA and a useful diff summary.

## Workstream 15: Repair and Optimization Tools

### P1 Repair Tools

- [ ] `fix_mesh`
- [ ] `remove_duplicate_vertices`
- [ ] `recalculate_normals`
- [ ] `clean_unused_data`
- [ ] `apply_transforms`
- [ ] `set_origin`

### P1 Optimization Tools

- [ ] `optimize_polycount`
- [ ] `generate_lod`
- [ ] `generate_collision_mesh`

### P1 Safety Rules

- [ ] Warn when repair may alter silhouette or UVs.
- [ ] Snapshot before aggressive optimization.
- [ ] Preserve original asset and create sibling LOD outputs when appropriate.

### Exit Criteria

- [ ] Common mesh cleanup actions work automatically and are reversible.

## Workstream 16: Export Pipeline

### P0 MVP Export Targets

- [ ] `export_asset` for GLB or glTF
- [ ] `export_asset` for FBX
- [ ] `.blend` save flow

### P1 Additional Export Targets

- [ ] OBJ
- [ ] USD or USDZ subject to runtime support
- [ ] STL

### P0 Export Presets

- [ ] `game`
- [ ] `web`
- [ ] `render`
- [ ] `concept`
- [ ] `print`
- [ ] `archive`

### P0 Export Validation

- [ ] Run export-readiness checks before actual export.
- [ ] Fail on blocking issues.
- [ ] Warn on lossy mappings.

### P0 GLTF-Specific Tasks

- [ ] Decide default GLB vs glTF separate behavior.
- [ ] Validate material patterns against Blender glTF exporter expectations.
- [ ] Support export settings for cameras and punctual lights when needed.

### P0 FBX-Specific Tasks

- [ ] Set axis and scaling defaults.
- [ ] Document instancing limitations.
- [ ] Document material limitations.

### Exit Criteria

- [ ] A generated MVP asset can be exported to GLB and FBX with recorded warnings and output metadata.

## Workstream 17: History, Preview History, and Rollback

### P1 Operation History

- [ ] Record every significant tool call.
- [ ] Record input params.
- [ ] Record output summary.
- [ ] Record created, modified, deleted object IDs.
- [ ] Record warnings and errors.

### P1 Preview History

- [ ] Save preview render records.
- [ ] Associate preview with project, snapshot, and operation.
- [ ] Track camera used.

### P1 Rollback

- [ ] Restore by snapshot ID.
- [ ] Log rollback event.
- [ ] Re-run project integrity checks after restore.

### Exit Criteria

- [ ] The system can show a timeline of create, revise, inspect, preview, and export operations.

## Workstream 18: Scene Composition

### P2 Scene Tools

- [ ] `create_scene`
- [ ] `place_asset`
- [ ] `scatter_assets`
- [ ] `arrange_scene`
- [ ] `generate_background`
- [ ] `generate_environment`
- [ ] `create_composition`

### P2 Scene Behaviors

- [ ] Support hero-asset display scene composition.
- [ ] Support showroom-style lighting presets.
- [ ] Support camera-aware composition suggestions.
- [ ] Support multi-view render batches.

### Exit Criteria

- [ ] A generated asset can be placed into a composed scene and rendered from multiple views automatically.

## Workstream 19: World Foundation Systems

### P2 World Tools

- [ ] `create_world`
- [ ] `generate_terrain`
- [ ] `generate_biomes`
- [ ] `generate_roads`
- [ ] `generate_water_system`
- [ ] `place_buildings`
- [ ] `scatter_vegetation`
- [ ] `create_region`
- [ ] `detail_region`
- [ ] `inspect_world`

### P2 World Metadata

- [ ] Track World, Region, Area, Location, Asset, and Part hierarchy.
- [ ] Store biome definitions.
- [ ] Store landmark definitions.
- [ ] Store world-level seed and style parameters.

### Exit Criteria

- [ ] A small world region with terrain, biome scatter, and a localized detail pass can be generated and inspected.

## Workstream 20: Modifier and Geometry Nodes Systems

### P1 Modifier Tools

- [ ] `add_modifier`
- [ ] `set_modifier`
- [ ] `apply_modifier`
- [ ] `remove_modifier`
- [ ] `list_modifiers`
- [ ] specialized helpers for bevel, mirror, array, boolean, and decimate

### P2 Geometry Nodes Tools

- [ ] `create_geometry_nodes`
- [ ] `add_geometry_node`
- [ ] `connect_geometry_nodes`
- [ ] `set_geometry_node_param`
- [ ] `create_scatter_node_setup`
- [ ] `create_procedural_building_nodes`
- [ ] `create_procedural_terrain_nodes`

### P2 Reusable Node Templates

- [ ] Terrain scatter template
- [ ] Vegetation scatter template
- [ ] Modular building template
- [ ] Road generation template

### Exit Criteria

- [ ] High-count placement uses instances or Geometry Nodes instead of naive duplication.

## Workstream 21: Texture and UV Pipeline

### P2 UV Tools

- [ ] `unwrap_uv`
- [ ] `pack_uv`
- [ ] `inspect_uv`

### P2 Texture Tools

- [ ] `apply_texture`
- [ ] `create_procedural_texture`
- [ ] `bake_texture`

### P2 Export Compatibility

- [ ] Validate glTF-friendly material and texture layouts.
- [ ] Warn when UDIM or unsupported material constructs degrade export behavior.

### Exit Criteria

- [ ] An asset can receive UVs and either procedural or image-based textures suitable for supported export paths.

## Workstream 22: Animation and Rigging

### P3 Simple Animation

- [ ] `create_keyframe_animation`
- [ ] `create_camera_animation`

### P3 Simple Rigging

- [ ] `create_simple_rig`
- [ ] `create_armature`
- [ ] `add_bone`
- [ ] `set_bone_transform`
- [ ] `auto_weight_limited`

### P3 Scope Constraints

- [ ] Limit first implementation to mechanical rigs.
- [ ] Do not promise full organic character quality.
- [ ] Keep this behind explicit feature gating until stable.

### Exit Criteria

- [ ] A simple mechanical asset can be rigged and animated for demo purposes.

## Workstream 23: Security Hardening

### P0 Authorization and Policy Enforcement

- [ ] Implement role model.
- [ ] Distinguish safe mutation vs destructive mutation.
- [ ] Restrict operator-only functions from normal creative tool exposure.

### P0 IO Restrictions

- [ ] Enforce allowed directories.
- [ ] Enforce extension allowlists.
- [ ] Redact unsafe paths from user-visible errors when needed.

### P1 Hosted-Mode Security

- [ ] Token verification for Streamable HTTP.
- [ ] Origin validation.
- [ ] Localhost binding default.
- [ ] TLS termination guidance.

### P0 Security Tests

- [ ] Path traversal tests.
- [ ] invalid secret tests.
- [ ] destructive action without confirmation tests.
- [ ] oversized workload rejection tests.

### Exit Criteria

- [ ] Unsafe requests fail before mutation.

## Workstream 24: Observability and Supportability

### P0 Metrics

- [ ] Tool call count by status.
- [ ] Tool latency percentiles.
- [ ] Controller availability.
- [ ] Bridge timeout count.
- [ ] Render duration.
- [ ] Export success rate.

### P0 Logs

- [ ] Application logs.
- [ ] Controller logs.
- [ ] Security violation logs.
- [ ] Correlation IDs across server and controller.

### P1 Support Commands

- [ ] Add internal health diagnostics endpoint or internal tool.
- [ ] Add config dump for safe non-secret values.
- [ ] Add runtime capability report.

### Exit Criteria

- [ ] Failures can be diagnosed from logs and history records without attaching a debugger in routine cases.

## Workstream 25: Testing Matrix

### P0 Unit Tests

- [ ] Settings validation
- [ ] Schema validation
- [ ] Result envelope generation
- [ ] Path safety
- [ ] Repository CRUD

### P0 Integration Tests

- [ ] Server startup
- [ ] Controller startup
- [ ] Project create/open/save
- [ ] Primitive create plus material apply
- [ ] Preview render
- [ ] Export GLB or FBX

### P1 E2E Tests

- [ ] Small SF drone flow
- [ ] Premium furniture flow
- [ ] Building shell flow
- [ ] Display scene flow

### P1 Regression Tests

- [ ] Snapshot and rollback
- [ ] Targeted local revision
- [ ] QA report generation
- [ ] export-readiness blocker path

### P2 Load and Soak Tests

- [ ] Repeated heavy render queue
- [ ] repeated snapshot loop
- [ ] scatter overload rejection
- [ ] long session controller stability

### Exit Criteria

- [ ] The baseline regression suite passes against the supported Blender version.

## Workstream 26: Client Integration and Examples

### P0 Desktop Client Integration

- [ ] Provide stdio launch config for VS Code or Copilot-compatible environments.
- [ ] Provide stdio launch config for Claude Desktop.
- [ ] Provide example env configuration.

### P1 Demo Scripts and Walkthroughs

- [ ] “Create SF drone” demo
- [ ] “Revise one part” demo
- [ ] “Render and export” demo

### P1 Docs

- [ ] Installation guide
- [ ] Troubleshooting guide
- [ ] Tool catalog reference
- [ ] Safety model reference

### Exit Criteria

- [ ] A new user can connect one desktop client and run the MVP flow with documented setup only.

## Workstream 27: Release Readiness

### P0 Packaging

- [ ] Version package correctly.
- [ ] Pin dependencies.
- [ ] Generate release notes from milestone status.

### P0 Compatibility Matrix

- [ ] Declare supported Blender version(s).
- [ ] Declare supported MCP transport modes.
- [ ] Declare supported export targets for MVP.

### P0 Release Gate Checklist

- [ ] lint passes
- [ ] unit tests pass
- [ ] integration smoke tests pass
- [ ] MVP E2E flow passes
- [ ] schema bundle updated
- [ ] docs updated

### Exit Criteria

- [ ] The first tagged release is installable and passes the MVP acceptance tests.

## Phase-by-Phase Execution Plan

### Phase 0: Technical Validation

- [ ] Complete Workstreams 00 through 10.

#### Phase 0 Exit Gate

- [ ] Server starts.
- [ ] Blender controller starts.
- [ ] Project lifecycle basics work.
- [ ] Primitive plus material plus camera plus light plus preview plus save works.

### Phase 1: MCP MVP

- [ ] Complete Workstreams 11, 12, and minimum export path from 16.

#### Phase 1 Exit Gate

- [ ] Desktop MCP client can call Core tools.
- [ ] One full MVP asset flow works end to end.
- [ ] GLB or FBX export works.

### Phase 2: Asset Generation Depth

- [ ] Complete Workstreams 13 and the remaining material and modifier depth needed for local revision quality.

#### Phase 2 Exit Gate

- [ ] Semantic parts exist.
- [ ] Local revisions are targeted.
- [ ] Materials and silhouette changes are usable in review loops.

### Phase 3: Inspection and Repair

- [ ] Complete Workstreams 14, 15, and history improvements in 17.

#### Phase 3 Exit Gate

- [ ] QA reports are machine-readable and useful.
- [ ] Common repair actions are reversible.

### Phase 4: Scene Composition

- [ ] Complete Workstream 18 and multi-view rendering depth.

#### Phase 4 Exit Gate

- [ ] Assets can be placed into composed scenes with review-ready lighting and camera framing.

### Phase 5: World Systems

- [ ] Complete Workstream 19.

#### Phase 5 Exit Gate

- [ ] Small world region generation works with local detail passes.

### Phase 6: Advanced Workflow

- [ ] Complete the stable subset of Workstreams 20, 21, and 22.

#### Phase 6 Exit Gate

- [ ] Geometry Nodes workflows, LOD generation, and limited mechanical animation paths are production-usable.

## Explicit Backlog That Must Not Creep Into MVP

- [ ] Full humanoid character generation
- [ ] high-quality cloth and hair systems
- [ ] advanced facial rigging
- [ ] full production animation library export
- [ ] multi-user collaborative editing
- [ ] generalized cloud render farm orchestration

## First Concrete File Creation Order

This is the recommended order for the first real implementation PRs.

1. [ ] `pyproject.toml`
2. [ ] `README.md`
3. [ ] `mcp_server/config.py`
4. [ ] `mcp_server/logger.py`
5. [ ] `mcp_server/server.py`
6. [ ] `mcp_server/models/common.py`
7. [ ] `mcp_server/db/base.py`
8. [ ] `mcp_server/db/models.py`
9. [ ] `mcp_server/db/repositories.py`
10. [ ] `mcp_server/workspace.py`
11. [ ] `mcp_server/policy.py`
12. [ ] `mcp_server/bridge/client.py`
13. [ ] `blender_controller/bootstrap.py`
14. [ ] `blender_controller/controller.py`
15. [ ] `blender_controller/project.py`
16. [ ] `blender_controller/objects.py`
17. [ ] `blender_controller/geometry.py`
18. [ ] `blender_controller/materials.py`
19. [ ] `blender_controller/lighting.py`
20. [ ] `blender_controller/cameras.py`
21. [ ] `blender_controller/rendering.py`
22. [ ] `mcp_server/tools/project_tools.py`
23. [ ] `mcp_server/tools/object_tools.py`
24. [ ] `mcp_server/tools/geometry_tools.py`
25. [ ] `mcp_server/tools/material_tools.py`
26. [ ] `mcp_server/tools/render_tools.py`
27. [ ] `tests/test_project_tools.py`
28. [ ] `tests/test_rendering.py`

## First End-to-End Demo Target

The first demo worth showing externally should be exactly this:

- [ ] Start MCP server from a desktop client.
- [ ] Ask for a small SF drone.
- [ ] Generate a part-aware hard-surface model.
- [ ] Apply white, black, and blue emissive materials.
- [ ] Auto-place camera and showroom lighting.
- [ ] Render preview.
- [ ] Ask for one local revision such as thicker landing gear.
- [ ] Re-render preview.
- [ ] Generate QA report.
- [ ] Save project.
- [ ] Export GLB.

## Maintenance Rules for This TODO

- [ ] Update this file when a feature is split, descoped, or renamed.
- [ ] Do not mark a phase complete while its exit gate remains unmet.
- [ ] If a task is blocked by a design conflict, add the blocker directly under the task instead of hiding it elsewhere.
- [ ] If a feature moves out of MVP, move it to the explicit backlog section rather than leaving it ambiguous.