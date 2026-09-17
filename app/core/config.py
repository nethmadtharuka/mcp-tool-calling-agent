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

    @property
    def mock_mode(self) -> bool:
        return self.llm_provider == "mock"


def get_settings() -> Settings:
    """Read settings from the environment, failing clearly if misconfigured."""
    provider = os.getenv("LLM_PROVIDER", "mock").lower()
    model = os.getenv("LLM_MODEL", "gpt-4o-mini")
    api_key = os.getenv("LLM_API_KEY")

    if provider != "mock" and not api_key:
        raise ConfigError(
            f"LLM_API_KEY is required when LLM_PROVIDER='{provider}'. "
            "Set it in your .env file, or set LLM_PROVIDER=mock to run "
            "without a real LLM for local development."
        )

    return Settings(llm_provider=provider, llm_model=model, llm_api_key=api_key)
