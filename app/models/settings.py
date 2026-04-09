from __future__ import annotations
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    github_token: str = Field(default="", alias="GITHUB_TOKEN")

    # AI provider keys
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    runpod_gemma_2_api_key: str = Field(default="", alias="RUNPOD_GEMMA_2_API_KEY")

    model_config = SettingsConfigDict(
        env_file=Path(__file__).parent.parent.parent / ".env",
        env_file_encoding="utf-8",
        populate_by_name=True,
    )

    @property
    def has_github_token(self) -> bool:
        return bool(self.github_token)

    @property
    def has_anthropic_key(self) -> bool:
        return bool(self.anthropic_api_key)

    def get_key_for_env_var(self, env_key: str) -> str:
        """Return the token for a given env var name, or empty string."""
        mapping = {
            "ANTHROPIC_API_KEY":      self.anthropic_api_key,
            "RUNPOD_GEMMA_2_API_KEY": self.runpod_gemma_2_api_key,
        }
        return mapping.get(env_key, "")


# Single shared instance
settings = AppSettings()
