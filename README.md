# Blender MCP

Blender MCP is an Apache-2.0 Python project that exposes safe, structured Blender workflows over the Model Context Protocol (MCP). It pairs an MCP server with a local authenticated Blender controller bridge so desktop clients and agents can create, inspect, revise, render, and export 3D work without arbitrary shell access.

## Overview

Blender MCP is designed for iterative creative workflows where a user reviews output while an MCP client drives Blender through typed, policy-checked tool calls.

Highlights:

- stdio-first MCP server with optional HTTP transport for local or remote MCP clients
- persistent Blender controller bridge for stateful modeling sessions
- deterministic mock runtime for CI and local development without Blender
- typed models and published JSON schemas for requests, results, and domain artifacts
- workspace allowlists, policy gates, snapshots, history, and QA reporting

Implemented tool families include project lifecycle, object and geometry authoring, transforms and alignment, selection sets, materials and material-node helpers, rendering, import and export, semantic parts, repair helpers, model generation, scene and world composition, production pipeline planning, execution-oriented AAA orchestration, 520 generated AAA workflow recipes, geometry nodes, texture and UV operations, QA inspection, and runtime diagnostics.

## Project Status

Blender MCP is currently alpha software. The repository is ready for local evaluation, client integration work, and community contributions, but public tool contracts and release automation may continue to evolve before a stable `1.0.0` release.

## Quick Start

### Prerequisites

- Python 3.12
- Optional Blender 5.x for real runtime validation
- A writable workspace directory for projects, renders, exports, logs, and snapshots

### Install From Source

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
cp .env.example .env
make schema-check
make lint
make test
```

### Start The Server

```bash
blender-mcp-server --transport stdio
```

### Configure A Desktop Client

Ready-to-edit examples are available in [examples/README.md](examples/README.md), [examples/claude-desktop.mock.json](examples/claude-desktop.mock.json), and [examples/claude-desktop.blender.json](examples/claude-desktop.blender.json).

For a deterministic local setup, use the mock runtime. For a Blender-backed setup, set `BLENDER_MCP_CONTROLLER_MODE=blender` and point `BLENDER_MCP_BLENDER_BINARY` at an installed Blender executable.

## Installation Options

### Source Checkout

This is the recommended setup for contributors and local evaluators:

```bash
python -m pip install -e ".[dev]"
```

### Built Artifacts

You can also build and install local artifacts:

```bash
python -m build
python -m pip install dist/blender_mcp-0.1.0-py3-none-any.whl
```

Use `make package-check` to verify that the wheel and sdist install cleanly in isolated environments and include the required release metadata.

The built artifacts also ship the generated public schemas under `generated_schemas/`.

## Usage

Blender MCP supports two runtime modes:

- `mock`: deterministic runtime for tests and local validation
- `blender`: managed or attached Blender runtime backed by the Blender Python API

Useful commands:

- `make run-stdio` to launch the stdio server
- `make run-http-unsafe` to launch an explicit unauthenticated loopback debug HTTP server
- `make run-http-remote-unsafe` to launch an explicit unauthenticated remote HTTP server on `0.0.0.0`
- `make test` to run the default regression suite
- `make test-blender-smoke` to validate a real Blender-backed launch path
- `make schema-export` to regenerate published schemas
- `make schema-check` to verify schema drift

## Safety Model

Blender MCP is intentionally conservative:

- no arbitrary shell execution is exposed through tool calls
- file access is restricted to allowlisted workspace roots
- destructive actions can trigger pre-mutation snapshots based on configured thresholds
- HTTP mode requires explicit opt-in and authentication unless unauthenticated mode is explicitly enabled
- controller traffic is authenticated with a shared secret and redacted in logs

## Configuration

The server reads environment variables prefixed with `BLENDER_MCP_`.

Important variables include:

- `BLENDER_MCP_WORKSPACE_ROOTS`: comma-separated allowlisted workspace roots
- `BLENDER_MCP_CONTROLLER_MODE`: `mock`, `blender`, or `auto`
- `BLENDER_MCP_BLENDER_BINARY`: Blender executable path for real runtime launch
- `BLENDER_MCP_TRANSPORT`: `stdio` or `http`
- `BLENDER_MCP_HTTP_HOST`: HTTP bind host, for example `127.0.0.1` or `0.0.0.0`
- `BLENDER_MCP_HTTP_PORT`: HTTP bind port
- `BLENDER_MCP_HTTP_AUTH_TOKEN`: bearer token for authenticated HTTP mode
- `BLENDER_MCP_ENABLE_UNAUTHENTICATED_HTTP`: set `true` to allow HTTP without bearer authentication
- `BLENDER_MCP_CONTROLLER_SECRET`: shared secret for the controller bridge
- `BLENDER_MCP_MAX_SAFE_MODE_POLYGON_BUDGET`: request budget guard for safe mode

See [.env.example](.env.example) for the full configuration surface.

## Documentation

- [specs/README.md](specs/README.md): detailed requirements, architecture, security, operations, and testing docs
- [specs/14-operations/runbooks/release-validation.md](specs/14-operations/runbooks/release-validation.md): release validation checklist
- [generated_schemas](generated_schemas): code-generated public schemas

## Contributing

Contributions are welcome. Start with [CONTRIBUTING.md](CONTRIBUTING.md), review the [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md), and check the active priorities in [ROADMAP.md](ROADMAP.md).

## Security

Please do not report vulnerabilities in public issues. Review [SECURITY.md](SECURITY.md) for the supported versions, reporting process, and disclosure expectations.

## License

Blender MCP is licensed under the Apache License 2.0. See [LICENSE](LICENSE) and [NOTICE](NOTICE) for the full terms and attribution notice.
