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
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    api_key = os.getenv("LLM_API_KEY")
    github_pat = os.getenv("GITHUB_PERSONAL_ACCESS_TOKEN")
    github_toolsets = os.getenv("GITHUB_TOOLSETS", "repos,issues,pull_requests")

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
    )
