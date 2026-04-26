# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to Semantic Versioning.

## [Unreleased]

## [0.1.0] - 2026-04-26

### Added

- Initial public release of Blender MCP as a Python 3.12 project for safe Blender workflows over MCP.
- A stdio-first MCP server with optional authenticated local HTTP transport.
- A persistent authenticated Blender controller bridge with Blender-backed and mock runtime modes.
- Typed models, published JSON schemas, metadata persistence, snapshots, QA reports, and workspace safety guards.
- Tool families for project lifecycle, object and geometry authoring, materials, rendering, import and export, semantic parts, scene and world composition, geometry nodes, texture and UV work, repair helpers, and runtime diagnostics.
- Deterministic regression coverage, Blender-backed smoke validation, and package installation smoke checks.
- Apache-2.0 licensing, community health files, contributor guidance, governance, and dependency automation baselines.

### Security

- Allowlisted workspace roots for file operations.
- Shared-secret authentication for the local controller bridge.
- Explicit authenticated versus loopback-only unsafe HTTP modes.
- Redacted logging for sensitive configuration values.
- Snapshot safeguards before destructive operations that exceed configured thresholds.