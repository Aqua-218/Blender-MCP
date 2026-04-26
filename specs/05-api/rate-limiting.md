# Rate Limiting and Workload Control

## Goal

The local-first product is constrained more by workstation resources than by internet-scale request rates. Therefore, workload control combines concurrency limits, queue depth limits, and per-tool resource budgets.

## Controls

- Maximum concurrent mutating jobs per Blender runtime: 1
- Maximum concurrent read-only inspection jobs per Blender runtime: configurable, default 2 if they do not require scene mutation
- Maximum queued jobs per session: 20
- Maximum queued render jobs per session: 5

## Heavy-Tool Guardrails

- World generation requires explicit budget parameters or safe-mode defaults.
- Final render jobs are queued and may be rejected when the queue is saturated.
- Scatter and subdivision-heavy operations are denied when predicted complexity exceeds policy ceilings.

## Client Feedback

- Rejected work returns `policy_violation` with a budget or concurrency explanation.
- Queued work returns immediate acknowledgment plus progress once started.