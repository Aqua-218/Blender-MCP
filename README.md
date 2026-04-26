# Blender MCP

Blender MCP is a Python 3.12 project that implements a safe MCP server, a local authenticated Blender controller bridge, structured metadata persistence, and deterministic tests for end-to-end creative workflows.

## Current Scope

This repository now covers the foundation workstreams plus the major advanced capability families that were originally staged after the MVP. Implemented areas include:

- project lifecycle, workspace safety, persistence, and policy enforcement
- object, geometry, material, lighting, camera, and render workflows
- asset import/export, export profiles, and export-readiness gates
- QA inspection, history, snapshots, diff summaries, and comparison renders
- modifiers, repair helpers, semantic parts, and localized model revisions
- model generation, scene composition, world generation, and geometry nodes helpers
- texture and UV workflows plus experimental animation and rigging helpers
- system diagnostics, runtime info, safe config inspection, and in-memory server metrics

Current regression status: the full repository test suite passes in this repository.

The project supports two runtime modes:

- Blender-backed runtime when a Blender binary is configured
- Mock controller runtime for deterministic automated tests when Blender is unavailable

The mock runtime is a test harness, not a replacement for the real bridge design. The server, policy layer, transport layer, and controller protocol remain the same in both modes.

## Quickstart

1. Create a Python 3.12 environment.
2. Install the package and developer dependencies.
3. Copy .env.example to .env if you want local overrides.
4. Run schema checks, lint, and tests.

Example:

```bash
python3 -m pip install -e ".[dev]"
make schema-check
make lint
make test
```

## Desktop Client Stdio Configuration

Any MCP client that launches servers over stdio can start this server directly from the repository virtual environment.

Example configuration:

```json
{
	"mcpServers": {
		"blender-mcp": {
			"command": "/absolute/path/to/blender-mcp/.venv/bin/python",
			"args": ["-m", "mcp_server.main", "--transport", "stdio"],
			"env": {
				"BLENDER_MCP_WORKSPACE_ROOTS": "/absolute/path/to/blender-mcp/workspace",
				"BLENDER_MCP_CONTROLLER_MODE": "mock"
			}
		}
	}
}
```

For a Blender-backed runtime, switch `BLENDER_MCP_CONTROLLER_MODE` to `blender` and set `BLENDER_MCP_BLENDER_BINARY` to the Blender executable path.

Ready-to-edit example files are available in:

- [examples/claude-desktop.mock.json](examples/claude-desktop.mock.json)
- [examples/claude-desktop.blender.json](examples/claude-desktop.blender.json)
- [examples/README.md](examples/README.md)

## Developer Commands

- Run stdio server: `make run-stdio`
- Run opt-in local HTTP debug server only: `make run-http-unsafe`
- Run default regression tests: `make test`
- Run integration tests only: `make test-integration`
- Run load and soak checks: `make test-load`
- Run the automated phase-0 MCP acceptance flow: `make test-phase0`
- Run Blender-backed bridge smoke validation: `make test-blender-smoke`
- Build wheel and sdist artifacts, verify archive hygiene, then install each artifact into a separate isolated environment and verify mock-mode startup without the repository checkout as cwd: `make package-check`
- Export generated schemas: `make schema-export`
- Check schema drift: `make schema-check`
- Run controller smoke tests: `make controller-smoke`

## Blender-Backed Validation

Use `make test-blender-smoke` to verify that the managed controller can launch a real Blender runtime and report runtime information.

The target uses `BLENDER_MCP_BLENDER_BINARY` when it is set, then falls back to `blender` on `PATH`, then `/Applications/Blender.app/Contents/MacOS/Blender` on macOS.

The current repository state has been validated locally against Blender 5.1.1 on macOS. When Blender is available, the full repository test run includes the Blender-backed bridge smoke test in addition to the mock-runtime regression suite.

The repository CI workflow also includes a dedicated Blender-backed smoke lane. For the full release checklist and client-facing validation sequence, see [specs/14-operations/runbooks/release-validation.md](specs/14-operations/runbooks/release-validation.md).

## Package Validation

Use `make package-check` to build both the sdist and wheel into `dist/`, verify that neither archive contains stale validation artifacts, install each artifact into its own isolated environment, and verify that the server can initialize and start in mock mode without relying on the repository checkout as the working directory.

## Environment

The server reads configuration from environment variables prefixed with `BLENDER_MCP_`.

Important variables:

- `BLENDER_MCP_REPO_ROOT`: optional override for source-checkout asset resolution and controller bootstrap without depending on the current working directory
- `BLENDER_MCP_WORKSPACE_ROOTS`: comma-separated allowlisted workspace roots
- `BLENDER_MCP_CONTROLLER_MODE`: `mock`, `blender`, or `auto`
- `BLENDER_MCP_BLENDER_BINARY`: path to Blender for real runtime launch
- `BLENDER_MCP_CONTROLLER_SECRET`: shared secret for authenticated bridge requests; set `BLENDER_MCP_CONTROLLER_ATTACH_TIMEOUT_SECONDS` when you want the server to wait for an already-running controller before spawning its own
- `BLENDER_MCP_CONTROLLER_ATTACH_TIMEOUT_SECONDS`: optional attach wait window before managed startup; keep this at `0` for normal managed cold starts
- `BLENDER_MCP_TRANSPORT`: `stdio` by default; `http` is disabled unless `BLENDER_MCP_ENABLE_UNAUTHENTICATED_HTTP=true` is set for loopback-only local inspection
- `BLENDER_MCP_HTTP_AUTH_TOKEN`: bearer token required for authenticated HTTP mode; leave unset only for explicit loopback-only unsafe debug mode
- `BLENDER_MCP_HTTP_AUTH_ROLE`: server-assigned role for authenticated HTTP requests
- `BLENDER_MCP_HTTP_MAX_REQUEST_BYTES`: maximum accepted HTTP request body size
- `BLENDER_MCP_DEFAULT_ROLE`: server-assigned fallback role for unauthenticated transports; clients must not send their own role
- `BLENDER_MCP_MAX_SAFE_MODE_POLYGON_BUDGET`: reject oversized generation requests before mutation when safe mode is enabled

## Transport Support

The recommended client transport remains stdio. Streamable HTTP is now supported in two explicit modes: authenticated HTTP using `BLENDER_MCP_HTTP_AUTH_TOKEN`, or loopback-only unsafe local debug mode using `BLENDER_MCP_ENABLE_UNAUTHENTICATED_HTTP=true`. Unsafe mode remains loopback-only. Hosted deployments should terminate TLS in front of the HTTP listener.

## Schema Source Of Truth

The canonical public schemas remain under specs/05-api/schemas. Code-generated schemas are exported into generated_schemas/ and compared against the spec copies during validation.
