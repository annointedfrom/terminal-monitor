# Terminal Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a FastAPI agent (port 8084) that scans all listening localhost ports, checks their health, detects running MCP servers from Claude Code's settings, feeds snapshots to the NeuroLinked brain every 60s, and appears in the Agent Hub as a new Ops Room character.

**Architecture:** Three scanner modules (ports via psutil, health via httpx, MCP via process matching) feed a single `_full_scan()` function in `main.py`. A background asyncio task syncs scan results to the brain every 60 seconds. The Agent Hub frontend gets a new `ops-room` splitting the current full-width Scout HQ row.

**Tech Stack:** Python 3.12, FastAPI, psutil, httpx, PyYAML, pytest, pytest-asyncio, respx

---

## File Map

| File | Responsibility |
|------|---------------|
| `termmon/__init__.py` | Package marker |
| `termmon/scanner/__init__.py` | Package marker |
| `termmon/scanner/ports.py` | psutil port + process enumeration |
| `termmon/scanner/health.py` | httpx concurrent health pings |
| `termmon/scanner/mcp.py` | Claude settings.json + process matching |
| `termmon/brain.py` | NeuroLinked POST helpers |
| `termmon/main.py` | FastAPI app + background brain sync + v2 stubs |
| `tests/test_ports.py` | Unit tests for ports scanner |
| `tests/test_health.py` | Unit tests for health pings |
| `tests/test_mcp.py` | Unit tests for MCP detector |
| `tests/test_api.py` | API endpoint tests |
| `requirements.txt` | Python dependencies |
| `pytest.ini` | asyncio_mode = auto |
| `README.md` | Setup and run instructions |

---

### Task 1: Project Scaffold

**Files:**
- Create: `requirements.txt`
- Create: `pytest.ini`
- Create: `termmon/__init__.py`
- Create: `termmon/scanner/__init__.py`
- Create: `tests/__init__.py`

- [ ] **Step 1: Create project directories**

```powershell
cd C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor
mkdir termmon\scanner, tests
```

- [ ] **Step 2: Write `requirements.txt`**

```
fastapi>=0.110.0
uvicorn[standard]>=0.29.0
httpx>=0.27.0
psutil>=5.9.0
pyyaml>=6.0.1
pytest>=8.2.0
pytest-asyncio>=0.23.0
respx>=0.21.0
```

- [ ] **Step 3: Write `pytest.ini`**

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 4: Create empty package markers**

`termmon/__init__.py` — empty file
`termmon/scanner/__init__.py` — empty file
`tests/__init__.py` — empty file

- [ ] **Step 5: Create and activate virtual environment**

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

Expected: all packages install without error.

- [ ] **Step 6: Verify pytest runs (no tests yet)**

```powershell
.\.venv\Scripts\python -m pytest tests/ -v
```

Expected: `no tests ran` or `0 passed`.

- [ ] **Step 7: Commit**

```powershell
git add requirements.txt pytest.ini termmon\ tests\
git commit -m "chore: project scaffold"
```

---

### Task 2: Port Scanner (`termmon/scanner/ports.py`)

**Files:**
- Create: `termmon/scanner/ports.py`
- Create: `tests/test_ports.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_ports.py`:

```python
import pathlib
import tempfile
import time
from unittest.mock import MagicMock, patch

import yaml

from termmon.scanner.ports import _load_labels, scan_ports


def test_load_labels_from_yaml():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"agents": [{"port": 8082, "name": "Job Agent"}]}, f)
        path = pathlib.Path(f.name)
    labels = _load_labels(path)
    assert labels == {8082: "Job Agent"}


def test_load_labels_missing_file():
    labels = _load_labels(pathlib.Path("/nonexistent/path.yaml"))
    assert labels == {}


def _make_conn(port, pid, status="LISTEN"):
    conn = MagicMock()
    conn.status = status
    conn.laddr = MagicMock(port=port)
    conn.pid = pid
    return conn


def test_scan_ports_filters_listen_only():
    conn_listen = _make_conn(8082, 100, "LISTEN")
    conn_established = _make_conn(9000, 200, "ESTABLISHED")

    mock_proc = MagicMock()
    mock_proc.name.return_value = "python.exe"
    mock_proc.memory_info.return_value = MagicMock(rss=50 * 1024 * 1024)
    mock_proc.create_time.return_value = 0.0

    with patch("psutil.net_connections", return_value=[conn_listen, conn_established]), \
         patch("psutil.Process", return_value=mock_proc), \
         patch("time.time", return_value=3600.0):
        result = scan_ports(hub_config_path=pathlib.Path("/nonexistent.yaml"))

    assert len(result) == 1
    assert result[0]["port"] == 8082


def test_scan_ports_attaches_label():
    conn = _make_conn(8082, 100)

    mock_proc = MagicMock()
    mock_proc.name.return_value = "python.exe"
    mock_proc.memory_info.return_value = MagicMock(rss=10 * 1024 * 1024)
    mock_proc.create_time.return_value = 0.0

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"agents": [{"port": 8082, "name": "Job Agent"}]}, f)
        cfg_path = pathlib.Path(f.name)

    with patch("psutil.net_connections", return_value=[conn]), \
         patch("psutil.Process", return_value=mock_proc), \
         patch("time.time", return_value=3600.0):
        result = scan_ports(hub_config_path=cfg_path)

    assert result[0]["label"] == "Job Agent"
```

- [ ] **Step 2: Run tests — verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests/test_ports.py -v
```

Expected: FAIL with `ModuleNotFoundError` or `ImportError`.

- [ ] **Step 3: Implement `termmon/scanner/ports.py`**

```python
from __future__ import annotations

import time
from pathlib import Path
from typing import Optional

import psutil
import yaml


def _load_labels(hub_config_path: Path) -> dict[int, str]:
    try:
        with open(hub_config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return {a["port"]: a["name"] for a in data.get("agents", [])}
    except Exception:
        return {}


def scan_ports(hub_config_path: Optional[Path] = None) -> list[dict]:
    if hub_config_path is None:
        hub_config_path = (
            Path(__file__).parent.parent.parent.parent / "agent-hub" / "hub-config.yaml"
        )
    labels = _load_labels(hub_config_path)

    results = []
    seen_ports: set[int] = set()

    for conn in psutil.net_connections(kind="inet"):
        if conn.status != "LISTEN":
            continue
        port = conn.laddr.port
        if port in seen_ports:
            continue
        seen_ports.add(port)

        pid = conn.pid
        process_name = "unknown"
        memory_mb = 0.0
        uptime_s = 0

        if pid:
            try:
                proc = psutil.Process(pid)
                process_name = proc.name()
                memory_mb = round(proc.memory_info().rss / 1024 / 1024, 1)
                uptime_s = int(time.time() - proc.create_time())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        results.append({
            "port": port,
            "pid": pid,
            "process": process_name,
            "memory_mb": memory_mb,
            "uptime_s": uptime_s,
            "healthy": False,
            "label": labels.get(port, ""),
        })

    return sorted(results, key=lambda x: x["port"])
```

- [ ] **Step 4: Run tests — verify they pass**

```powershell
.\.venv\Scripts\python -m pytest tests/test_ports.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```powershell
git add termmon\scanner\ports.py tests\test_ports.py
git commit -m "feat: port scanner with psutil and hub label lookup"
```

---

### Task 3: Health Checker (`termmon/scanner/health.py`)

**Files:**
- Create: `termmon/scanner/health.py`
- Create: `tests/test_health.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_health.py`:

```python
import httpx
import pytest
import respx

from termmon.scanner.health import check_health

_PORT_ENTRY = {
    "port": 8082,
    "pid": 1,
    "process": "python.exe",
    "memory_mb": 50.0,
    "uptime_s": 100,
    "healthy": False,
    "label": "Job Agent",
}


@pytest.mark.asyncio
async def test_healthy_port():
    with respx.mock:
        respx.get("http://localhost:8082/health").mock(return_value=httpx.Response(200))
        result = await check_health([_PORT_ENTRY])
    assert result[0]["healthy"] is True


@pytest.mark.asyncio
async def test_unhealthy_port_connection_error():
    entry = {**_PORT_ENTRY, "port": 9999, "label": ""}
    with respx.mock:
        respx.get("http://localhost:9999/health").mock(
            side_effect=httpx.ConnectError("refused")
        )
        result = await check_health([entry])
    assert result[0]["healthy"] is False


@pytest.mark.asyncio
async def test_falls_back_to_root_on_404():
    entry = {**_PORT_ENTRY, "port": 34872, "label": "Roblox"}
    with respx.mock:
        respx.get("http://localhost:34872/health").mock(return_value=httpx.Response(404))
        respx.get("http://localhost:34872/").mock(return_value=httpx.Response(200))
        result = await check_health([entry])
    assert result[0]["healthy"] is True
```

- [ ] **Step 2: Run tests — verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests/test_health.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `termmon/scanner/health.py`**

```python
from __future__ import annotations

import asyncio

import httpx


async def _ping(client: httpx.AsyncClient, port: int) -> bool:
    try:
        r = await client.get(f"http://localhost:{port}/health", timeout=1.5)
        if r.status_code != 404:
            return r.status_code < 500
        r2 = await client.get(f"http://localhost:{port}/", timeout=1.5)
        return r2.status_code < 500
    except Exception:
        return False


async def check_health(ports: list[dict]) -> list[dict]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_ping(client, p["port"]) for p in ports])
    return [{**p, "healthy": healthy} for p, healthy in zip(ports, results)]
```

- [ ] **Step 4: Run tests — verify they pass**

```powershell
.\.venv\Scripts\python -m pytest tests/test_health.py -v
```

Expected: 3 PASSED.

- [ ] **Step 5: Commit**

```powershell
git add termmon\scanner\health.py tests\test_health.py
git commit -m "feat: async health checker with /health fallback to /"
```

---

### Task 4: MCP Detector (`termmon/scanner/mcp.py`)

**Files:**
- Create: `termmon/scanner/mcp.py`
- Create: `tests/test_mcp.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_mcp.py`:

```python
import json
import pathlib
import tempfile
from unittest.mock import MagicMock, patch

from termmon.scanner.mcp import _read_mcp_config, scan_mcp


def _make_settings(servers: dict) -> pathlib.Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"mcpServers": servers}, f)
        return pathlib.Path(f.name)


def test_read_mcp_config_parses_servers():
    path = _make_settings({"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}})
    result = _read_mcp_config(path)
    assert "playwright" in result


def test_read_mcp_config_missing_file():
    result = _read_mcp_config(pathlib.Path("/nonexistent.json"))
    assert result == {}


def test_scan_mcp_running():
    path = _make_settings({"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}})
    mock_proc = MagicMock()
    mock_proc.info = {
        "pid": 9999,
        "name": "node.exe",
        "cmdline": ["node", "@playwright/mcp@latest"],
    }
    with patch("psutil.process_iter", return_value=[mock_proc]):
        result = scan_mcp(settings_path=path)
    assert result[0]["name"] == "playwright"
    assert result[0]["running"] is True
    assert result[0]["pid"] == 9999


def test_scan_mcp_not_running():
    path = _make_settings(
        {"chrome-devtools-mcp": {"command": "npx", "args": ["chrome-devtools-mcp"]}}
    )
    with patch("psutil.process_iter", return_value=[]):
        result = scan_mcp(settings_path=path)
    assert result[0]["running"] is False
    assert result[0]["pid"] is None
```

- [ ] **Step 2: Run tests — verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests/test_mcp.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `termmon/scanner/mcp.py`**

```python
from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

import psutil


def _settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _read_mcp_config(settings_path: Path) -> dict[str, dict]:
    try:
        with open(settings_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("mcpServers", {})
    except Exception:
        return {}


def _find_process(token: str) -> tuple[bool, Optional[int]]:
    token_lower = token.lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or []).lower()
            if token_lower in cmdline:
                return True, proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False, None


def scan_mcp(settings_path: Optional[Path] = None) -> list[dict]:
    if settings_path is None:
        settings_path = _settings_path()
    servers = _read_mcp_config(settings_path)

    results = []
    for name, config in servers.items():
        command = config.get("command", "")
        args = config.get("args", [])

        search_token = name
        for arg in reversed(args):
            if not arg.startswith("-") and len(arg) > 2:
                search_token = arg
                break

        running, pid = _find_process(search_token)
        full_command = f"{command} {' '.join(str(a) for a in args)}".strip()
        results.append({
            "name": name,
            "command": full_command,
            "running": running,
            "pid": pid,
        })

    return results
```

- [ ] **Step 4: Run tests — verify they pass**

```powershell
.\.venv\Scripts\python -m pytest tests/test_mcp.py -v
```

Expected: 4 PASSED.

- [ ] **Step 5: Commit**

```powershell
git add termmon\scanner\mcp.py tests\test_mcp.py
git commit -m "feat: MCP detector via Claude settings.json and process matching"
```

---

### Task 5: Brain Sync (`termmon/brain.py`)

**Files:**
- Create: `termmon/brain.py`

No dedicated test file — brain.py is exercised via `test_api.py` in Task 6.

- [ ] **Step 1: Implement `termmon/brain.py`**

```python
from __future__ import annotations

import logging

import httpx

BRAIN_URL = "http://localhost:8000"
logger = logging.getLogger(__name__)


async def sync(scan_result: dict) -> None:
    summary = scan_result.get("summary", {})
    ports = scan_result.get("ports", [])

    port_list = ", ".join(
        f"{p['port']} {p['label'] or p['process']} {'healthy' if p['healthy'] else 'down'}"
        for p in ports[:10]
    )
    text = (
        f"Terminal Monitor snapshot: {summary.get('port_count', 0)} ports active, "
        f"{summary.get('mcp_count', 0)} MCP servers running. "
        f"Ports: [{port_list}]"
    )

    async with httpx.AsyncClient() as client:
        try:
            await client.post(
                f"{BRAIN_URL}/api/claude/remember",
                json={
                    "text": text,
                    "source": "terminal-monitor",
                    "tags": ["terminal-monitor", "system-state", "ports", "mcp-servers"],
                },
                timeout=5.0,
            )
            await client.post(
                f"{BRAIN_URL}/api/claude/observe",
                json={
                    "type": "action",
                    "content": (
                        f"Terminal Monitor auto-sync: {summary.get('port_count', 0)} ports, "
                        f"{summary.get('mcp_count', 0)} MCP online"
                    ),
                    "source": "terminal-monitor",
                },
                timeout=5.0,
            )
        except Exception as exc:
            logger.warning("Brain sync failed: %s", exc)
```

- [ ] **Step 2: Commit**

```powershell
git add termmon\brain.py
git commit -m "feat: brain sync module with fire-and-forget error handling"
```

---

### Task 6: FastAPI App (`termmon/main.py`)

**Files:**
- Create: `termmon/main.py`
- Create: `tests/test_api.py`

- [ ] **Step 1: Write the failing tests**

`tests/test_api.py`:

```python
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from termmon.main import app

client = TestClient(app)


def _mock_scan():
    return {
        "scanned_at": "2026-05-18T00:00:00+00:00",
        "ports": [
            {
                "port": 8082,
                "pid": 1,
                "process": "python.exe",
                "memory_mb": 50.0,
                "uptime_s": 100,
                "healthy": True,
                "label": "Job Agent",
            }
        ],
        "mcp_servers": [
            {"name": "playwright", "command": "npx @playwright/mcp@latest", "running": True, "pid": 9999}
        ],
        "summary": {"port_count": 1, "mcp_count": 1, "process_count": 1},
    }


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_scan_returns_required_keys():
    with patch("termmon.main._full_scan", new=AsyncMock(return_value=_mock_scan())):
        r = client.get("/api/scan")
    assert r.status_code == 200
    data = r.json()
    assert "ports" in data
    assert "mcp_servers" in data
    assert "summary" in data


def test_stats_port_count():
    with patch("termmon.main.scan_ports", return_value=[{"port": 8082}, {"port": 8084}]):
        r = client.get("/api/stats/port_count")
    assert r.status_code == 200
    assert r.json() == 2


def test_stats_mcp_count():
    with patch(
        "termmon.main.scan_mcp",
        return_value=[
            {"running": True, "pid": 1},
            {"running": False, "pid": None},
        ],
    ):
        r = client.get("/api/stats/mcp_count")
    assert r.status_code == 200
    assert r.json() == 1


def test_brain_sync_endpoint():
    mock_sync = AsyncMock()
    with patch("termmon.main._full_scan", new=AsyncMock(return_value=_mock_scan())), \
         patch("termmon.main.brain.sync", new=mock_sync):
        r = client.post("/api/brain/sync")
    assert r.status_code == 200
    assert r.json()["synced"] is True
    mock_sync.assert_called_once()


def test_kill_stub_returns_501():
    r = client.post("/api/kill/12345")
    assert r.status_code == 501


def test_restart_stub_returns_501():
    r = client.post("/api/restart/job-agent")
    assert r.status_code == 501
```

- [ ] **Step 2: Run tests — verify they fail**

```powershell
.\.venv\Scripts\python -m pytest tests/test_api.py -v
```

Expected: FAIL with `ImportError`.

- [ ] **Step 3: Implement `termmon/main.py`**

```python
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from termmon import brain
from termmon.scanner.health import check_health
from termmon.scanner.mcp import scan_mcp
from termmon.scanner.ports import scan_ports

logger = logging.getLogger(__name__)


async def _full_scan() -> dict:
    ports = scan_ports()
    ports = await check_health(ports)
    mcps = scan_mcp()
    mcp_count = sum(1 for m in mcps if m["running"])
    process_names = {p["process"] for p in ports if p["process"] != "unknown"}
    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "ports": ports,
        "mcp_servers": mcps,
        "summary": {
            "port_count": len(ports),
            "mcp_count": mcp_count,
            "process_count": len(process_names),
        },
    }


async def _brain_loop() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            result = await _full_scan()
            await brain.sync(result)
        except Exception as exc:
            logger.warning("Brain loop error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_brain_loop())
    yield
    task.cancel()


app = FastAPI(title="Terminal Monitor", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/scan")
async def get_scan():
    return await _full_scan()


@app.get("/api/mcp")
async def get_mcp():
    return scan_mcp()


@app.get("/api/stats/port_count")
async def stats_port_count():
    return len(scan_ports())


@app.get("/api/stats/mcp_count")
async def stats_mcp_count():
    return sum(1 for m in scan_mcp() if m["running"])


@app.get("/api/stats/process_count")
async def stats_process_count():
    ports = scan_ports()
    return len({p["process"] for p in ports if p["process"] != "unknown"})


@app.post("/api/brain/sync")
async def brain_sync():
    result = await _full_scan()
    await brain.sync(result)
    return {"synced": True, "summary": result["summary"]}


@app.post("/api/kill/{pid}")
async def kill_process(pid: int):
    return JSONResponse(status_code=501, content={"detail": "kill not implemented (v2)"})


@app.post("/api/restart/{agent_id}")
async def restart_agent(agent_id: str):
    return JSONResponse(status_code=501, content={"detail": "restart not implemented (v2)"})
```

- [ ] **Step 4: Run all tests — verify they pass**

```powershell
.\.venv\Scripts\python -m pytest tests/ -v
```

Expected: 18 PASSED (4 ports + 3 health + 4 mcp + 7 api).

- [ ] **Step 5: Commit**

```powershell
git add termmon\main.py tests\test_api.py
git commit -m "feat: FastAPI app with scan endpoints, stats, brain sync, and v2 stubs"
```

---

### Task 7: Agent Hub Integration

**Files:**
- Modify: `../agent-hub/hub-config.yaml`
- Modify: `../agent-hub/frontend/index.html`

No new tests — changes are config + HTML/CSS/JS. Verify visually at http://localhost:8090 after the hub reloads.

- [ ] **Step 1: Add terminal-monitor to `hub-config.yaml`**

Append to the end of `C:\Users\hms16\Me\MyWords\Sandbox\projects\agent-hub\hub-config.yaml`:

```yaml
  - id: terminal-monitor
    name: Terminal Monitor
    class: Ops Monitor
    port: 8084
    health: /health
    dashboard: http://localhost:8084/docs
    start_command: "uvicorn termmon.main:app --port 8084"
    character: "🖥️"
    room: ops-room
    stats:
      - label: Active Ports
        endpoint: /api/stats/port_count
      - label: MCP Online
        endpoint: /api/stats/mcp_count
      - label: Processes
        endpoint: /api/stats/process_count
    actions:
      - key: A
        label: Refresh Scan
        endpoint: /api/scan
        method: GET
      - key: B
        label: MCP Status
        endpoint: /api/mcp
        method: GET
      - key: C
        label: Sync Brain
        endpoint: /api/brain/sync
        method: POST
      - key: D
        label: Open Dashboard
        type: link
        url: http://localhost:8084/docs
    mcp_servers:
      - name: Claude Code Settings
        connected: true
      - name: NeuroLinked Brain
        connected: true
```

- [ ] **Step 2: Update CSS — split Scout HQ row to add Ops Room**

In `frontend/index.html`, find and replace the Scout HQ CSS line:

Find:
```css
  #room-scout-hq      { grid-column: 1 / 3; grid-row: 3; border-color: #2ecc7155; }
```

Replace with:
```css
  #room-scout-hq      { grid-column: 1; grid-row: 3; border-color: #2ecc7155; }
  #room-ops-room      { grid-column: 2; grid-row: 3; border-color: #00bcd455; }
```

- [ ] **Step 3: Add Ops Room HTML**

In `frontend/index.html`, find the closing `</div>` after the Scout HQ room div:

Find:
```html
    <div class="room" id="room-scout-hq">
      <div class="room-label">SCOUT HQ</div>
      <div class="furniture" style="bottom:14px;right:20px">&#128302;</div>
      <div class="furniture" style="bottom:14px;right:52px">&#128225;</div>
      <div class="character" id="char-github-scout" data-agent="github-scout" style="left:50%;bottom:40%">&#129489;&#8205;&#128187;</div>
    </div>

  </div>
```

Replace with:
```html
    <div class="room" id="room-scout-hq">
      <div class="room-label">SCOUT HQ</div>
      <div class="furniture" style="bottom:14px;right:20px">&#128302;</div>
      <div class="furniture" style="bottom:14px;right:52px">&#128225;</div>
      <div class="character" id="char-github-scout" data-agent="github-scout" style="left:50%;bottom:40%">&#129489;&#8205;&#128187;</div>
    </div>

    <div class="room" id="room-ops-room">
      <div class="room-label">OPS ROOM</div>
      <div class="furniture" style="bottom:14px;right:20px">&#128268;</div>
      <div class="furniture" style="bottom:14px;right:52px">&#128187;</div>
      <div class="character" id="char-terminal-monitor" data-agent="terminal-monitor" style="left:40%;bottom:35%">&#128421;</div>
    </div>

  </div>
```

- [ ] **Step 4: Update minimap — split Scout HQ map cell**

Find:
```html
        <div class="map-room full-width" id="map-scout-hq">
          <div class="map-dot" id="dot-github-scout"></div>
          <span style="position:absolute;bottom:1px;left:2px;font-size:6px;color:#444">SCOUT</span>
        </div>
```

Replace with:
```html
        <div class="map-room" id="map-scout-hq">
          <div class="map-dot" id="dot-github-scout"></div>
          <span style="position:absolute;bottom:1px;left:2px;font-size:6px;color:#444">SCOUT</span>
        </div>
        <div class="map-room" id="map-ops-room">
          <div class="map-dot" id="dot-terminal-monitor"></div>
          <span style="position:absolute;bottom:1px;left:2px;font-size:6px;color:#444">OPS</span>
        </div>
```

- [ ] **Step 5: Add terminal-monitor drift config to JS**

Find:
```javascript
  'github-scout': { minX: 15, maxX: 80, minB: 20, maxB: 55 },
};
```

Replace with:
```javascript
  'github-scout':      { minX: 15, maxX: 80, minB: 20, maxB: 55 },
  'terminal-monitor':  { minX: 15, maxX: 75, minB: 20, maxB: 60 },
};
```

- [ ] **Step 6: Verify hub reloads and shows Ops Room**

The hub is running with `--reload`, so it picks up hub-config.yaml changes automatically. Open http://localhost:8090 and verify:
- Scout HQ now occupies only the left half of row 3
- Ops Room occupies the right half of row 3
- `🖥️` character appears in Ops Room (offline state since terminal-monitor isn't running yet)
- Minimap shows OPS cell alongside SCOUT cell

- [ ] **Step 7: Commit hub changes**

```powershell
cd C:\Users\hms16\Me\MyWords\Sandbox\projects\agent-hub
git add hub-config.yaml frontend\index.html
git commit -m "feat: add ops-room and terminal-monitor to agent hub"
cd C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor
```

---

### Task 8: README

**Files:**
- Create: `README.md`

- [ ] **Step 1: Write `README.md`**

```markdown
# Terminal Monitor

FastAPI agent (port 8084) that scans all listening localhost ports, checks their health, detects running MCP servers, and feeds snapshots to the NeuroLinked brain. Appears in the Agent Hub as `🖥️` in the Ops Room.

## Setup

```powershell
python -m venv .venv
.\.venv\Scripts\pip install -r requirements.txt
```

## Run

```powershell
.\.venv\Scripts\uvicorn termmon.main:app --port 8084 --reload
```

Open http://localhost:8084/docs for the interactive API.

## Test

```powershell
.\.venv\Scripts\python -m pytest tests/ -v
```

## Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/health` | Health check |
| GET | `/api/scan` | Full scan: ports + health + MCP |
| GET | `/api/mcp` | MCP server status only |
| GET | `/api/stats/port_count` | Count of listening ports |
| GET | `/api/stats/mcp_count` | Count of running MCP servers |
| GET | `/api/stats/process_count` | Count of unique processes |
| POST | `/api/brain/sync` | Push snapshot to NeuroLinked brain |
| POST | `/api/kill/{pid}` | *501 stub — v2* |
| POST | `/api/restart/{id}` | *501 stub — v2* |

## Agent Hub

Add to `agent-hub/hub-config.yaml` — see the `terminal-monitor` entry in that file. Hub room: `ops-room` (right half of row 3, sharing the row with Scout HQ).

## Brain sync

Auto-syncs every 60 seconds. Manual sync via `POST /api/brain/sync`. Brain at `http://localhost:8000`.

## MCP detection

Reads `~/.claude/settings.json` for configured MCP server names, then scans the Windows process list for matching executables. Stdio-based MCP servers (most Claude Code servers) show up via their node.exe or python.exe command lines.
```

- [ ] **Step 2: Run full test suite one final time**

```powershell
.\.venv\Scripts\python -m pytest tests/ -v
```

Expected: 18 PASSED, 0 FAILED.

- [ ] **Step 3: Final commit**

```powershell
git add README.md
git commit -m "docs: README with setup, endpoints, and hub integration notes"
```
