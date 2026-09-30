"""MCP clients: discovers tools from the official GitHub and Filesystem
MCP servers.

Unlike app/agent/tools.py (a plain Python function), these tool
definitions are NOT written by us - they're fetched at runtime from
separate processes (the MCP servers) that we launch over stdio.
"""

import logging
from pathlib import Path

from langchain_mcp_adapters.client import MultiServerMCPClient

from app.core.config import Settings

logger = logging.getLogger(__name__)

# ponytail: process-lifetime cache, no invalidation. Avoids spawning new
# MCP server subprocesses on every agent_node/tool_node call within a
# single request. Restart the app if GITHUB_TOOLSETS/FILESYSTEM_MCP_ENABLED
# changes.
_tools_cache: list | None = None

# app/agent/mcp_tools.py -> app/agent -> app -> repo root. Computed, not
# hardcoded, so the mount always tracks wherever this repo actually lives,
# but it can never point anywhere else.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]

# The filesystem MCP server has no --read-only flag of its own (unlike
# github-mcp-server), so read-only is enforced two ways: the Docker mount
# below uses ,ro (writes physically fail), and this hardcoded allowlist
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


def _filesystem_server_config(settings: Settings) -> dict:
    mount_dst = "/projects/mcp-tool-calling-agent"
    return {
        "filesystem": {
            "transport": "stdio",
            "command": "docker",
            "args": [
                "run",
                "-i",
                "--rm",
                # ,ro is hardcoded here, not read from an env var, so this
                # project's directory can never be accidentally mounted
                # writable by misconfiguring .env.
                "--mount",
                f"type=bind,src={_PROJECT_ROOT},dst={mount_dst},ro",
                "mcp/filesystem",
                mount_dst,
            ],
        }
    }


async def get_mcp_tools(settings: Settings) -> list:
    """Return the enabled MCP tools (GitHub, Filesystem, or both).

    Starts (or connects to) whichever MCP server subprocess(es) are
    enabled and asks each for its tool schemas - the MCP equivalent of
    the @tool decorator in tools.py, except the schemas come from the
    servers, not us.
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

    if "github" in connections:
        tools += await client.get_tools(server_name="github")

    if "filesystem" in connections:
        fs_tools = await client.get_tools(server_name="filesystem")
        tools += [t for t in fs_tools if t.name in _FILESYSTEM_READONLY_TOOLS]

    _tools_cache = tools
    logger.info(
        "Discovered %d MCP tool(s): %s",
        len(_tools_cache),
        [t.name for t in _tools_cache],
    )

    return _tools_cache
