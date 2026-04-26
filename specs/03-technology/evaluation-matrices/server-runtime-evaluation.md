# Evaluation Matrix: MCP Server Runtime

## Candidates

- Python 3.12 + official MCP Python SDK
- TypeScript + MCP TypeScript SDK
- Go + custom or lower-level MCP implementation

## Weighted Criteria

| Criterion | Weight |
| --- | ---: |
| Blender integration fit | 30 |
| MCP ecosystem fit | 20 |
| Structured schema ergonomics | 15 |
| Operational simplicity | 15 |
| Local workstation distribution | 10 |
| Performance headroom | 10 |

## Scores

| Candidate | Blender Fit | MCP Fit | Schema Ergonomics | Ops Simplicity | Distribution | Performance | Weighted Total |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Python + MCP Python SDK | 10 | 10 | 9 | 8 | 8 | 7 | 8.95 |
| TypeScript + MCP TS SDK | 5 | 9 | 8 | 8 | 8 | 8 | 7.25 |
| Go + custom stack | 4 | 5 | 6 | 7 | 8 | 9 | 5.90 |

## Recommendation

Select Python 3.12 with the official MCP Python SDK.

## Evidence

- The official MCP Python SDK is actively maintained, supports FastMCP, structured output, stdio, Streamable HTTP, progress, lifespan, and authentication patterns.
- The repository shows strong activity, broad contributor participation, and recent releases.
- Blender’s primary automation surface is Python.

## Rejected Options

- TypeScript is strong for generic MCP work but introduces a language boundary against Blender’s Python-centric runtime.
- Go is attractive for performance but offers lower ecosystem leverage for Blender automation and would force a larger custom surface.