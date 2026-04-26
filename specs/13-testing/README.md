# Testing Strategy Overview

## Goal

Prove that the MCP server, Blender controller, and workspace safety model behave correctly across local iterative editing workflows.

## Test Layers

- Unit tests for schemas, validation, policy, and metadata persistence
- Integration tests for server-to-controller execution
- End-to-end tests for representative creative workflows
- Load tests for long-running and queue-heavy scenarios
- Security tests for path, permission, and policy enforcement

## Required Documents

- [test-pyramid.md](test-pyramid.md)
- [integration-testing.md](integration-testing.md)
- [e2e-testing.md](e2e-testing.md)
- [load-testing.md](load-testing.md)
- [security-testing.md](security-testing.md)