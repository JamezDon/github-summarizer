
"""GitHub Repository Summarizer API."""

import os
import re
import json
import base64
import logging
from typing import Optional

import httpx
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, field_validator

load_dotenv()

app = FastAPI(title="GitHub Repository Summarizer")
logger = logging.getLogger(__name__)

#Config
NEBIUS_API_KEY = os.environ.get("NEBIUS_API_KEY", "")
MAX_CONTENT_CHARS = 60_000


class SummarizeRequest(BaseModel):
    github_url: str

    @field_validator("github_url")
    @classmethod
    def validate_github_url(cls, v: str) -> str:
        v = v.strip().rstrip("/")
        pattern = r"^https?://github\.com/[\w.\-]+/[\w.\-]+$"
        if not re.match(pattern, v):
            raise ValueError("Invalid GitHub repository URL")
        return v

#Request/response models
class SummarizeResponse(BaseModel):
    summary: str
    technologies: list[str]
    structure: str


class ErrorResponse(BaseModel):
    status: str = "error"
    message: str


# GitHub helpers
SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".tox", ".mypy_cache",
    ".pytest_cache", "venv", "env", ".venv", ".env", "dist", "build",
    ".next", ".nuxt", "vendor", "target", ".idea", ".vscode",
    "coverage", ".coverage", "htmlcov", "egg-info", ".eggs",
}

SKIP_EXTENSIONS = {
    ".pyc", ".pyo", ".so", ".o", ".a", ".dylib", ".dll", ".exe",
    ".bin", ".dat", ".db", ".sqlite", ".sqlite3",
    ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".ico", ".svg", ".webp",
    ".mp3", ".mp4", ".wav", ".avi", ".mov", ".mkv",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".rar", ".7z",
    ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".pdf", ".doc", ".docx", ".xls", ".xlsx",
    ".min.js", ".min.css", ".map",
    ".lock",
}

SKIP_FILENAMES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "Pipfile.lock",
    "poetry.lock", "Gemfile.lock", "composer.lock", "cargo.lock",
    ".DS_Store", "Thumbs.db",
}

PRIORITY_FILES = {
    "readme.md": 100, "readme.rst": 100, "readme.txt": 100, "readme": 100,
    "setup.py": 80, "setup.cfg": 80, "pyproject.toml": 80,
    "package.json": 80, "cargo.toml": 80, "go.mod": 80,
    "gemfile": 80, "composer.json": 80, "build.gradle": 80, "pom.xml": 80,
    "makefile": 70, "dockerfile": 70, "docker-compose.yml": 70,
    "docker-compose.yaml": 70,
    "requirements.txt": 70, "requirements.in": 60,
    "tsconfig.json": 60, "webpack.config.js": 60,
    "app.py": 65, "main.py": 65, "index.ts": 65, "index.js": 65,
    "main.go": 65, "main.rs": 65, "lib.rs": 65,
    "manage.py": 60, "settings.py": 60,
}


def parse_github_url(url: str) -> tuple[str, str]:
    parts = url.rstrip("/").split("/")
    return parts[-2], parts[-1]


def should_skip_path(path: str) -> bool:
    parts = path.lower().split("/")
    for part in parts:
        if part in SKIP_DIRS or part.endswith(".egg-info"):
            return True
    return False


def should_skip_file(path: str) -> bool:
    filename = path.split("/")[-1].lower()
    if filename in SKIP_FILENAMES:
        return True
    for ext in SKIP_EXTENSIONS:
        if filename.endswith(ext):
            return True
    return False


def get_file_priority(path: str) -> int:
    lower = path.lower()
    filename = lower.split("/")[-1]
    for pattern, score in PRIORITY_FILES.items():
        if filename == pattern or lower.endswith(pattern):
            return score
    ext = "." + filename.rsplit(".", 1)[-1] if "." in filename else ""
    if ext in {".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".cpp", ".c", ".h"}:
        depth = path.count("/")
        return max(40 - depth * 5, 10)
    if ext in {".toml", ".yaml", ".yml", ".json", ".cfg", ".ini"}:
        return 30
    return 5


async def fetch_repo_tree(client: httpx.AsyncClient, owner: str, repo: str) -> list[dict]:
    url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/HEAD?recursive=1"
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    resp = await client.get(url, headers=headers, timeout=30)
    if resp.status_code == 404:
        raise HTTPException(status_code=404, detail="Repository not found or is private")
    if resp.status_code == 409:
        raise HTTPException(status_code=400, detail="Repository is empty")
    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"GitHub API error: {resp.status_code}")
    return resp.json().get("tree", [])


async def fetch_file_content(client: httpx.AsyncClient, owner: str, repo: str, path: str) -> Optional[str]:
    url = f"https://api.github.com/repos/{owner}/{repo}/contents/{path}"
    headers = {"Accept": "application/vnd.github.v3+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"token {token}"
    resp = await client.get(url, headers=headers, timeout=20)
    if resp.status_code != 200:
        return None
    data = resp.json()
    if data.get("encoding") == "base64" and data.get("content"):
        try:
            return base64.b64decode(data["content"]).decode("utf-8", errors="replace")
        except Exception:
            return None
    return None


async def gather_repo_content(owner: str, repo: str) -> tuple[str, str]:
    async with httpx.AsyncClient() as client:
        tree = await fetch_repo_tree(client, owner, repo)
        tree_lines = []
        candidate_files = []
        for item in tree:
            path = item.get("path", "")
            item_type = item.get("type", "")
            if should_skip_path(path):
                continue
            if item_type == "blob":
                if should_skip_file(path):
                    tree_lines.append(f"  {path}")
                    continue
                tree_lines.append(f"  {path}")
                size = item.get("size", 0)
                if size > 500_000:
                    continue
                priority = get_file_priority(path)
                candidate_files.append((priority, size, path))
            elif item_type == "tree":
                tree_lines.append(f"  {path}/")

        candidate_files.sort(key=lambda x: (-x[0], x[1]))
        dir_tree = "\n".join(tree_lines[:500])
        remaining_budget = MAX_CONTENT_CHARS - len(dir_tree)
        file_contents_parts = []

        for priority, size, path in candidate_files:
            if remaining_budget <= 0:
                break
            content = await fetch_file_content(client, owner, repo, path)
            if content is None:
                continue
            if len(content) > 10_000:
                content = content[:10_000] + "\n... [truncated]"
            entry = f"\n--- {path} ---\n{content}\n"
            if len(entry) > remaining_budget:
                if priority >= 70:
                    entry = entry[:remaining_budget]
                    file_contents_parts.append(entry)
                break
            file_contents_parts.append(entry)
            remaining_budget -= len(entry)

        return dir_tree, "".join(file_contents_parts)


# LLM Analysis
SYSTEM_PROMPT = """You are a senior software engineer analyzing a GitHub repository.
Given the repository's directory tree and key file contents, produce a structured analysis.

You MUST respond with valid JSON matching this exact schema:
{
  "summary": "A clear, concise description of what this project does and its purpose (2-4 sentences).",
  "technologies": ["list", "of", "main", "technologies", "languages", "frameworks"],
  "structure": "Brief description of how the project is organized (1-3 sentences)."
}

Guidelines:
- summary: Describe what the project does, its purpose, and who it's for. Be specific.
- technologies: List the primary programming languages, frameworks, libraries, and tools.
- structure: Describe the project layout — main source directories, test locations, docs, config.

Return ONLY the JSON object. No markdown, no code fences, no explanation."""


def build_user_prompt(owner: str, repo: str, dir_tree: str, file_contents: str) -> str:
    return f"""Analyze the GitHub repository: {owner}/{repo}

## Directory Structure
{dir_tree}

## Key File Contents
{file_contents}

Provide your analysis as a JSON object with "summary", "technologies", and "structure" fields."""


def call_llm(prompt: str, system: str) -> str:
    if not NEBIUS_API_KEY:
        raise HTTPException(status_code=500, detail="NEBIUS_API_KEY is not set.")
    from openai import OpenAI
    client = OpenAI(
        base_url="https://api.tokenfactory.nebius.com/v1/",
        api_key=NEBIUS_API_KEY,
    )
    response = client.chat.completions.create(
        model="meta-llama/Llama-3.3-70B-Instruct",
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": [{"type": "text", "text": prompt}]},
        ],
        max_tokens=1024,
        temperature=0.2,
    )
    return response.choices[0].message.content


def parse_llm_response(raw: str) -> dict:
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            data = json.loads(match.group())
        else:
            raise HTTPException(status_code=502, detail="LLM returned invalid JSON")
    return {
        "summary": data.get("summary", ""),
        "technologies": data.get("technologies", []),
        "structure": data.get("structure", ""),
    }


# Endpoint
@app.post("/summarize", response_model=SummarizeResponse)
async def summarize(request: SummarizeRequest):
    try:
        owner, repo = parse_github_url(request.github_url)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid GitHub URL format")

    try:
        dir_tree, file_contents = await gather_repo_content(owner, repo)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to fetch repository contents")
        raise HTTPException(status_code=502, detail=f"Failed to fetch repository: {str(e)}")

    if not dir_tree and not file_contents:
        raise HTTPException(status_code=400, detail="Repository appears to be empty")

    user_prompt = build_user_prompt(owner, repo, dir_tree, file_contents)

    try:
        raw_response = call_llm(user_prompt, SYSTEM_PROMPT)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("LLM API call failed")
        raise HTTPException(status_code=502, detail=f"LLM API error: {str(e)}")

    try:
        result = parse_llm_response(raw_response)
    except HTTPException:
        raise
    except Exception as e:
        logger.exception("Failed to parse LLM response")
        raise HTTPException(status_code=502, detail=f"Failed to parse LLM response: {str(e)}")

    return SummarizeResponse(**result)


@app.exception_handler(HTTPException)
async def http_exception_handler(request, exc):
    return JSONResponse(status_code=exc.status_code, content={"status": "error", "message": exc.detail})

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request, exc):
    return JSONResponse(status_code=400, content={"status": "error", "message": str(exc)})