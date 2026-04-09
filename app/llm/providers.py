from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class LLMProvider:
    label: str          # shown in UI combobox
    base_url: str       # OpenAI-compatible endpoint
    env_key: str        # name of the env var that holds the API key
    default_model: str  # default model string for this provider


PROVIDERS: list[LLMProvider] = [
    LLMProvider(
        label="Claude (Anthropic)",
        base_url="https://api.anthropic.com/v1/",
        env_key="ANTHROPIC_API_KEY",
        default_model="claude-sonnet-4-6",
    ),
    LLMProvider(
        label="Gemma 2 — RunPod",
        base_url="https://0wc79vfhndills-8000.proxy.runpod.net/v1",
        env_key="RUNPOD_GEMMA_2_API_KEY",
        default_model="google/gemma-2-9b-it",
    ),
]

PROVIDER_BY_LABEL: dict[str, LLMProvider] = {p.label: p for p in PROVIDERS}
