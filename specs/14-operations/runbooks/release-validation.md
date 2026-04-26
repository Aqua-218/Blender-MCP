# Release Validation Runbook

## Purpose

Use this runbook before cutting a release, publishing a package, or updating a desktop MCP client configuration that points at this repository.

The goal is to prove four things:

- the Python environment is bootstrapped correctly
- schemas, lint, and the full automated regression suite are green
- the managed controller can launch a real Blender runtime
- a stdio client configuration can launch the server with the expected workspace and controller settings

## Preconditions

- Python 3.12 environment available
- development dependencies installed with `python -m pip install -e ".[dev]"`
- Blender binary installed locally or exported through `BLENDER_MCP_BLENDER_BINARY`
- allowlisted workspace root available at `workspace/` or overridden through `BLENDER_MCP_WORKSPACE_ROOTS`

## Required Validation Steps

1. Run `make schema-check`.
2. Run `make lint`.
3. Run `make typecheck`.
4. Run `make test`.
5. Run `make test-blender-smoke`.
6. Run `make package-check`.

Do not cut a release if any step above fails.

## Expected Outcomes

- schema drift check passes
- full repository test suite passes
- Blender-backed smoke test reports a passing runtime-info validation
- built wheel and sdist each pass archive-hygiene checks, install into separate isolated environments, and can initialize/start in mock mode without the repository checkout as cwd
- no caller-supplied role bypasses are accepted on unauthenticated transports

## Desktop Client Smoke

For a final operator-facing check, launch a desktop MCP client over stdio with the server configuration from [README.md](../../../README.md).

Minimum environment:

- `BLENDER_MCP_WORKSPACE_ROOTS=/absolute/path/to/blender-mcp/workspace`
- `BLENDER_MCP_CONTROLLER_MODE=mock` for deterministic smoke validation

When validating a real runtime path, switch to:

- `BLENDER_MCP_CONTROLLER_MODE=blender`
- `BLENDER_MCP_BLENDER_BINARY=/absolute/path/to/blender`

Then verify that the client can:

- enumerate tools successfully
- call `ping_bridge`
- call `get_runtime_info`

Use the ready-to-edit templates in:

- [examples/claude-desktop.mock.json](../../../examples/claude-desktop.mock.json)
- [examples/claude-desktop.blender.json](../../../examples/claude-desktop.blender.json)

## CI Expectations

The repository CI workflow defines two lanes:

- `validate`: lint, typecheck, full test suite, schema drift, package build, isolated wheel-and-sdist install startup smoke
- `blender-smoke`: Blender installation plus `make test-blender-smoke`

If the Blender lane fails in CI but local mock-runtime regression is green, treat the issue as a release blocker until the real-runtime path is understood.