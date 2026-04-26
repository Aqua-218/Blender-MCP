# Threat Model

## Protected Assets

- User workspace files
- Blender project files and snapshots
- Exported deliverables
- QA and history metadata
- Controller bridge session secrets
- HTTP authentication tokens when hosted mode is used

## Trust Boundaries

- Between MCP client and MCP server
- Between MCP server and Blender controller bridge
- Between MCP server and filesystem
- Between HTTP clients and hosted MCP endpoints

## STRIDE Summary

| Threat | Example | Mitigation |
| --- | --- | --- |
| Spoofing | Unauthorized process connects to the controller bridge | Localhost-only binding plus per-session shared secret |
| Tampering | Model attempts to overwrite files outside workspace | Path canonicalization and allowlist enforcement |
| Repudiation | Destructive actions cannot be attributed | Immutable operation logs with request_id and timestamps |
| Information Disclosure | Import/export tools read arbitrary local paths | Allowlisted directories and extension restrictions |
| Denial of Service | Excessive scatter or render requests exhaust workstation | Resource ceilings, queue limits, and timeouts |
| Elevation of Privilege | Read-only session attempts deletion or rollback | Role-based policy and confirmation gates |

## Highest-Risk Abuse Paths

1. Path traversal or arbitrary local file access
2. Unsafe HTTP exposure without origin validation
3. Long-running geometry or render jobs consuming excessive resources
4. High-blast-radius edits without snapshot protection

## Required Mitigations

- Canonicalize and validate every filesystem path before use.
- Never expose arbitrary command execution.
- Bind internal services to localhost unless a hosted topology explicitly requires more.
- Require authentication for non-local HTTP deployments.
- Snapshot before configured destructive actions.