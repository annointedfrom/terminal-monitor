# Docker Packaging Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Package Terminal Monitor as a Docker container so buyers can run it with `docker-compose up` â€” no Python, venv, or manual setup required.

**Architecture:** Python 3.11-slim image with a shell entrypoint that bootstraps `data/` and `config.yaml` on first run. `config.yaml` and `data/` are bind-mounted from the host so personal config and history survive container restarts. Ollama URL is read from an `OLLAMA_URL` environment variable (defaulting to `host.docker.internal:11434`) so the AI chat feature works across Mac, Windows, and Linux Docker environments.

**Tech Stack:** Docker, docker-compose v2, Python 3.11-slim, sh (POSIX shell for entrypoint)

---

## File Map

| Action | Path | Purpose |
|---|---|---|
| Modify | `termmon/scanner/ollama.py` | Read OLLAMA_URL from env var per call |
| Modify | `termmon/main.py` | Add `GET /health` endpoint |
| Modify | `tests/test_api.py` | Add health endpoint test |
| Create | `tests/test_ollama_url.py` | Test env var behavior |
| Create | `.dockerignore` | Exclude personal data and dev artifacts from image |
| Create | `docker-entrypoint.sh` | Bootstrap data/ and config.yaml, exec uvicorn |
| Create | `Dockerfile` | Python 3.11-slim image definition |
| Create | `docker-compose.yml` | Volumes, ports, env, extra_hosts |
| Create | `docs/docker-setup.md` | Buyer-facing setup instructions |

---

### Task 1: `/health` endpoint + OLLAMA_URL env var

**Files:**
- Modify: `termmon/scanner/ollama.py`
- Modify: `termmon/main.py`
- Modify: `tests/test_api.py`
- Create: `tests/test_ollama_url.py`

- [x] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
def test_health_endpoint():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
```

Create `tests/test_ollama_url.py`:

```python
import os
from unittest.mock import patch

import termmon.scanner.ollama as ollama_mod


def test_ollama_url_defaults_to_localhost():
    with patch.dict(os.environ, {}, clear=False):
        os.environ.pop("OLLAMA_URL", None)
        assert ollama_mod._ollama_url() == "http://localhost:11434"


def test_ollama_url_reads_env_var():
    with patch.dict(os.environ, {"OLLAMA_URL": "http://host.docker.internal:11434"}):
        assert ollama_mod._ollama_url() == "http://host.docker.internal:11434"
```

- [x] **Step 2: Run tests to verify they fail**

```powershell
cd C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor
.venv\Scripts\python -m pytest tests/test_api.py::test_health_endpoint tests/test_ollama_url.py -v
```

Expected: `test_health_endpoint` fails with 404; `test_ollama_url_reads_env_var` fails with AttributeError (`_ollama_url` not found).

- [x] **Step 3: Update `termmon/scanner/ollama.py`**

Replace the full file with:

```python
from __future__ import annotations

import os

import httpx

DEFAULT_MODEL = "llama3.2:3b"


def _ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")


async def generate(message: str, system: str, model: str = DEFAULT_MODEL) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{_ollama_url()}/api/generate",
                json={"model": model, "system": system, "prompt": message, "stream": False},
                timeout=30.0,
            )
            r.raise_for_status()
            return {"reply": r.json()["response"], "available": True}
    except Exception:
        return {"reply": None, "available": False}


async def list_models() -> list[str]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{_ollama_url()}/api/tags", timeout=5.0)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []
```

- [x] **Step 4: Add `/health` endpoint to `termmon/main.py`**

Find the `@app.get("/api/config")` route. Add this endpoint immediately before it:

```python
@app.get("/health")
async def health():
    return {"status": "ok"}
```

- [x] **Step 5: Run tests to verify they pass**

```powershell
.venv\Scripts\python -m pytest tests/test_api.py::test_health_endpoint tests/test_ollama_url.py -v
```

Expected: 3 PASSED.

- [x] **Step 6: Run full suite**

```powershell
.venv\Scripts\python -m pytest -v
```

Expected: All 68 tests pass.

- [x] **Step 7: Commit**

```powershell
git add termmon/scanner/ollama.py termmon/main.py tests/test_api.py tests/test_ollama_url.py
git commit -m "feat: read OLLAMA_URL from env, add /health endpoint"
```

---

### Task 2: `.dockerignore`

**Files:**
- Create: `.dockerignore`

- [x] **Step 1: Create `.dockerignore`**

```
# Python artifacts
__pycache__/
*.pyc
*.pyo
.pytest_cache/
.ruff_cache/
*.egg-info/

# Virtual environment
.venv/

# Personal data (gitignored, never ships in image)
config.yaml
data/
models/Modelfile
models/training_seed.jsonl
models/checkpoints/
models/*.gguf
models/Modelfile.generated

# Development-only files
.git/
tests/
docs/

# OS / IDE
.DS_Store
Thumbs.db
.vscode/
.idea/
```

- [x] **Step 2: Verify the ignore list**

```powershell
docker build --dry-run . 2>&1 | head -5
```

If `docker` is not installed yet, skip this step â€” it will be verified in Task 6.

- [x] **Step 3: Commit**

```powershell
git add .dockerignore
git commit -m "chore: add .dockerignore for Docker build"
```

---

### Task 3: `docker-entrypoint.sh`

**Files:**
- Create: `docker-entrypoint.sh`

- [x] **Step 1: Create `docker-entrypoint.sh`**

```sh
#!/bin/sh
set -e

# Ensure data directory exists for history persistence
mkdir -p /app/data

# Ensure config.yaml exists as a file (web setup wizard populates it)
if [ ! -f /app/config.yaml ]; then
  touch /app/config.yaml
fi

exec python -m uvicorn termmon.main:app --host 0.0.0.0 --port 8084
```

- [x] **Step 2: Make it executable**

```powershell
git add docker-entrypoint.sh
git update-index --chmod=+x docker-entrypoint.sh
```

- [x] **Step 3: Commit**

```powershell
git commit -m "chore: add Docker entrypoint script"
```

---

### Task 4: `Dockerfile`

**Files:**
- Create: `Dockerfile`

- [x] **Step 1: Create `Dockerfile`**

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install dependencies first for layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source
COPY termmon/ termmon/
COPY setup.py .
COPY config.example.yaml .
COPY models/ models/

# Entrypoint
COPY docker-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8084

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8084/health', timeout=4)"

ENTRYPOINT ["/entrypoint.sh"]
```

- [x] **Step 2: Commit**

```powershell
git add Dockerfile
git commit -m "chore: add Dockerfile (Python 3.11-slim)"
```

---

### Task 5: `docker-compose.yml`

**Files:**
- Create: `docker-compose.yml`

- [x] **Step 1: Create `docker-compose.yml`**

```yaml
services:
  terminal-monitor:
    build: .
    ports:
      - "8084:8084"
    volumes:
      - ./config.yaml:/app/config.yaml
      - ./data:/app/data
    environment:
      # Reaches Ollama running on the host machine (works on Mac, Windows, Linux)
      OLLAMA_URL: ${OLLAMA_URL:-http://host.docker.internal:11434}
    extra_hosts:
      # Makes host.docker.internal resolve on Linux (no-op on Mac/Windows Docker Desktop)
      - "host.docker.internal:host-gateway"
    restart: unless-stopped
```

- [x] **Step 2: Commit**

```powershell
git add docker-compose.yml
git commit -m "chore: add docker-compose.yml with volume mounts and Ollama host networking"
```

---

### Task 6: Docker smoke test

**Files:**
- No new files â€” verifies Tasks 1-5 work end to end

Prerequisites: Docker Desktop (Mac/Windows) or Docker Engine + Compose plugin (Linux) must be installed.

- [x] **Step 1: Create required host files**

```powershell
touch config.yaml
mkdir -p data
```

- [x] **Step 2: Build the image**

```powershell
docker build -t terminal-monitor:local .
```

Expected: `Successfully built <id>` with no errors. Should complete in under 3 minutes on first build (downloads Python base image + installs deps).

- [x] **Step 3: Start the container**

```powershell
docker-compose up -d
```

Expected: `Started terminal-monitor` with no errors.

- [x] **Step 4: Verify health endpoint**

```powershell
Start-Sleep -Seconds 5
Invoke-RestMethod http://localhost:8084/health
```

Expected output:
```
status
------
ok
```

- [x] **Step 5: Verify setup redirect**

Open `http://localhost:8084` in a browser. Expected: redirects to `/setup` (since `config.yaml` is empty).

- [x] **Step 6: Stop the container**

```powershell
docker-compose down
```

- [x] **Step 7: Commit smoke test notes (optional)**

If any workarounds were needed during the smoke test, document them:

```powershell
git add -A
git commit -m "fix: <whatever needed fixing after smoke test>"
```

---

### Task 7: `docs/docker-setup.md` + push to public repo

**Files:**
- Create: `docs/docker-setup.md`

- [x] **Step 1: Create `docs/docker-setup.md`**

```markdown
# Running Terminal Monitor with Docker

No Python setup needed. Docker handles everything.

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (Mac or Windows)
- Or Docker Engine + Compose plugin (Linux)
- Ollama running on your machine (optional â€” needed for AI chat)

## Quick Start

```bash
git clone https://github.com/annointedfrom/terminal-monitor
cd terminal-monitor
touch config.yaml
mkdir -p data
docker-compose up -d
```

Open `http://localhost:8084` â€” the setup wizard appears automatically on first run.

Fill in your preferences and click **SAVE CONFIG**. You'll be redirected to the dashboard.

## Ollama / AI Chat

The AI chat tab connects to Ollama running on your host machine. Docker-compose is
pre-configured to reach it at `host.docker.internal:11434`. Just make sure Ollama is
running before starting the container:

```bash
ollama serve          # starts Ollama if not already running
ollama pull ops-brain # or: ollama pull llama3.2:3b
docker-compose up -d
```

To use a different Ollama URL:

```bash
OLLAMA_URL=http://my-server:11434 docker-compose up -d
```

## Stopping and Restarting

```bash
docker-compose down   # stop
docker-compose up -d  # start again
```

Your `config.yaml` and `data/` history survive restarts because they're mounted from the host.

## Updating

```bash
docker-compose down
git pull
docker-compose up -d --build
```

## Ports

| Port | Service |
|------|---------|
| 8084 | Terminal Monitor dashboard |

## Data locations (on your host machine)

| Path | Contents |
|------|----------|
| `./config.yaml` | Your personal settings |
| `./data/` | Scan + resource history |
```

- [x] **Step 2: Run full test suite one last time**

```powershell
cd C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor
.venv\Scripts\python -m pytest -v
```

Expected: All 68 tests pass.

- [x] **Step 3: Commit docs**

```powershell
git add docs/docker-setup.md
git commit -m "docs: add Docker setup guide for buyers"
```

- [x] **Step 4: Push to public repo**

```powershell
git push origin master
```

- [x] **Step 5: Push to private dev repo**

```powershell
git push dev master
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task |
|---|---|
| Docker image builds and runs | 4, 6 |
| No Python setup for buyer | 4, 7 |
| config.yaml persists across restarts | 5 |
| data/ history persists across restarts | 5 |
| Ollama works from inside container | 1, 5 |
| /health endpoint for Agent Hub | 1 |
| Buyer docs | 7 |
| Both repos updated | 7 |

**Placeholder scan:** None â€” all steps contain complete code.

**Type consistency:** `_ollama_url()` defined in Task 1, called in same file only. `/health` returns `{"status": "ok"}` â€” consistent shape, no downstream consumers.
