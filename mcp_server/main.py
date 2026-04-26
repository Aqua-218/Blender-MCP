from __future__ import annotations

import argparse
import asyncio

from mcp_server.config import ServerSettings
from mcp_server.server import MCPServerApplication


def main() -> None:
    parser = argparse.ArgumentParser(description="Blender MCP server entrypoint")
    parser.add_argument("--transport", choices=["stdio", "http"], default=None)
    args = parser.parse_args()
    try:
        settings = ServerSettings.from_env()
        if args.transport is not None:
            settings = ServerSettings.model_validate(
                {
                    **settings.model_dump(),
                    "transport": args.transport,
                }
            )
    except ValueError as exc:
        parser.error(str(exc))
    application = MCPServerApplication(settings)
    if settings.transport == "http":
        application.serve_http()
    else:
        asyncio.run(application.serve_stdio())


if __name__ == "__main__":
    main()

