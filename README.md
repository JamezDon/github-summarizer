# GitHub Repository Summarizer API

A FastAPI service that takes a GitHub repository URL and returns a human-readable summary using an LLM.

## Setup & Run

1. Unzip and enter the project directory

2. Create and activate a virtual environment: `python3 -m venv .venv` then `source .venv/bin/activate`

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

Example using curl:
```
curl -X POST http://localhost:8000/summarize   -H "Content-Type: application/json"   -d '{"github_url": "https://github.com/microsoft/mcp-for-beginners"}'
```

Example response:
```json
{"summary":"The microsoft/mcp-for-beginners GitHub repository provides a comprehensive guide for beginners to learn about Microsoft's Cloud Partner Program (MCP) and its related technologies. It includes tutorials, examples, and exercises in various programming languages such as Python, TypeScript, Java, and C#. The repository covers topics like security, deployment, and advanced concepts, making it a valuable resource for developers and IT professionals looking to enhance their skills in cloud computing and MCP.",
"technologies":["Python","TypeScript","Java","C#","Azure","MCP","Cloud Computing","Docker","Rust","dotnet"],
"structure":"The repository is organized into several sections, including introductions to MCP, core concepts, security, and getting started guides for various programming languages. It also includes advanced topics, deployment strategies, and testing techniques, with each section containing detailed tutorials, code examples, and exercises to help learners practice and reinforce their understanding of the subject matter."}
```

## Model Choice

I went with **meta-llama/Llama-3.3-70B-Instruct** on Nebius Token Factory. It's the biggest Llama model available there and handles code well. The main reason I picked it is that it reliably outputs valid JSON when asked, which is important since the API needs structured responses. It's also cheap to run on Nebius.

I considered using OpenAI's GPT-4o or Anthropic's Claude, which would probably give slightly better summaries, but they're significantly more expensive per token. Since the Llama 3.3 70B model is more than capable for this task, it didn't seem worth the extra cost. I also looked at smaller models like Llama 8B on Nebius, but found the 70B version was noticeably better at following the JSON schema consistently and producing more detailed summaries.

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