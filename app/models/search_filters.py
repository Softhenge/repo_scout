from __future__ import annotations
from datetime import date, timedelta
from typing import Optional
from pydantic import BaseModel, Field


PREDEFINED_DOMAINS: dict[str, list[str]] = {
    # value = list of topic alternatives (OR-ed as keywords, not topic: qualifiers)
    "Machine Learning / AI": ["machine-learning", "deep-learning", "neural-network", "llm"],
    "Web Development":        ["web", "frontend", "backend", "rest-api"],
    "DevOps / Infrastructure":["devops", "kubernetes", "infrastructure", "cicd"],
    "Data Science":           ["data-science", "data-analysis", "pandas", "jupyter"],
    "Security":               ["security", "cybersecurity", "cryptography"],
    "Mobile":                 ["android", "ios", "flutter", "react-native"],
    "Databases":              ["database", "postgresql", "mongodb", "redis"],
    "CLI Tools":              ["cli", "command-line", "terminal", "shell"],
    "Game Development":       ["game", "gamedev", "unity", "pygame"],
    "Blockchain":             ["blockchain", "ethereum", "web3", "solidity"],
}

ACTIVITY_OPTIONS: dict[str, Optional[date]] = {
    "Any time":      None,
    "Last week":     date.today() - timedelta(weeks=1),
    "Last month":    date.today() - timedelta(days=30),
    "Last 3 months": date.today() - timedelta(days=90),
    "Last 6 months": date.today() - timedelta(days=180),
    "Last year":     date.today() - timedelta(days=365),
}

LANGUAGES = [
    "Any", "Python", "JavaScript", "TypeScript", "Go", "Rust",
    "Java", "C++", "C", "C#", "Ruby", "PHP", "Swift", "Kotlin",
    "Dart", "Shell", "Scala", "R",
]

STAR_OPTIONS: dict[str, int] = {
    "Any":   0,
    "50+":   50,
    "100+":  100,
    "500+":  500,
    "1K+":   1_000,
    "5K+":   5_000,
    "10K+":  10_000,
    "50K+":  50_000,
}

FORK_OPTIONS: dict[str, int] = {
    "Any":   0,
    "10+":   10,
    "50+":   50,
    "100+":  100,
    "500+":  500,
    "1K+":   1_000,
    "5K+":   5_000,
}


class SearchFilters(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)   # selected domain labels
    min_stars: int = 0
    min_forks: int = 0
    language: Optional[str] = None                     # None means any
    topics: list[str] = Field(default_factory=list)    # extra topic tags
    pushed_after: Optional[date] = None                # recent activity cutoff
    sort: str = "stars"

    def build_query(self) -> str:
        parts: list[str] = []

        # Collect all domain keyword alternatives and OR them together so
        # GitHub matches repos that have ANY of them (not all at once).
        domain_terms: list[str] = []
        for label in self.domains:
            domain_terms.extend(PREDEFINED_DOMAINS.get(label, [label]))

        # User free-text keywords also go into the OR group.
        # Multi-word phrases are quoted so GitHub treats them as a phrase search.
        def _quoted(term: str) -> str:
            return f'"{term}"' if " " in term else term

        all_text_terms = [_quoted(t) for t in domain_terms + self.keywords]
        if all_text_terms:
            if len(all_text_terms) == 1:
                parts.append(all_text_terms[0])
            else:
                parts.append(f"({' OR '.join(all_text_terms)})")

        # Required topics: match repos that have the tag assigned OR have the
        # term in their repository name — so manually tagged AND named repos qualify.
        for topic in self.topics:
            if topic:
                parts.append(f"(topic:{topic} OR {topic} in:name)")

        if self.min_stars > 0:
            parts.append(f"stars:>={self.min_stars}")

        if self.min_forks > 0:
            parts.append(f"forks:>={self.min_forks}")

        if self.language:
            parts.append(f"language:{self.language}")

        if self.pushed_after:
            parts.append(f"pushed:>={self.pushed_after.isoformat()}")

        return " ".join(parts) if parts else "stars:>=100"
