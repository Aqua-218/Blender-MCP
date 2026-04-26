# Blender AI MCP Specification Suite

## Purpose

This specification suite defines an implementation-facing architecture for a Blender-focused MCP server that allows LLM clients to create, inspect, revise, render, optimize, and export 3D assets through safe and structured tool calls.

The system is intended for an art-director workflow:

- The human user provides intent, review, and corrective feedback.
- The LLM plans and executes work through MCP tools.
- The MCP server validates, routes, logs, and constrains requests.
- A Blender controller performs the actual Blender Python API operations.

## Product Boundary

This specification covers:

- MCP server design and tool contracts
- Blender runtime control architecture
- Project, asset, scene, world, inspection, rendering, and export workflows
- Metadata, history, snapshot, and QA storage
- Safety, observability, performance, and deployment requirements
- MVP scope and phased delivery path to the full capability target

This specification does not cover:

- Training or fine-tuning new generative 3D foundation models
- Full autonomous character production at commercial AAA quality
- Control of non-Blender DCC applications
- Arbitrary workstation automation beyond approved Blender-related operations

## Recommended Architecture Summary

- MCP server runtime: external Python process using the official MCP Python SDK
- Client transport priority: stdio first for desktop clients, optional Streamable HTTP for browser or hosted clients
- Blender control plane: persistent Blender runtime plus a local controller bridge, not one Blender process per tool call
- Metadata store: local SQLite database for projects, operations, snapshots, exports, and QA reports
- Artifact store: workspace-local directories for .blend files, renders, exports, logs, and snapshot payloads
- Safety model: explicit allowlisted directories, typed schemas, resource budgets, destructive-operation confirmation, and timeouts

## Why This Architecture

- Blender exposes its richest automation surface through the Blender Python API.
- MCP clients commonly support stdio, and the MCP specification explicitly recommends stdio support where possible.
- A persistent Blender runtime preserves scene state across iterative review-and-fix loops.
- Blender-as-module is viable for some automation tasks but remains less portable and still inherits single-active-blend restrictions.
- Local SQLite fits application-local metadata with low writer concurrency and a single application server process.

## Document Map

- [ASSUMPTIONS.md](ASSUMPTIONS.md): Explicit assumptions and validation status
- [GLOSSARY.md](GLOSSARY.md): Shared vocabulary
- [01-requirements/README.md](01-requirements/README.md): Product requirements package
- [02-architecture/README.md](02-architecture/README.md): System architecture and ADRs
- [03-technology/README.md](03-technology/README.md): Technology evaluation and selected stack
- [04-database/README.md](04-database/README.md): Metadata and history storage design
- [05-api/README.md](05-api/README.md): MCP tool contract design and schemas
- [06-security/README.md](06-security/README.md): Threat model and safety architecture
- [07-infrastructure/README.md](07-infrastructure/README.md): Runtime, deployment, CI/CD, and observability design
- [13-testing/README.md](13-testing/README.md): Verification strategy
- [14-operations/README.md](14-operations/README.md): Operational runbooks
- [15-project-management/README.md](15-project-management/README.md): Delivery plan, milestones, and risks

## Evidence Base

Primary design decisions in this suite are grounded in the following sources, accessed on 2026-04-24:

- MCP transport specification: https://modelcontextprotocol.io/docs/concepts/transports
- Official MCP Python SDK: https://github.com/modelcontextprotocol/python-sdk
- Blender Python API index: https://docs.blender.org/api/current/
- Blender as a Python module: https://docs.blender.org/api/current/info_advanced_blender_as_bpy.html
- Blender command-line and background execution: https://docs.blender.org/manual/en/latest/advanced/command_line/arguments.html
- Blender glTF 2.0 importer/exporter: https://docs.blender.org/manual/en/latest/addons/import_export/scene_gltf2.html
- Blender FBX exporter: https://docs.blender.org/manual/en/latest/addons/import_export/scene_fbx.html
- Blender asset libraries: https://docs.blender.org/manual/en/latest/files/asset_libraries/introduction.html
- SQLite usage guidance: https://www.sqlite.org/whentouse.html

## Acceptance Target

This specification is complete when an engineering team can implement:

- Phase 0 to MVP without further product clarification
- A stable controller bridge and tool contract layer
- Safe iterative model-authoring flows with preview, QA, snapshot, and export support
- A clear extension path from asset generation to scene and world generation