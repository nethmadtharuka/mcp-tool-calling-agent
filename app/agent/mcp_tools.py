"""MCP clients: discovers tools from the official GitHub and Filesystem
MCP servers.

Unlike app/agent/tools.py (a plain Python function), these tool
definitions are NOT written by us - they're fetched at runtime from
separate processes (the MCP servers) that we launch over stdio.
"""

import asyncio
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

# Covers starting the Docker container and the MCP handshake. Generous
# because the first run may need to pull the image.
_DISCOVERY_TIMEOUT_SECONDS = 60

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


# Never visible inside the filesystem MCP container (compared lowercase).
_HIDDEN_FROM_FILESYSTEM_MCP = frozenset({".env"})


def _filesystem_server_config(settings: Settings) -> dict:
    mount_dst = "/projects/mcp-tool-calling-agent"
    # Each top-level entry is bind-mounted on its own, skipping .env, so
    # the secrets file simply doesn't exist in the container. Mounting the
    # whole root and overlaying an empty file on .env is NOT enough: on a
    # Windows host .ENV/.Env still resolve to the real file through the
    # case-insensitive bind mount.
    # ponytail: entries are listed when the config is built; a top-level
    # file added later is visible only after an app restart.
    mounts = []
    for entry in sorted(_PROJECT_ROOT.iterdir()):
        if entry.name.lower() in _HIDDEN_FROM_FILESYSTEM_MCP:
            continue
        # ,ro is hardcoded here, not read from an env var, so this
        # project's files can never be accidentally mounted writable by
        # misconfiguring .env.
        mounts += ["--mount", f"type=bind,src={entry},dst={mount_dst}/{entry.name},ro"]
    return {
        "filesystem": {
            "transport": "stdio",
            "command": "docker",
            "args": ["run", "-i", "--rm", *mounts, "mcp/filesystem", mount_dst],
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
    all_ok = True

    # Each server is optional: if one is down (Docker not running, image
    # missing, handshake fails), log it and carry on with the others.
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
    # (fast when Docker is simply down). Add a backoff if that gets noisy.
    if all_ok:
        _tools_cache = tools
    return tools
