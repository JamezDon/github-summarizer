# GitHub Repository Summarizer API

A FastAPI service that takes a GitHub repository URL and returns a human-readable summary using an LLM.

## Setup & Run

1. Unzip and enter the project directory

2. Create and activate a virtual environment:
   - On Linux/Mac: `python3 -m venv venv` then `source venv/bin/activate`
   - On Windows: `python -m venv venv` then `venv\Scripts\activate`

3. Install dependencies: `pip install -r requirements.txt`

4. Create a `.env` file in the project directory with your API keys:
```
   NEBIUS_API_KEY=your-nebius-key-here
   GITHUB_TOKEN=your-github-token-here
```

5. Start the server: `uvicorn app:app --host 0.0.0.0 --port 8000`

## Test

Send a POST request to `http://localhost:8000/summarize` with a JSON body:
```json
{"github_url": "https://github.com/psf/requests"}
```

## Model Choice

**meta-llama/Llama-3.3-70B-Instruct** via Nebius Token Factory — a strong open-source model with good instruction-following for structured JSON output, available at low cost.

## Approach to Repository Content Handling

### What gets included (by priority)
1. **README** (highest priority) — best source of project purpose and description
2. **Config/manifest files** (`package.json`, `pyproject.toml`, `Cargo.toml`, `Dockerfile`, etc.) — reveal technologies and dependencies
3. **Top-level source files** (`main.py`, `app.py`, `index.ts`, etc.) — show entry points and core logic
4. **Full directory tree** — gives structural overview even for files we don't read

### What gets skipped
- **Binary files** (images, compiled objects, fonts, archives)
- **Lock files** (`package-lock.json`, `yarn.lock`, `poetry.lock`, etc.) — large, low signal
- **Generated/vendored directories** (`node_modules/`, `dist/`, `build/`, `vendor/`, `__pycache__/`)
- **IDE config** (`.idea/`, `.vscode/`)

### Context budget management
- Total content sent to the LLM is capped at ~60k characters (~15-20k tokens)
- Files are ranked by priority score and fetched in order until the budget is exhausted
- Individual files are truncated at 10k characters
- High-priority files get partial inclusion even when budget is tight
- The directory tree is always included (capped at 500 entries) so the LLM sees the full structure