"""MCP clients: discovers tools from the official GitHub and Filesystem
MCP servers.

Unlike app/agent/tools.py (a plain Python function), these tool
definitions are NOT written by us - they're fetched at runtime from
separate containers (the MCP servers, see docker-compose.yml) over
streamable HTTP.
"""

import asyncio
import logging

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.core.config import Settings

logger = logging.getLogger(__name__)

# ponytail: process-lifetime cache, no invalidation. Avoids spawning new
# MCP sessions on every agent_node/tool_node call within a single request. Restart the app if GITHUB_TOOLSETS/FILESYSTEM_MCP_ENABLED
# changes.
_tools_cache: list | None = None

# Covers the HTTP connect and the MCP handshake.
_DISCOVERY_TIMEOUT_SECONDS = 60

# The filesystem MCP server has no --read-only flag of its own (unlike
# github-mcp-server), so read-only is enforced two ways: every mount in
# docker-compose.yml is :ro (writes physically fail), and this hardcoded allowlist
# keeps write_file/edit_file/move_file/create_directory off the tool list
# the LLM ever sees, so it can't even request them.
_FILESYSTEM_READONLY_TOOLS = frozenset(
    {
        "read_file",  # older mcp/filesystem:latest image (this is what's pulled)
        "read_text_file",  # newer @modelcontextprotocol/server-filesystem naming
        "read_multiple_files",
        "read_media_file",
        "list_directory",
        "list_directory_with_sizes",
        "directory_tree",
        "search_files",
        "get_file_info",
        "list_allowed_directories",
    }
)


def _github_server_config(settings: Settings) -> dict:
    # --read-only is set on the server itself (docker-compose.yml) and
    # can't be lifted per request; X-MCP-Readonly is a second, client-side
    # ask for the same thing.
    return {
        "github": {
            "transport": "streamable_http",
            "url": settings.github_mcp_url,
            "headers": {
                "Authorization": f"Bearer {settings.github_pat}",
                "X-MCP-Readonly": "true",
                "X-MCP-Toolsets": settings.github_toolsets,
            },
        }
    }


def _filesystem_server_config(settings: Settings) -> dict:
    # Which files the server can see (never .env) and that they're
    # mounted read-only is decided in docker-compose.yml, not here.
    return {"filesystem": {"transport": "streamable_http", "url": settings.filesystem_mcp_url}}


async def get_mcp_tools(settings: Settings) -> list:
    """Return the enabled MCP tools (GitHub, Filesystem, or both).

    Connects to whichever MCP server container(s) are enabled and asks
    each for its tool schemas - the MCP equivalent of the @tool decorator
    in tools.py, except the schemas come from the servers, not us.
    """
    global _tools_cache

    if _tools_cache is not None:
        return _tools_cache

    connections: dict = {}
    if settings.github_mcp_enabled:
        connections.update(_github_server_config(settings))
    else:
        logger.info("GitHub MCP disabled: GITHUB_PERSONAL_ACCESS_TOKEN not set")

    if settings.filesystem_mcp_enabled:
        connections.update(_filesystem_server_config(settings))
    else:
        logger.info("Filesystem MCP disabled: FILESYSTEM_MCP_ENABLED not set to true")

    if not connections:
        return []

    client = MultiServerMCPClient(connections)
    tools = []
    all_ok = True

    # Each server is optional: if one is down (container stopped,
    # unreachable, handshake fails), log it and carry on with the others.
    for server_name in connections:
        try:
            server_tools = await asyncio.wait_for(
                client.get_tools(server_name=server_name), _DISCOVERY_TIMEOUT_SECONDS
            )
        except Exception:
            all_ok = False
            logger.warning(
                "%s MCP server unavailable, continuing without its tools",
                server_name,
                exc_info=True,
            )
            continue
        if server_name == "filesystem":
            server_tools = [t for t in server_tools if t.name in _FILESYSTEM_READONLY_TOOLS]
        tools += server_tools

    logger.info("Discovered %d MCP tool(s): %s", len(tools), [t.name for t in tools])

    # ponytail: a failed server is retried on every agent/tool node call
    # (fast when the container is simply down). Add a backoff if that gets noisy.
    if all_ok:
        _tools_cache = tools
    return tools
