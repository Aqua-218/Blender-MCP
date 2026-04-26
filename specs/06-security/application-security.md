# Application Security

## Controls

- Strict typed schema validation for all tool inputs
- Directory and extension allowlists for import/export/file operations
- No tool that executes arbitrary code, Python, or shell fragments from request text
- Normalized result envelopes for error handling and auditability
- Safe-mode defaults for resource-heavy tools

## Input Handling

- Free-form instruction text is advisory; execution only occurs through typed tool parameters and policy-approved operations.
- Controller commands are generated from validated data, not from direct script interpolation.

## Logging Rules

- Log request correlation IDs, not full sensitive payloads where unnecessary.
- Record failure context sufficient for debugging without leaking secrets.