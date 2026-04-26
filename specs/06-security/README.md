# Security Overview

## Security Goal

Allow LLM-driven Blender execution without allowing the MCP server to become a general local-agent backdoor.

## Security Principles

- Minimize authority
- Keep Blender execution inside approved workspaces
- Require structured inputs, not free-form code execution
- Gate destructive operations
- Prefer local-only bindings by default
- Preserve audit trails for every significant action

## Documents

- [threat-model.md](threat-model.md)
- [authentication-design.md](authentication-design.md)
- [authorization-design.md](authorization-design.md)
- [data-security.md](data-security.md)
- [application-security.md](application-security.md)
- [infrastructure-security.md](infrastructure-security.md)
- [compliance.md](compliance.md)
- [incident-response.md](incident-response.md)