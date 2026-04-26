from __future__ import annotations

from mcp_server.logging_utils import setup_structured_logger


def get_logger(level: str = "INFO"):
    return setup_structured_logger("mcp_server", level=level)
