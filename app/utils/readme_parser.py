from __future__ import annotations
import base64
import re


# Headings that contain useful project information
_INCLUDE = re.compile(
    r"about|overview|description|introduction|summary|"
    r"what\s+is|why\s+|motivation|background|concept|"
    r"feature|capabilit|highlight|"
    r"architecture|design|how\s+it\s+works?|internals?|"
    r"tech\s*stack|built\s+with|technolog|"
    r"dependenc|prerequisite|requirement|librar|package|"
    r"component|module|structure|flow",
    re.IGNORECASE,
)

# Headings to always skip
_EXCLUDE = re.compile(
    r"install|setup|getting\s+started|quickstart|quick\s+start|"
    r"build|compil|run|start|deploy|docker|container|"
    r"test|ci\b|continuous|lint|"
    r"contribut|code\s+of\s+conduct|pull\s+request|"
    r"changelog|history|release|version|"
    r"license|copyright|author|credit|acknowledgement|"
    r"todo|roadmap|faq|troubleshoot",
    re.IGNORECASE,
)

_BADGE_LINE  = re.compile(r"^\s*(\[!\[|!\[|<img\b)", re.IGNORECASE)
_HEADING_LINE = re.compile(r"^#{1,4}\s+")

# A section must have at least this many meaningful characters to be shown
_MIN_CONTENT_CHARS = 80
# The overall result must reach this length, otherwise suppress the block
_MIN_TOTAL_CHARS = 60


def parse_readme(content_b64: str, max_chars: int = 3000) -> str:
    """Decode a base64 README and return only informational sections.

    Returns an empty string when the extracted content is too thin to be useful.
    """
    try:
        raw = base64.b64decode(content_b64).decode("utf-8", errors="replace")
    except Exception:
        return ""

    sections = re.split(r"\n(?=#{1,4}\s)", raw)
    parts: list[str] = []

    for idx, section in enumerate(sections):
        lines = section.strip().splitlines()
        if not lines:
            continue

        heading_line = lines[0].strip()
        heading_text = re.sub(r"^#+\s*", "", heading_line)

        # ── Intro block (text before first subheading) ────────────────────
        if idx == 0:
            cleaned = _clean(lines, strip_heading=True)
            if _is_substantial(cleaned):
                parts.append(cleaned[:800])
            continue

        # ── Skip excluded sections ────────────────────────────────────────
        if _EXCLUDE.search(heading_text):
            continue

        # ── Include matched sections ──────────────────────────────────────
        if _INCLUDE.search(heading_text):
            cleaned = _clean(lines, strip_heading=False)
            if _is_substantial(cleaned):
                parts.append(cleaned[:700])

    combined = "\n\n".join(parts).strip()
    if len(combined) < _MIN_TOTAL_CHARS:
        return ""
    return combined[:max_chars]


def _clean(lines: list[str], strip_heading: bool = False) -> str:
    """Remove badges, markdown heading lines (optionally), and excess blank lines."""
    kept: list[str] = []
    for line in lines:
        if _BADGE_LINE.match(line):
            continue
        if strip_heading and _HEADING_LINE.match(line.strip()):
            continue
        kept.append(line)
    text = "\n".join(kept)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def _is_substantial(text: str) -> bool:
    """Return True if the text has enough real content to be worth showing."""
    # Strip markdown syntax characters to count actual words
    plain = re.sub(r"[#*`>\[\]|_~]", " ", text)
    plain = re.sub(r"https?://\S+", "", plain)  # remove URLs from count
    words = plain.split()
    return len(text) >= _MIN_CONTENT_CHARS and len(words) >= 12
