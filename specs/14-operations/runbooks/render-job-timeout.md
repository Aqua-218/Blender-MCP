# Runbook: Render Job Timeout

## Symptoms

- Final or standard render exceeds configured timeout
- Client receives timeout or cancellation error

## Steps

1. Check whether the render is still progressing.
2. If progress is stalled, cancel the render job.
3. Reduce resolution, samples, or camera batch size.
4. Retry with preview or standard preset.
5. If repeated, investigate scene complexity and render engine settings.

## Escalation Rule

- If three consecutive renders of the same project exceed timeout under reasonable settings, create a performance investigation ticket.