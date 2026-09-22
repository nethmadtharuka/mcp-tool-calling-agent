"""GitHub MCP client: discovers tools from the official GitHub MCP server.

Unlike app/agent/tools.py (a plain Python function), these tool
definitions are NOT written by us - they're fetched at runtime from a
separate process (the GitHub MCP server) that we launch over stdio.
"""

import logging

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.core.config import Settings

logger = logging.getLogger(__name__)

# ponytail: process-lifetime cache, no invalidation. Avoids spawning a new
# github-mcp-server subprocess on every agent_node/tool_node call within a
# single request. Restart the app if GITHUB_TOOLSETS changes.
_tools_cache: list | None = None


def _github_server_config(settings: Settings) -> dict:
    return {
        "github": {
            "transport": "stdio",
            "command": "docker",
            # --read-only is hardcoded here, not read from an env var, so
            # it can never be accidentally disabled by config.
            "args": [
                "run",
                "-i",
                "--rm",
                "-e",
                "GITHUB_PERSONAL_ACCESS_TOKEN",
                "-e",
                "GITHUB_TOOLSETS",
                "ghcr.io/github/github-mcp-server",
                "stdio",
                "--read-only",
            ],
            "env": {
                "GITHUB_PERSONAL_ACCESS_TOKEN": settings.github_pat,
                "GITHUB_TOOLSETS": settings.github_toolsets,
            },
        }
    }


async def get_mcp_tools(settings: Settings) -> list:
    """Return the GitHub MCP tools, or [] if GitHub MCP isn't configured.

    This starts (or connects to) the github-mcp-server subprocess and
    asks it for its tool schemas - the MCP equivalent of the @tool
    decorator in tools.py, except the schema comes from GitHub, not us.
    """
    global _tools_cache

    if not settings.github_mcp_enabled:
        logger.info("GitHub MCP disabled: GITHUB_PERSONAL_ACCESS_TOKEN not set")
        return []

    if _tools_cache is None:
        client = MultiServerMCPClient(_github_server_config(settings))
        _tools_cache = await client.get_tools()
        logger.info(
            "Discovered %d GitHub MCP tool(s): %s",
            len(_tools_cache),
            [t.name for t in _tools_cache],
        )

    return _tools_cache
