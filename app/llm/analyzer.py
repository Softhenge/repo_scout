from __future__ import annotations
import json
from openai import OpenAI
from app.models.github_models import GitHubRepo
from app.models.ai_models import RepoAnalysis
from app.models.settings import settings
from app.llm.providers import LLMProvider, PROVIDERS
from app.utils.logger import get_logger

log = get_logger("analyzer")


class RepoAnalyzer:
    def __init__(self, provider: LLMProvider | None = None):
        self._provider = provider or PROVIDERS[0]  # default: Claude
        api_key = settings.get_key_for_env_var(self._provider.env_key) or "no-key"
        self._client = OpenAI(
            base_url=self._provider.base_url,
            api_key=api_key,
        )
        self._model = self._provider.default_model
        log.info(
            "RepoAnalyzer initialized  provider=%s  model=%s",
            self._provider.label, self._model,
        )

    def set_provider(self, provider: LLMProvider) -> None:
        """Switch provider at runtime (called when user changes combobox)."""
        self._provider = provider
        api_key = settings.get_key_for_env_var(provider.env_key) or "no-key"
        self._client = OpenAI(base_url=provider.base_url, api_key=api_key)
        self._model = provider.default_model
        log.info(
            "RepoAnalyzer switched  provider=%s  model=%s",
            provider.label, self._model,
        )

    @property
    def provider(self) -> LLMProvider:
        return self._provider

    def has_key(self) -> bool:
        """Return True if a key is configured for the current provider (Ollama is always OK)."""
        if not self._provider.env_key:
            return True  # local / no-key provider
        return bool(settings.get_key_for_env_var(self._provider.env_key))

    def analyze_repo(self, repo: GitHubRepo, readme: str = "") -> RepoAnalysis:
        """Calls the selected LLM provider and returns a validated RepoAnalysis.
        Called only on explicit user request — never during search.
        """
        log.info(
            "Requesting AI analysis  repo=%s  provider=%s  model=%s  readme_chars=%d",
            repo.full_name, self._provider.label, self._model, len(readme),
        )
        prompt = self._build_prompt(repo, readme)

        log.debug(
            "── PROMPT SENT (%s) ─────────────────────────────────\n%s\n"
            "─────────────────────────────────────────────────────",
            self._provider.label, prompt,
        )

        response = self._client.chat.completions.create(
            model=self._model,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )
        raw = response.choices[0].message.content or ""
        usage = response.usage

        log.debug(
            "── RESPONSE RECEIVED (%s) ───────────────────────────\n%s\n"
            "─────────────────────────────────────────────────────",
            self._provider.label, raw,
        )

        if usage:
            log.info(
                "LLM usage  provider=%s  repo=%s  input_tokens=%d  output_tokens=%d  total=%d",
                self._provider.label, repo.full_name,
                usage.prompt_tokens, usage.completion_tokens,
                usage.total_tokens,
            )

        result = self._parse_response(repo.full_name, raw)
        log.info(
            "AI analysis complete  provider=%s  repo=%s  "
            "relevance=%.1f  health=%.1f  contribution=%.1f  final=%.1f",
            self._provider.label, repo.full_name,
            result.relevance_score.score,
            result.health_score.score,
            result.contribution_score.score,
            result.final_score,
        )
        return result

    # ── Private helpers ───────────────────────────────────────────────────────

    def _build_prompt(self, repo: GitHubRepo, readme: str = "") -> str:
        topics = ", ".join(repo.topics) if repo.topics else "none"
        license_name = repo.license.name if repo.license else "unknown"
        owner_type = repo.owner.type or "unknown"
        pushed = repo.pushed_at.strftime("%Y-%m-%d") if repo.pushed_at else "unknown"

        readme_section = (
            f"\nREADME (overview sections only):\n{readme}\n"
            if readme else
            "\nREADME: not available\n"
        )

        return (
            f"Analyze this GitHub repository for a developer evaluating it.\n\n"
            f"## Repository Data\n"
            f"Name: {repo.full_name}\n"
            f"Owner type: {owner_type}\n"
            f"Description: {repo.description or 'No description'}\n"
            f"Language: {repo.language or 'unknown'}\n"
            f"Stars: {repo.stargazers_count:,}\n"
            f"Forks: {repo.forks_count:,}\n"
            f"Open issues: {repo.open_issues_count:,}\n"
            f"Topics: {topics}\n"
            f"License: {license_name}\n"
            f"Default branch: {repo.default_branch}\n"
            f"Last pushed: {pushed}\n"
            f"Archived: {repo.archived}\n"
            f"{readme_section}\n"
            f"## Instructions\n"
            f"Score each dimension from 0.0 to 10.0. Be specific in reasons.\n\n"
            f"Reply with ONLY a valid JSON object matching this exact schema:\n"
            f"{{\n"
            f'  "summary": "2-3 sentence description of what the project does",\n'
            f'  "target_audience": "who this project is for",\n'
            f'  "relevance_score": {{\n'
            f'    "score": 7.5,\n'
            f'    "reasons": ["keyword X found in name", "topic Y matches", "language matches"]\n'
            f'  }},\n'
            f'  "health_score": {{\n'
            f'    "score": 8.0,\n'
            f'    "reasons": ["pushed N days ago", "not archived", "N open issues is manageable"]\n'
            f'  }},\n'
            f'  "contribution_score": {{\n'
            f'    "score": 6.5,\n'
            f'    "reasons": ["N open issues", "README is clear", "has contributing guide"]\n'
            f'  }},\n'
            f'  "final_score": 7.5,\n'
            f'  "verdict": "one-line verdict for a developer"\n'
            f"}}"
        )

    def _parse_response(self, full_name: str, raw: str) -> RepoAnalysis:
        text = raw.strip()
        if text.startswith("```"):
            text = text.split("\n", 1)[-1]
            text = text.rsplit("```", 1)[0]
        try:
            data = json.loads(text.strip())
        except json.JSONDecodeError as exc:
            log.error(
                "Failed to parse LLM JSON  provider=%s  repo=%s  error=%s  raw=%.300s",
                self._provider.label, full_name, exc, raw,
            )
            raise
        return RepoAnalysis(repo_full_name=full_name, **data)
