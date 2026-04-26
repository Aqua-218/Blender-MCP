# Stakeholder Analysis

## Stakeholder Matrix

| Stakeholder | Goals | Main Risks if Design Fails | Success Criteria |
| --- | --- | --- | --- |
| Human Director User | Direct asset creation through natural language, review previews, request precise local changes, and approve outputs. | Low editability, poor preview quality, unsafe destructive actions, and long iteration loops. | The user can move from concept to approved export using review and correction prompts only. |
| LLM Client | Discover tools reliably, receive structured outputs, operate with low ambiguity, and report progress. | Schema ambiguity, inconsistent outputs, hidden side effects, and poor recovery after partial failure. | Tool discovery, typed inputs, progress notifications, and deterministic output shapes all work consistently. |
| MCP Server Operator | Configure safe workspaces, monitor logs, control budgets, and deploy updates without breaking clients. | Directory escape, uncontrolled compute usage, silent failures, and version drift. | Strong configuration boundaries, auditable logs, reproducible versions, and safe defaults. |
| Blender Runtime Host | Keep Blender stable under repeated automated operations. | Runtime crashes, memory growth, corrupted scenes, or non-recoverable controller disconnects. | Long editing sessions complete without runtime collapse and can recover safely from controller errors. |
| Pipeline Integrator | Connect outputs to web viewers, game engines, or downstream DCC/game pipelines. | Exports that look correct in Blender but fail in target runtimes, missing metadata, and inconsistent axes or units. | Export presets, validation checks, and format-specific warnings reduce downstream integration failures. |
| QA Reviewer | Inspect topology, naming, materials, scale, and export readiness quickly. | Missing inspection data, weak comparability between revisions, and no machine-readable review artifacts. | The system produces structured QA reports, diff summaries, and comparison renders for each iteration. |
| Asset Librarian | Organize reusable assets, worlds, materials, and templates. | Asset duplication, invalid references, and inability to reuse prior outputs safely. | Assets are tagged, cataloged, and searchable within approved library paths. |
| Security Administrator | Prevent arbitrary command execution, path abuse, and unsafe external content loading. | Local file exposure, destructive operations, or abuse of Blender to act outside its intended boundary. | Allowlist-based IO, timeouts, file-type restrictions, and audit logs are enforced by default. |

## Primary User Journey

1. The human provides a natural-language art direction request.
2. The LLM selects MCP tools and creates or opens a project.
3. The system generates an initial model or scene using part-aware structure.
4. The system renders previews and inspection summaries.
5. The human requests local revisions.
6. The LLM revises only the targeted parts or regions.
7. The system re-renders, re-inspects, snapshots, and exports approved outputs.

## Design Implication Summary

- The product is not a general automation host; it is a safe creative execution substrate.
- Edit locality matters as much as initial generation quality.
- Structured metadata is mandatory because local revisions, QA, rollback, and export all depend on it.
- Progress feedback is mandatory because modeling, rendering, and export are long-running operations.