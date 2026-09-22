import pytest


@pytest.fixture(autouse=True)
def disable_github_mcp(monkeypatch):
    """Force GitHub MCP off for every test, regardless of what's in the
    developer's local .env.

    app/agent/mcp_tools.py treats an empty GITHUB_PERSONAL_ACCESS_TOKEN as
    "GitHub MCP not configured" and returns [] without touching Docker or
    the network (see Settings.github_mcp_enabled). Without this, a real
    token sitting in .env would make normal `pytest` runs try to spawn
    the real github-mcp-server container.
    """
    monkeypatch.setenv("GITHUB_PERSONAL_ACCESS_TOKEN", "")
