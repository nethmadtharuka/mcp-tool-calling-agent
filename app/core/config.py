"""Application configuration, loaded from environment variables."""

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


class ConfigError(Exception):
    """Raised when required configuration is missing or invalid."""


@dataclass(frozen=True)
class Settings:
    llm_provider: str
    llm_model: str
    llm_api_key: str | None
    github_pat: str | None
    github_toolsets: str
    filesystem_mcp_enabled: bool
    # Defaults are the docker-compose service names. Read from env only,
    # never from anything the LLM produces.
    github_mcp_url: str = "http://github-mcp:8082/"
    filesystem_mcp_url: str = "http://filesystem-mcp:8000/mcp"

    @property
    def mock_mode(self) -> bool:
        return self.llm_provider == "mock"

    @property
    def github_mcp_enabled(self) -> bool:
        # GitHub MCP is optional: without a token we just run with the
        # Phase 2 local tool, so the app and its tests still work with
        # no Docker and no GitHub account configured.
        return bool(self.github_pat)


def get_settings() -> Settings:
    """Read settings from the environment, failing clearly if misconfigured."""
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    default_model = "gemini-flash-lite-latest" if provider == "gemini" else "gpt-4o-mini"
    model = os.getenv("LLM_MODEL", default_model)
    api_key = os.getenv("LLM_API_KEY")
    github_pat = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    github_toolsets = os.getenv("GITHUB_TOOLSETS", "repos,issues,pull_requests")
    # Off by default: unlike GitHub MCP (gated by needing a PAT), the
    # filesystem server needs no secret, so it needs an explicit opt-in to
    # avoid every `pytest`/dev run silently trying to reach it.
    # docker-compose.yml sets it to true for the agent container.
    filesystem_mcp_enabled = os.getenv("FILESYSTEM_MCP_ENABLED", "false").lower() == "true"

    if provider != "mock" and not api_key:
        raise ConfigError(
            f"LLM_API_KEY is required when LLM_PROVIDER='{provider}'. "
            "Set it in your .env file, or set LLM_PROVIDER=mock to run "
            "without a real LLM for local development."
        )

    return Settings(
        llm_provider=provider,
        llm_model=model,
        llm_api_key=api_key,
        github_pat=github_pat,
        github_toolsets=github_toolsets,
        filesystem_mcp_enabled=filesystem_mcp_enabled,
        github_mcp_url=os.getenv("GITHUB_MCP_URL", Settings.github_mcp_url),
        filesystem_mcp_url=os.getenv("FILESYSTEM_MCP_URL", Settings.filesystem_mcp_url),
    )
