# repo_scout
A desktop app for searching and AI-analysing GitHub repositories. Filter by domain, keywords, language, stars, and activity — then get a structured AI analysis of any result.

## Features

- Search GitHub repos with domain, keyword, language, star, fork, and activity filters
- Keyword highlighting in results
- README preview in the detail panel
- AI analysis (relevance, health, contribution scores + verdict) via Claude or Gemma 2 on RunPod
- Each "Analyze with AI" call opens a new tab, so you can compare results across providers

## Requirements

- Python 3.10+
- A GitHub personal access token
- An Anthropic API key (for Claude) and/or a RunPod API key (for Gemma 2)

## Setup

**1. Clone the repo**

```bash
git@github.com:Softhenge/repo_scout.git
cd repo-scout
```

**2. Install dependencies**

```bash
pip install -r requirements.txt
```

**3. Configure environment variables**

```bash
cp .env.example .env
```

Then open `.env` and fill in your tokens:

```env
GITHUB_TOKEN=your_github_personal_access_token

ANTHROPIC_API_KEY=your_anthropic_api_key
RUNPOD_GEMMA_2_API_KEY=your_runpod_api_key
```

- **GITHUB_TOKEN** — create one at https://github.com/settings/tokens (no scopes needed for public repo search)
- **ANTHROPIC_API_KEY** — from https://console.anthropic.com
- **RUNPOD_GEMMA_2_API_KEY** — from your RunPod deployment (leave empty if not using Gemma 2)

**4. Run**

```bash
python main.py
```
