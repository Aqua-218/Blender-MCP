from __future__ import annotations

import asyncio

from mcp_server.bridge import ControllerBridgeClient
from mcp_server.config import ServerSettings


async def _run() -> None:
    settings = ServerSettings.from_env()
    bridge = ControllerBridgeClient(settings)
    try:
        await bridge.start()
        runtime = await bridge.get_runtime_info()
        print(f"controller backend={runtime['backend']} host={settings.controller_host} port={settings.controller_port}")
    finally:
        await bridge.stop()


def main() -> None:
    asyncio.run(_run())


if __name__ == "__main__":
    main()
