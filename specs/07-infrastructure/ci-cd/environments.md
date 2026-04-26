# Environments

## Local Development

- Fast iteration environment for tool and controller development
- Uses stdio and local Blender runtime

## CI Validation

- Runs non-interactive tests
- Executes Blender smoke tests in background or container-compatible automation mode when available

## Staging

- Optional internal environment for pre-release validation
- Uses a dedicated workspace root and test artifacts

## Production Local

- End-user workstation deployment
- Uses stdio by default

## Hosted Pilot

- Optional Streamable HTTP deployment with authentication and isolated Blender workers