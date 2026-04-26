# Third-Party Licenses

This file summarizes the direct third-party dependencies used by Blender MCP at the time of the Apache-2.0 OSS release preparation on 2026-04-26.

It is informational only and does not replace the original license terms distributed by each dependency.

## Runtime Dependencies

| Package | Version | License |
| --- | --- | --- |
| `mcp` | `1.27.0` | MIT |
| `pydantic` | `2.13.3` | MIT |
| `sqlalchemy` | `2.0.49` | MIT |
| `alembic` | `1.18.4` | MIT |
| `typing-extensions` | `4.15.0` | PSF-2.0 |
| `orjson` | `3.11.8` | MPL-2.0 AND (Apache-2.0 OR MIT) |

## Development Dependencies

| Package | Version | License |
| --- | --- | --- |
| `build` | `1.4.4` | MIT |
| `pytest` | `9.0.3` | MIT |
| `pytest-asyncio` | `1.3.0` | Apache-2.0 |
| `ruff` | `0.15.11` | MIT |
| `mypy` | `1.20.2` | MIT |
| `pre-commit` | `4.6.0` | MIT |

## Notes

- The dependency versions listed above were read from the project's local virtual environment.
- Permissive licenses identified here are compatible with Apache-2.0 for this repository.
- Release maintainers should revalidate dependency versions and license metadata before each public release.