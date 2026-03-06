# GitHub Repository Summarizer API

A FastAPI service that takes a GitHub repository URL and returns a human-readable summary of the project using an LLM.

## Setup & Run

```bash
# 1. Clone / unzip the project and cd into it
cd github-summarizer

# 2. Create a virtual environment (optional but recommended)
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Set your LLM API key (pick one)
export NEBIUS_API_KEY="your-key-here"
# OR
export OPENAI_API_KEY="your-key-here"
# OR
export ANTHROPIC_API_KEY="your-key-here"

# 5. (Optional) Set a GitHub token for higher rate limits
export GITHUB_TOKEN="your-github-token"

# 6. Start the server
uvicorn app:app --host 0.0.0.0 --port 8000
```

## Test

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{"github_url": "https://github.com/psf/requests"}'
```

## Model Choice

**Nebius (default):** `meta-llama/Meta-Llama-3.1-70B-Instruct` — a strong open-source model with a large context window and good instruction-following for structured JSON output, available at low cost on Nebius Token Factory.

Falls back to OpenAI (`gpt-4o-mini`) or Anthropic (`claude-sonnet-4-20250514`) if the corresponding key is set instead.

## Approach to Repository Content Handling

### What gets included (prioritized)
1. **README** (highest priority) — the single best source of project purpose and description
2. **Config/manifest files** (`package.json`, `pyproject.toml`, `Cargo.toml`, `Dockerfile`, etc.) — reveal technologies, dependencies, and build setup
3. **Top-level source files** (`main.py`, `app.py`, `index.ts`, etc.) — show entry points and core logic
4. **Full directory tree** — gives structural overview even for files we don't read

### What gets skipped
- **Binary files** (images, compiled objects, fonts, archives)
- **Lock files** (`package-lock.json`, `yarn.lock`, `poetry.lock`, etc.) — large, low signal
- **Generated/vendored directories** (`node_modules/`, `dist/`, `build/`, `vendor/`, `__pycache__/`)
- **IDE config** (`.idea/`, `.vscode/`)

### Context budget management
- Total content sent to the LLM is capped at ~60k characters (~15-20k tokens)
- Files are ranked by a priority score and fetched in order until the budget is exhausted
- Individual files are truncated at 10k characters
- High-priority files (README, configs) get partial inclusion even when budget is tight
- The directory tree is always included (capped at 500 entries) so the LLM sees the full structure
