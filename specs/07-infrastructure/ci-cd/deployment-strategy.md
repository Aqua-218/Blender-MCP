# Deployment Strategy

## MVP Release Model

- Deliver as a versioned Python project installable with uv or pip.
- Support local stdio launch configuration for MCP clients.
- Keep Blender controller and MCP server versions aligned in the same release train.

## Rollout Strategy

- Development builds for internal testing
- Release candidates for staged user validation
- Stable releases after Blender compatibility smoke tests and regression tests pass

## Rollback Strategy

- Reinstall previous package version
- Restore previous metadata backup if migrations were applied
- Restore latest known-good project snapshot if user content was affected