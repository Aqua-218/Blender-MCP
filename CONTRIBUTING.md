# Contributing to Blender MCP

## Welcome

Thank you for contributing to Blender MCP.

This repository focuses on safe, structured Blender automation over MCP. Good contributions improve reliability, clarity of tool contracts, packaging quality, documentation, and contributor experience just as much as they add new runtime capabilities.

## Code of Conduct

Participation in this project is governed by [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).

## How Can I Contribute?

### Reporting Bugs

Use the GitHub bug report form and include:

- the Blender MCP version or commit you tested
- whether you used `mock`, `blender`, or `auto` controller mode
- whether the client transport was `stdio` or `http`
- the exact steps to reproduce the issue
- expected behavior, actual behavior, and any relevant logs

Security issues must not be reported in public issues. Follow [SECURITY.md](SECURITY.md) instead.

### Suggesting Features

Use the feature request form for new tool families, transport changes, client integration improvements, packaging changes, or documentation gaps.

When proposing a new capability, explain the user workflow, the safety constraints, and the expected request and result shape.

### Your First Contribution

Good first contributions include:

- documentation improvements in the root docs or `specs/`
- schema and type clarification
- additional regression coverage for an existing tool family
- example configuration polish
- contributor tooling and packaging improvements

## Pull Request Process

1. Fork the repository and create a topic branch from `main`.
2. Use a branch name such as `feat/<description>`, `fix/<description>`, `docs/<description>`, or `chore/<description>`.
3. Make focused changes with tests and documentation updates where appropriate.
4. Run the relevant local checks before pushing.
5. Write Conventional Commit subjects for your commits.
6. Open a pull request using the provided template.
7. Address review feedback with follow-up commits or a rebase as appropriate.
8. Maintainers will merge once checks and review expectations are met.

## Development Setup

### Prerequisites

- Python 3.12
- `make`
- Git
- Optional Blender 5.x for Blender-backed validation

### Clone And Install

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[dev]"
pre-commit install --install-hooks --hook-type pre-commit --hook-type commit-msg --hook-type pre-push
```

### Common Commands

```bash
make lint
make typecheck
make schema-check
make test
make test-integration
make test-phase0
make package-check
```

### Blender-Backed Validation

If Blender is installed locally, run:

```bash
BLENDER_MCP_BLENDER_BINARY=/path/to/blender make test-blender-smoke
```

## Style Guide

- Follow the repository's Ruff and mypy configuration.
- Keep JSON schemas and typed models in sync.
- Avoid adding any tool path that enables arbitrary shell execution.
- Keep file access inside allowlisted workspace roots.
- Preserve safety gates around destructive operations and snapshot creation.
- Use clear commit scopes that match the affected subsystem.

## Commit Message Format

This repository uses Conventional Commits.

Examples:

- `feat(scene): add layered scene composition helpers`
- `fix(workspace): reject paths outside allowlisted roots`
- `docs(readme): clarify desktop client setup`

The repository ships a commit-msg hook that validates commit subjects locally.

## Project Structure

- `mcp_server/`: MCP server, policy, persistence, schemas, and tool implementations
- `blender_controller/`: controller host, protocol, runtime implementations, and bootstrap logic
- `generated_schemas/`: code-generated public JSON schemas
- `specs/`: requirements, architecture, API, security, testing, and operations documentation
- `tests/`: unit, integration, contract, HTTP security, and packaging smoke coverage

## Community And Support

- Use issues for reproducible defects and scoped feature requests.
- Use pull requests for concrete changes.
- For security-sensitive reports, use the private process in [SECURITY.md](SECURITY.md).

Maintainers aim to acknowledge well-formed contributions within a few business days.