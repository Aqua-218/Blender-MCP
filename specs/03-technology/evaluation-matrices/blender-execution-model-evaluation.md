# Evaluation Matrix: Blender Execution Model

## Candidates

- Persistent Blender runtime with local controller bridge
- Spawn background-mode Blender per request
- Use Blender as a Python module inside the MCP server process

## Weighted Criteria

| Criterion | Weight |
| --- | ---: |
| Interactive iteration fit | 30 |
| Portability | 20 |
| Latency | 20 |
| Failure isolation | 15 |
| Operational complexity | 15 |

## Scores

| Candidate | Iteration Fit | Portability | Latency | Failure Isolation | Ops Complexity | Weighted Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Persistent runtime + bridge | 10 | 8 | 9 | 8 | 6 | 8.50 |
| Spawn Blender per request | 3 | 9 | 2 | 9 | 8 | 5.70 |
| Blender as Python module | 7 | 5 | 8 | 4 | 7 | 6.25 |

## Recommendation

Select a persistent Blender runtime with a local controller bridge.

## Evidence

- Blender background mode is first-class for automation, but per-call startup cost is too high for iterative review.
- Blender-as-module is documented and viable, but it is not the default distribution path and still carries single-state constraints.

## Rejected Options

- Per-request spawning is acceptable for batch conversion, not interactive authoring.
- Blender-as-module remains a viable future deployment variant for specialized environments, but not the default architecture.