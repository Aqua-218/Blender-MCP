# Runbook: Blender Controller Disconnected

## Symptoms

- Tool calls fail with `controller_unavailable`
- Heartbeat loss from the controller bridge
- Blender process not responding

## Steps

1. Confirm whether Blender is still running.
2. If Blender is hung, terminate the Blender process only.
3. Restart the controller and reattach to the latest project if safe.
4. Verify the bridge secret rotated.
5. Re-run a read-only health check such as project info or object list.

## Recovery Validation

- Project opens successfully
- Recent snapshot is present
- One read-only tool succeeds