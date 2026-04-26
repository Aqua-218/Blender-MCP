# Incident Response

## Trigger Conditions

- Suspected directory-escape attempt
- Unexpected destructive edit without confirmation
- Controller bridge abuse or unauthorized connection attempt
- Repeated Blender crashes caused by malicious or malformed requests

## Response Steps

1. Stop the MCP server.
2. Preserve metadata and logs.
3. Revoke controller session secrets.
4. Restore the latest safe snapshot if project damage occurred.
5. Review operation history and policy configuration.
6. Patch validation or policy gaps before re-enabling service.

## Post-Incident Requirements

- Record the incident timeline.
- Identify whether the failure was validation, authorization, or controller execution related.
- Add a regression test for the failure mode.