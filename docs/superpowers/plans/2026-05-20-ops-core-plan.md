# ops-core Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Make Terminal Monitor shippable with zero personal data leaks â€” config-driven personalization, persistent history, proactive alerts, and a first-run setup wizard.

**Architecture:** `config.yaml` (gitignored) drives all personal values. Pydantic config module exposes safe settings via `/api/config`. NDJSON files under `data/` persist history. Browser Notification API + 30s poller delivers proactive alerts. CLI and web wizards write config on first run.

**Tech Stack:** FastAPI, Pydantic v2, pyyaml (already in requirements.txt), psutil, stdlib json (NDJSON), Browser Notification API

---

## File Map

| Action | Path | Purpose |
|---|---|---|
| Create | `termmon/config.py` | Pydantic Settings model, get/write/reload_settings() |
| Create | `termmon/scanner/history.py` | NDJSON append/load, 500-entry rolling cap |
| Create | `termmon/scanner/alerts.py` | evaluate_alerts() against config thresholds |
| Create | `setup.py` | CLI first-run wizard (stdlib-friendly) |
| Create | `termmon/setup.html` | Web setup wizard self-contained HTML |
| Create | `config.example.yaml` | Buyer template with inline comments |
| Create | `tests/test_config.py` | Config module unit tests |
| Create | `tests/test_history.py` | History module unit tests |
| Create | `tests/test_alerts.py` | Alerts module unit tests |
| Create | `tests/test_setup.py` | CLI wizard unit tests |
| Modify | `termmon/brain.py` | URL from config, no hardcoded localhost:8000 |
| Modify | `termmon/main.py` | Config wiring, cached state, 5 new endpoints |
| Modify | `termmon/dashboard.html` | Remove MCP_PORT_MAP, history seed, alert poller |
| Modify | `termmon/proc_desc.json` | Remove duplicate Obsidian.exe (system section) |
| Modify | `.gitignore` | Add config.yaml, data/, model artifacts |

---

### Task 1: Config module

**Files:**
- Create: `termmon/config.py`
- Create: `tests/test_config.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_config.py
import textwrap
from unittest.mock import patch


def test_defaults_when_no_config_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    import termmon.config as cfg_mod
    cfg_mod._settings = None
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        s = cfg_mod._load()
    assert s.dashboard.title == "Ops Dashboard"
    assert s.brain.enabled is False
    assert s.alerts.cpu_threshold == 80
    assert s.services == []


def test_loads_custom_values(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(textwrap.dedent("""\
        dashboard:
          title: "My Ops"
          default_model: "llama3.2:3b"
          training_threshold: 50
        brain:
          enabled: true
          url: "http://localhost:9000"
        services:
          - name: "my-agent"
            port: 8090
        alerts:
          cpu_threshold: 70
          ram_threshold: 75
          offline_notify: false
    """), encoding="utf-8")
    import termmon.config as cfg_mod
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        s = cfg_mod._load()
    assert s.dashboard.title == "My Ops"
    assert s.brain.enabled is True
    assert s.brain.url == "http://localhost:9000"
    assert s.services[0].name == "my-agent"
    assert s.services[0].port == 8090
    assert s.alerts.cpu_threshold == 70
    assert s.alerts.offline_notify is False


def test_write_and_reload(tmp_path):
    import yaml
    import termmon.config as cfg_mod
    from termmon.config import Settings, DashboardConfig
    config_path = tmp_path / "config.yaml"
    s = Settings(dashboard=DashboardConfig(title="Written"))
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        cfg_mod.write_settings(s)
        loaded = yaml.safe_load(config_path.read_text())
    assert loaded["dashboard"]["title"] == "Written"


def test_missing_sections_get_defaults(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("dashboard:\n  title: Partial\n", encoding="utf-8")
    import termmon.config as cfg_mod
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        s = cfg_mod._load()
    assert s.alerts.cpu_threshold == 80
    assert s.brain.enabled is False
    assert s.services == []
```

- [x] **Step 2: Run test to verify it fails**

```powershell
.venv\Scripts\python -m pytest tests/test_config.py -v
```
Expected: `ImportError` â€” `termmon.config` not found.

- [x] **Step 3: Implement `termmon/config.py`**

```python
from __future__ import annotations

import pathlib
from typing import Optional

import yaml
from pydantic import BaseModel, Field

_CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.yaml"


class DashboardConfig(BaseModel):
    title: str = "Ops Dashboard"
    default_model: str = "ops-brain"
    training_threshold: int = 100


class BrainConfig(BaseModel):
    enabled: bool = False
    url: str = "http://localhost:8000"


class ServiceConfig(BaseModel):
    name: str
    port: int
    start_command: Optional[str] = None


class AlertsConfig(BaseModel):
    cpu_threshold: int = 80
    ram_threshold: int = 80
    gpu_temp_threshold: int = 80
    offline_notify: bool = True


class Settings(BaseModel):
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    brain: BrainConfig = Field(default_factory=BrainConfig)
    services: list[ServiceConfig] = Field(default_factory=list)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)


_settings: Optional[Settings] = None


def _load() -> Settings:
    if not _CONFIG_PATH.exists():
        return Settings()
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8")) or {}
    return Settings.model_validate(raw)


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = _load()
    return _settings


def reload_settings() -> Settings:
    global _settings
    _settings = _load()
    return _settings


def write_settings(settings: Settings) -> None:
    data = settings.model_dump()
    _CONFIG_PATH.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    reload_settings()
```

- [x] **Step 4: Run tests to verify they pass**

```powershell
.venv\Scripts\python -m pytest tests/test_config.py -v
```
Expected: 4 PASSED.

- [x] **Step 5: Run full suite to check for regressions**

```powershell
.venv\Scripts\python -m pytest -v
```
Expected: All existing tests pass.

- [x] **Step 6: Commit**

```powershell
git add termmon/config.py tests/test_config.py
git commit -m "feat: add Pydantic config module with get/write/reload_settings"
```

---

### Task 2: Security fixes

**Files:**
- Modify: `termmon/brain.py`
- Modify: `termmon/proc_desc.json`
- Modify: `.gitignore`

- [x] **Step 1: Replace `termmon/brain.py`**

```python
from __future__ import annotations

import logging

import httpx

from termmon.config import get_settings

logger = logging.getLogger(__name__)


async def sync(scan_result: dict) -> None:
    settings = get_settings()
    brain_url = settings.brain.url
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
                f"{brain_url}/api/claude/remember",
                json={
                    "text": text,
                    "source": "terminal-monitor",
                    "tags": ["terminal-monitor", "system-state", "ports", "mcp-servers"],
                },
                timeout=5.0,
            )
            await client.post(
                f"{brain_url}/api/claude/observe",
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

- [x] **Step 2: Remove duplicate Obsidian.exe from `termmon/proc_desc.json`**

In the `"system"` section (near line 220), find and remove this line:

```json
    "Obsidian.exe": "Obsidian â€” Markdown note-taking app. Runs a local server on port 27123 for plugin and MCP access.",
```

Keep only the entry in the `"utilities"` section (line 172). The `"system"` section should flow directly from `"node.exe"` to `"chrome.exe"`.

- [x] **Step 3: Append to `.gitignore`**

```
# Personal config (never ships to buyers)
config.yaml

# History data (personal machine state)
data/

# Model artifacts
models/Modelfile
models/training_seed.jsonl
models/Modelfile.generated
```

- [x] **Step 4: Run full test suite**

```powershell
.venv\Scripts\python -m pytest -v
```
Expected: All pass. `test_process_descriptions_returns_dict` still passes â€” `Dolphin.exe` is in the gaming section, untouched.

- [x] **Step 5: Commit**

```powershell
git add termmon/brain.py termmon/proc_desc.json .gitignore
git commit -m "fix: read brain URL from config, remove hardcoded personal refs, update gitignore"
```

---

### Task 3: `/api/config` endpoint + main.py wiring + dashboard MCP_PORT_MAP

**Files:**
- Modify: `termmon/main.py`
- Modify: `termmon/dashboard.html`
- Modify: `tests/test_api.py`

- [x] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
def test_api_config_safe_fields():
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "title" in data
    assert "default_model" in data
    assert "services" in data
    assert "alerts" in data
    assert "brain_enabled" in data
    # brain URL must NOT be exposed to frontend
    assert "url" not in data
    assert "brain_url" not in data
```

- [x] **Step 2: Run test to verify it fails**

```powershell
.venv\Scripts\python -m pytest tests/test_api.py::test_api_config_safe_fields -v
```
Expected: FAIL â€” 404 Not Found.

- [x] **Step 3: Update `termmon/main.py`** â€” three changes:

**3a.** Add imports at top of file:
```python
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from termmon.config import get_settings, write_settings
```
(Replace the existing `from fastapi.responses import FileResponse, JSONResponse` line.)

**3b.** Replace the `lifespan` function so brain loop is conditional:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    tasks = []
    if settings.brain.enabled:
        tasks.append(asyncio.create_task(_brain_loop()))
    yield
    for t in tasks:
        t.cancel()
```

**3c.** Add `/api/config` endpoint (before the `/dashboard` route):
```python
@app.get("/api/config")
async def get_config():
    settings = get_settings()
    return {
        "title": settings.dashboard.title,
        "default_model": settings.dashboard.default_model,
        "training_threshold": settings.dashboard.training_threshold,
        "services": [s.model_dump() for s in settings.services],
        "alerts": settings.alerts.model_dump(),
        "brain_enabled": settings.brain.enabled,
    }
```

**3d.** Add `_CONFIG_PATH` constant and update `/dashboard` route to redirect on missing config:
```python
_CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.yaml"

@app.get("/dashboard")
async def dashboard():
    if not _CONFIG_PATH.exists():
        return RedirectResponse("/setup", status_code=303)
    return FileResponse(_DASHBOARD, media_type="text/html")
```

- [x] **Step 4: Run new tests to verify they pass**

```powershell
.venv\Scripts\python -m pytest tests/test_api.py::test_api_config_safe_fields -v
```
Expected: PASSED.

- [x] **Step 5: Fix `termmon/dashboard.html` â€” replace MCP_PORT_MAP**

Find line 249:
```javascript
var MCP_PORT_MAP = { 'neurolinked-brain': 8000, 'obsidian': 27123 };
```

Replace with:
```javascript
var _config = { title: 'Ops Dashboard', default_model: 'ops-brain', training_threshold: 100, services: [], alerts: {} };
var _svcPortMap = {};

async function _loadConfig() {
  try {
    var r = await fetch('/api/config');
    if (!r.ok) return;
    _config = await r.json();
    _svcPortMap = {};
    (_config.services || []).forEach(function(s) { _svcPortMap[s.name] = s.port; });
    if (_config.title) document.title = _config.title;
    if (_config.default_model && !localStorage.getItem('ops-model')) {
      _selectedModel = _config.default_model;
    }
  } catch(_) {}
}
```

Find the line (around line 557):
```javascript
var svcPort = MCP_PORT_MAP[m.name];
```

Replace with:
```javascript
var svcPort = _svcPortMap[m.name];
```

Find the bottom init block (the last few lines of `<script>`):
```javascript
doScan();
setInterval(fetchScan, 5000);
```

Replace the entire bottom block with:
```javascript
_loadConfig();
doScan();
setInterval(fetchScan, 5000);
setInterval(fetchResources, 5000);
setInterval(tickUpdated, 1000);
```

- [x] **Step 6: Run full suite**

```powershell
.venv\Scripts\python -m pytest -v
```
Expected: All tests pass.

- [x] **Step 7: Commit**

```powershell
git add termmon/main.py termmon/dashboard.html tests/test_api.py
git commit -m "feat: add /api/config, conditional brain loop, load service map from frontend"
```

---

### Task 4: History module

**Files:**
- Create: `termmon/scanner/history.py`
- Create: `tests/test_history.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_history.py
import json
from unittest.mock import patch

import termmon.scanner.history as hist_mod


def _patched(tmp_path):
    return [
        patch.object(hist_mod, "_DATA_DIR", tmp_path),
        patch.object(hist_mod, "_SCAN_PATH", tmp_path / "scan_history.jsonl"),
        patch.object(hist_mod, "_RESOURCE_PATH", tmp_path / "resource_history.jsonl"),
    ]


def test_append_scan_creates_file(tmp_path):
    with _patched(tmp_path)[0], _patched(tmp_path)[1], _patched(tmp_path)[2]:
        hist_mod.append_scan({"scanned_at": "t1", "summary": {}})
        lines = (tmp_path / "scan_history.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["scanned_at"] == "t1"


def test_load_returns_last_n(tmp_path):
    patches = _patched(tmp_path)
    with patches[0], patches[1], patches[2]:
        for i in range(10):
            hist_mod.append_scan({"scanned_at": f"t{i}"})
        result = hist_mod.load_scan_history(n=3)
    assert len(result) == 3
    assert result[0]["scanned_at"] == "t7"
    assert result[-1]["scanned_at"] == "t9"


def test_rolling_cap_drops_oldest(tmp_path):
    patches = _patched(tmp_path)
    with patches[0], patches[1], patches[2]:
        for i in range(510):
            hist_mod.append_scan({"scanned_at": f"t{i}"})
        lines = (tmp_path / "scan_history.jsonl").read_text().strip().splitlines()
    assert len(lines) == 500
    assert json.loads(lines[0])["scanned_at"] == "t10"


def test_append_resource_and_load(tmp_path):
    patches = _patched(tmp_path)
    with patches[0], patches[1], patches[2]:
        hist_mod.append_resource({"cpu_percent": 42.0})
        result = hist_mod.load_resource_history(n=5)
    assert len(result) == 1
    assert result[0]["cpu_percent"] == 42.0


def test_empty_returns_empty_list(tmp_path):
    patches = _patched(tmp_path)
    with patches[0], patches[1], patches[2]:
        result = hist_mod.load_scan_history()
    assert result == []
```

- [x] **Step 2: Run tests to verify they fail**

```powershell
.venv\Scripts\python -m pytest tests/test_history.py -v
```
Expected: `ImportError` â€” `termmon.scanner.history` not found.

- [x] **Step 3: Implement `termmon/scanner/history.py`**

```python
from __future__ import annotations

import json
import pathlib

_DATA_DIR = pathlib.Path(__file__).parent.parent.parent / "data"
_SCAN_PATH = _DATA_DIR / "scan_history.jsonl"
_RESOURCE_PATH = _DATA_DIR / "resource_history.jsonl"
_CAP = 500


def _append(path: pathlib.Path, entry: dict) -> None:
    _DATA_DIR.mkdir(exist_ok=True)
    lines: list[str] = []
    if path.exists():
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    lines.append(json.dumps(entry, ensure_ascii=False))
    if len(lines) > _CAP:
        lines = lines[-_CAP:]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _load(path: pathlib.Path, n: int) -> list[dict]:
    if not path.exists():
        return []
    lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
    return [json.loads(ln) for ln in lines[-n:]]


def append_scan(entry: dict) -> None:
    _append(_SCAN_PATH, entry)


def append_resource(entry: dict) -> None:
    _append(_RESOURCE_PATH, entry)


def load_scan_history(n: int = 30) -> list[dict]:
    return _load(_SCAN_PATH, n)


def load_resource_history(n: int = 30) -> list[dict]:
    return _load(_RESOURCE_PATH, n)
```

- [x] **Step 4: Run tests to verify they pass**

```powershell
.venv\Scripts\python -m pytest tests/test_history.py -v
```
Expected: 5 PASSED.

- [x] **Step 5: Run full suite**

```powershell
.venv\Scripts\python -m pytest -v
```
Expected: All pass.

- [x] **Step 6: Commit**

```powershell
git add termmon/scanner/history.py tests/test_history.py
git commit -m "feat: add NDJSON history module with 500-entry rolling cap"
```

---

### Task 5: `/api/history` endpoint + history wiring

**Files:**
- Modify: `termmon/main.py`
- Modify: `tests/test_api.py`

- [x] **Step 1: Write failing test**

Add to `tests/test_api.py`:

```python
def test_api_history_structure():
    r = client.get("/api/history")
    assert r.status_code == 200
    data = r.json()
    assert "scan" in data
    assert "resources" in data
    assert isinstance(data["scan"], list)
    assert isinstance(data["resources"], list)
```

- [x] **Step 2: Run test to verify it fails**

```powershell
.venv\Scripts\python -m pytest tests/test_api.py::test_api_history_structure -v
```
Expected: FAIL â€” 404.

- [x] **Step 3: Update `termmon/main.py`**

Add imports after the scanner imports:
```python
from termmon.scanner.history import (
    append_scan, append_resource,
    load_scan_history, load_resource_history,
)
```

Add global cached state (after `_desc_cache` declaration around line 39):
```python
_last_scan: dict | None = None
_last_resources: dict | None = None
```

Update `_full_scan()` to cache and persist â€” add two lines at the end before `return`:
```python
async def _full_scan() -> dict:
    global _last_scan
    ports = scan_ports()
    ports = await check_health(ports)
    mcps = scan_mcp()
    mcp_count = sum(1 for m in mcps if m["running"])
    process_names = {p["process"] for p in ports if p["process"] != "unknown"}
    port_pids = {p["pid"] for p in ports if p["pid"]}
    background = scan_background_processes(exclude_pids=port_pids)
    result = {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "ports": ports,
        "background_processes": background,
        "mcp_servers": mcps,
        "summary": {
            "port_count": len(ports),
            "mcp_count": mcp_count,
            "process_count": len(process_names),
        },
    }
    _last_scan = result
    append_scan(result)
    return result
```

Update `get_resources_endpoint()`:
```python
@app.get("/api/resources")
async def get_resources_endpoint():
    global _last_resources
    result = get_resources()
    _last_resources = result
    append_resource(result)
    return result
```

Add `/api/history` endpoint:
```python
@app.get("/api/history")
async def get_history():
    return {
        "scan": load_scan_history(n=30),
        "resources": load_resource_history(n=30),
    }
```

- [x] **Step 4: Run tests**

```powershell
.venv\Scripts\python -m pytest tests/test_api.py -v
```
Expected: All pass including `test_api_history_structure`.

- [x] **Step 5: Commit**

```powershell
git add termmon/main.py tests/test_api.py
git commit -m "feat: add /api/history, cache scan+resource state, wire history appends"
```

---

### Task 6: Frontend history seed

**Files:**
- Modify: `termmon/dashboard.html`

- [x] **Step 1: Add `_seedHistory()` function**

Find the lines:
```javascript
var _scanHistory = [];
var _resHistory  = [];
```

Immediately after them, insert:
```javascript
async function _seedHistory() {
  try {
    var r = await fetch('/api/history');
    if (!r.ok) return;
    var data = await r.json();
    _scanHistory = (data.scan || []).map(function(s) {
      return {
        ts: new Date(s.scanned_at).getTime(),
        portCount: (s.ports || []).length,
        procCount: (s.summary || {}).process_count || 0,
        mcpOnline: (s.summary || {}).mcp_count || 0,
        mcpTotal: (s.mcp_servers || []).length,
        procs: Array.from(new Set((s.ports || []).map(function(p) { return p.process; }))),
      };
    });
    _resHistory = (data.resources || []).map(function(res) {
      return {
        ts: Date.now(),
        cpu: res.cpu_percent || 0,
        ramPct: (res.memory || {}).percent || 0,
        ramRaw: res.memory || null,
        diskPct: (res.disk || {}).percent || 0,
        gpuUtil: res.gpus && res.gpus.length ? (res.gpus[0].util_pct || undefined) : undefined,
      };
    });
  } catch(_) {}
}
```

- [x] **Step 2: Call `_seedHistory()` at init**

Find the bottom init block (the `_loadConfig(); doScan(); ...` block from Task 3) and add `_seedHistory()` between `_loadConfig()` and `doScan()`:

```javascript
_loadConfig();
_seedHistory();
doScan();
setInterval(fetchScan, 5000);
setInterval(fetchResources, 5000);
setInterval(tickUpdated, 1000);
```

- [x] **Step 3: Manual smoke test**

```powershell
.venv\Scripts\python -m uvicorn termmon.main:app --port 8084
```

Open `http://localhost:8084/dashboard`. Click HISTORY and ENERGY tabs immediately before the 5s scan fires. If `data/scan_history.jsonl` has entries, they show up; otherwise both tabs show the "Collectingâ€¦" placeholder â€” which is correct for a clean install.

- [x] **Step 4: Commit**

```powershell
git add termmon/dashboard.html
git commit -m "feat: seed scan+resource history from /api/history on page load"
```

---

### Task 7: Alerts module

**Files:**
- Create: `termmon/scanner/alerts.py`
- Create: `tests/test_alerts.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_alerts.py
from termmon.config import Settings, AlertsConfig, ServiceConfig
from termmon.scanner.alerts import evaluate_alerts


def _settings(**kw) -> Settings:
    return Settings(alerts=AlertsConfig(**kw))


def _scan(ports=None) -> dict:
    return {"ports": ports or [], "mcp_servers": [], "summary": {}}


def _res(cpu=0.0, ram=0.0, gpu_temp=None) -> dict:
    r: dict = {"cpu_percent": cpu, "memory": {"percent": ram}, "disk": {"percent": 5.0}}
    if gpu_temp is not None:
        r["gpu_temp_c"] = gpu_temp
    return r


def test_no_alerts_below_thresholds():
    alerts = evaluate_alerts(_scan(), _res(cpu=50.0, ram=60.0), _settings())
    assert alerts == []


def test_cpu_triggers_alert():
    alerts = evaluate_alerts(_scan(), _res(cpu=85.0), _settings(cpu_threshold=80))
    assert any("cpu" in a["id"] for a in alerts)


def test_ram_triggers_alert_with_value_in_message():
    alerts = evaluate_alerts(_scan(), _res(ram=87.0), _settings(ram_threshold=80))
    msg = next(a["message"] for a in alerts if "ram" in a["id"])
    assert "87" in msg


def test_service_offline_when_notify_enabled():
    svc = ServiceConfig(name="my-agent", port=8090)
    s = Settings(alerts=AlertsConfig(offline_notify=True), services=[svc])
    alerts = evaluate_alerts(_scan(ports=[]), _res(), s)
    assert any(a["id"] == "service_offline_my-agent" for a in alerts)


def test_offline_notify_false_skips_service_alerts():
    svc = ServiceConfig(name="my-agent", port=8090)
    s = Settings(alerts=AlertsConfig(offline_notify=False), services=[svc])
    alerts = evaluate_alerts(_scan(ports=[]), _res(), s)
    assert not any("service_offline" in a["id"] for a in alerts)


def test_gpu_temp_triggers_alert():
    alerts = evaluate_alerts(_scan(), _res(gpu_temp=85.0), _settings(gpu_temp_threshold=80))
    assert any("gpu_temp" in a["id"] for a in alerts)


def test_alert_ids_deterministic():
    s = _settings(cpu_threshold=80)
    r = _res(cpu=85.0)
    assert [a["id"] for a in evaluate_alerts(_scan(), r, s)] == \
           [a["id"] for a in evaluate_alerts(_scan(), r, s)]


def test_service_healthy_port_no_alert():
    svc = ServiceConfig(name="my-agent", port=8090)
    s = Settings(alerts=AlertsConfig(offline_notify=True), services=[svc])
    port_entry = {"port": 8090, "process": "python.exe", "healthy": True,
                  "pid": 1, "label": "my-agent", "memory_mb": 50.0}
    alerts = evaluate_alerts(_scan(ports=[port_entry]), _res(), s)
    assert not any("service_offline" in a["id"] for a in alerts)
```

- [x] **Step 2: Run tests to verify they fail**

```powershell
.venv\Scripts\python -m pytest tests/test_alerts.py -v
```
Expected: `ImportError` â€” `termmon.scanner.alerts` not found.

- [x] **Step 3: Implement `termmon/scanner/alerts.py`**

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from termmon.config import Settings


def evaluate_alerts(scan: dict, resources: dict, settings: "Settings") -> list[dict]:
    alerts: list[dict] = []
    cfg = settings.alerts

    cpu = resources.get("cpu_percent", 0.0)
    if cpu >= cfg.cpu_threshold:
        alerts.append({
            "id": f"cpu_{int(cpu)}",
            "severity": "high" if cpu >= 90 else "warn",
            "message": f"CPU at {cpu:.1f}%",
        })

    ram = (resources.get("memory") or {}).get("percent", 0.0)
    if ram >= cfg.ram_threshold:
        alerts.append({
            "id": f"ram_{int(ram)}",
            "severity": "high" if ram >= 90 else "warn",
            "message": f"RAM at {ram:.1f}%",
        })

    gpu_temp = resources.get("gpu_temp_c")
    if gpu_temp is not None and gpu_temp >= cfg.gpu_temp_threshold:
        alerts.append({
            "id": f"gpu_temp_{int(gpu_temp)}",
            "severity": "high" if gpu_temp >= 90 else "warn",
            "message": f"GPU temp at {gpu_temp:.0f}Â°C",
        })

    if cfg.offline_notify:
        healthy_ports = {
            p["port"]
            for p in scan.get("ports", [])
            if p.get("healthy", False)
        }
        for svc in settings.services:
            if svc.port not in healthy_ports:
                slug = svc.name.lower().replace(" ", "-")
                alerts.append({
                    "id": f"service_offline_{slug}",
                    "severity": "high",
                    "message": f"{svc.name} offline",
                })

    return alerts
```

- [x] **Step 4: Run tests to verify they pass**

```powershell
.venv\Scripts\python -m pytest tests/test_alerts.py -v
```
Expected: 8 PASSED.

- [x] **Step 5: Run full suite**

```powershell
.venv\Scripts\python -m pytest -v
```
Expected: All pass.

- [x] **Step 6: Commit**

```powershell
git add termmon/scanner/alerts.py tests/test_alerts.py
git commit -m "feat: add alerts evaluator against config thresholds"
```

---

### Task 8: `/api/alerts/current` endpoint

**Files:**
- Modify: `termmon/main.py`
- Modify: `tests/test_api.py`

- [x] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
def test_api_alerts_empty_when_no_cached_data():
    import termmon.main as main_mod
    orig_scan, orig_res = main_mod._last_scan, main_mod._last_resources
    main_mod._last_scan = None
    main_mod._last_resources = None
    try:
        r = client.get("/api/alerts/current")
        assert r.status_code == 200
        assert r.json()["alerts"] == []
    finally:
        main_mod._last_scan = orig_scan
        main_mod._last_resources = orig_res


def test_api_alerts_returns_list_when_data_present():
    import termmon.main as main_mod
    main_mod._last_scan = {"ports": [], "mcp_servers": [], "summary": {}}
    main_mod._last_resources = {"cpu_percent": 10.0, "memory": {"percent": 20.0}, "disk": {"percent": 5.0}}
    try:
        r = client.get("/api/alerts/current")
        assert r.status_code == 200
        assert isinstance(r.json()["alerts"], list)
    finally:
        main_mod._last_scan = None
        main_mod._last_resources = None
```

- [x] **Step 2: Run tests to verify they fail**

```powershell
.venv\Scripts\python -m pytest tests/test_api.py::test_api_alerts_empty_when_no_cached_data tests/test_api.py::test_api_alerts_returns_list_when_data_present -v
```
Expected: FAIL â€” 404.

- [x] **Step 3: Update `termmon/main.py`**

Add import:
```python
from termmon.scanner.alerts import evaluate_alerts
```

Add endpoint:
```python
@app.get("/api/alerts/current")
async def get_current_alerts():
    if _last_scan is None or _last_resources is None:
        return {"alerts": []}
    settings = get_settings()
    return {"alerts": evaluate_alerts(_last_scan, _last_resources, settings)}
```

- [x] **Step 4: Run tests**

```powershell
.venv\Scripts\python -m pytest tests/test_api.py -v
```
Expected: All pass.

- [x] **Step 5: Commit**

```powershell
git add termmon/main.py tests/test_api.py
git commit -m "feat: add /api/alerts/current using cached scan+resource state"
```

---

### Task 9: Frontend alert poller

**Files:**
- Modify: `termmon/dashboard.html`

- [x] **Step 1: Add two functions before the bottom init block**

Find the section with `// â”€â”€ Training status â”€â”€` (around line 1047). After the `loadModels` function, add:

```javascript
// â”€â”€ Alert poller â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
var _activeAlertIds = new Set();

function _requestNotifPermission() {
  if (localStorage.getItem('notif_denied') === '1') return;
  if (!('Notification' in window)) return;
  if (Notification.permission === 'default') {
    Notification.requestPermission().then(function(perm) {
      if (perm === 'denied') localStorage.setItem('notif_denied', '1');
    });
  }
}

function _startAlertPoller() {
  setInterval(async function() {
    try {
      var r = await fetch('/api/alerts/current');
      if (!r.ok) return;
      var data = await r.json();
      var incoming = data.alerts || [];
      var currentIds = new Set(incoming.map(function(a) { return a.id; }));
      if (Notification.permission === 'granted') {
        incoming.forEach(function(a) {
          if (!_activeAlertIds.has(a.id)) {
            new Notification('Terminal Monitor', { body: a.message });
          }
        });
      }
      _activeAlertIds = currentIds;
    } catch(_) {}
  }, 30000);
}
```

- [x] **Step 2: Update the bottom init block**

Find (the block from Tasks 3 + 6):
```javascript
_loadConfig();
_seedHistory();
doScan();
```

Replace with:
```javascript
_loadConfig();
_seedHistory();
_requestNotifPermission();
_startAlertPoller();
doScan();
```

- [x] **Step 3: Manual smoke test**

Start server, open dashboard. Browser prompts for notification permission. In DevTools console:

```javascript
fetch('/api/alerts/current').then(r => r.json()).then(console.log)
```

Expected output: `{ alerts: [] }` (or active alerts if any threshold is exceeded).

- [x] **Step 4: Commit**

```powershell
git add termmon/dashboard.html
git commit -m "feat: browser notification poller for proactive alerts (30s interval)"
```

---

### Task 10: CLI setup wizard

**Files:**
- Create: `setup.py`
- Create: `tests/test_setup.py`

- [x] **Step 1: Write failing tests**

```python
# tests/test_setup.py
import pathlib
import yaml
from unittest.mock import patch


def test_build_config_structure():
    import setup as setup_mod
    cfg = setup_mod._build_config(
        title="Test Ops", default_model="llama3.2:3b", training_threshold=50,
        brain_enabled=False, brain_url="http://localhost:8000",
        services=[{"name": "my-agent", "port": 8090}],
        cpu_threshold=70, ram_threshold=75, gpu_temp_threshold=85, offline_notify=True,
    )
    assert cfg["dashboard"]["title"] == "Test Ops"
    assert cfg["brain"]["enabled"] is False
    assert cfg["services"][0]["port"] == 8090
    assert cfg["alerts"]["cpu_threshold"] == 70


def test_write_config_writes_yaml(tmp_path):
    import setup as setup_mod
    out = tmp_path / "config.yaml"
    cfg = setup_mod._build_config(
        title="X", default_model="m", training_threshold=100,
        brain_enabled=False, brain_url="http://localhost:8000",
        services=[], cpu_threshold=80, ram_threshold=80, gpu_temp_threshold=80, offline_notify=True,
    )
    setup_mod._write_config(cfg, out)
    loaded = yaml.safe_load(out.read_text())
    assert loaded["dashboard"]["title"] == "X"


def test_write_config_overwrites_existing(tmp_path):
    import setup as setup_mod
    out = tmp_path / "config.yaml"
    out.write_text("old: data\n")
    cfg = setup_mod._build_config(
        title="New", default_model="m", training_threshold=100,
        brain_enabled=False, brain_url="http://localhost:8000",
        services=[], cpu_threshold=80, ram_threshold=80, gpu_temp_threshold=80, offline_notify=True,
    )
    setup_mod._write_config(cfg, out)
    loaded = yaml.safe_load(out.read_text())
    assert "old" not in loaded
    assert loaded["dashboard"]["title"] == "New"
```

- [x] **Step 2: Run tests to verify they fail**

```powershell
.venv\Scripts\python -m pytest tests/test_setup.py -v
```
Expected: `ModuleNotFoundError` â€” `setup` not found.

- [x] **Step 3: Implement `setup.py`**

```python
#!/usr/bin/env python
"""First-run setup wizard â€” writes config.yaml. Run: python setup.py"""
from __future__ import annotations

import pathlib
import sys

_CONFIG_PATH = pathlib.Path(__file__).parent / "config.yaml"


def _build_config(
    title: str, default_model: str, training_threshold: int,
    brain_enabled: bool, brain_url: str, services: list[dict],
    cpu_threshold: int, ram_threshold: int, gpu_temp_threshold: int,
    offline_notify: bool,
) -> dict:
    return {
        "dashboard": {
            "title": title,
            "default_model": default_model,
            "training_threshold": training_threshold,
        },
        "brain": {"enabled": brain_enabled, "url": brain_url},
        "services": services,
        "alerts": {
            "cpu_threshold": cpu_threshold,
            "ram_threshold": ram_threshold,
            "gpu_temp_threshold": gpu_temp_threshold,
            "offline_notify": offline_notify,
        },
    }


def _write_config(cfg: dict, path: pathlib.Path) -> None:
    try:
        import yaml
        text = yaml.dump(cfg, default_flow_style=False, allow_unicode=True)
    except ImportError:
        lines = [
            "dashboard:",
            f'  title: "{cfg["dashboard"]["title"]}"',
            f'  default_model: "{cfg["dashboard"]["default_model"]}"',
            f'  training_threshold: {cfg["dashboard"]["training_threshold"]}',
            "brain:",
            f'  enabled: {str(cfg["brain"]["enabled"]).lower()}',
            f'  url: "{cfg["brain"]["url"]}"',
            "services: []",
            "alerts:",
            f'  cpu_threshold: {cfg["alerts"]["cpu_threshold"]}',
            f'  ram_threshold: {cfg["alerts"]["ram_threshold"]}',
            f'  gpu_temp_threshold: {cfg["alerts"]["gpu_temp_threshold"]}',
            f'  offline_notify: {str(cfg["alerts"]["offline_notify"]).lower()}',
        ]
        text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")


def _ask(prompt: str, default: str) -> str:
    val = input(f"{prompt} [{default}]: ").strip()
    return val if val else default


def _ask_int(prompt: str, default: int) -> int:
    while True:
        val = input(f"{prompt} [{default}]: ").strip()
        if not val:
            return default
        try:
            return int(val)
        except ValueError:
            print("  Enter a whole number.")


def _ask_bool(prompt: str, default: bool) -> bool:
    val = input(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def _collect_services() -> list[dict]:
    services: list[dict] = []
    print("\nServices to monitor (blank name to finish):")
    while True:
        name = input("  Name: ").strip()
        if not name:
            break
        port = _ask_int("  Port", 8080)
        cmd = input("  Start command (optional): ").strip() or None
        entry: dict = {"name": name, "port": port}
        if cmd:
            entry["start_command"] = cmd
        services.append(entry)
    return services


def main(config_path: pathlib.Path = _CONFIG_PATH) -> None:
    print("=" * 50)
    print("  Terminal Monitor â€” First-Run Setup")
    print("=" * 50)

    if config_path.exists():
        if not _ask_bool("config.yaml exists. Overwrite?", False):
            print("Cancelled â€” existing config kept.")
            sys.exit(0)

    print()
    title = _ask("Dashboard title", "Ops Dashboard")
    model = _ask("Default Ollama model", "ops-brain")
    threshold = _ask_int("Training pair threshold", 100)

    print()
    brain = _ask_bool("Enable brain sync?", False)
    brain_url = "http://localhost:8000"
    if brain:
        brain_url = _ask("Brain URL", "http://localhost:8000")

    services = _collect_services()

    print("\nAlert thresholds:")
    cpu_t = _ask_int("  CPU %", 80)
    ram_t = _ask_int("  RAM %", 80)
    gpu_t = _ask_int("  GPU temp degC", 80)
    offline_n = _ask_bool("  Notify when services go offline?", True)

    cfg = _build_config(
        title=title, default_model=model, training_threshold=threshold,
        brain_enabled=brain, brain_url=brain_url, services=services,
        cpu_threshold=cpu_t, ram_threshold=ram_t, gpu_temp_threshold=gpu_t,
        offline_notify=offline_n,
    )
    _write_config(cfg, config_path)

    print(f"\n  Written to {config_path}")
    print("  Start: python -m uvicorn termmon.main:app --port 8084")
    print("  Open:  http://localhost:8084/dashboard")


if __name__ == "__main__":
    main()
```

- [x] **Step 4: Run tests to verify they pass**

```powershell
.venv\Scripts\python -m pytest tests/test_setup.py -v
```
Expected: 3 PASSED.

- [x] **Step 5: Run full suite**

```powershell
.venv\Scripts\python -m pytest -v
```
Expected: All pass.

- [x] **Step 6: Commit**

```powershell
git add setup.py tests/test_setup.py
git commit -m "feat: add CLI first-run setup wizard (stdlib-friendly)"
```

---

### Task 11: Web setup wizard + config.example.yaml + final clean build

**Files:**
- Create: `termmon/setup.html`
- Create: `config.example.yaml`
- Modify: `termmon/main.py`
- Modify: `tests/test_api.py`

- [x] **Step 1: Write failing tests**

Add to `tests/test_api.py`:

```python
def test_setup_get_returns_html():
    r = client.get("/setup")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_setup_post_saves_config(tmp_path):
    import termmon.main as main_mod
    import termmon.config as cfg_mod
    config_path = tmp_path / "config.yaml"
    with patch.object(main_mod, "_CONFIG_PATH", config_path), \
         patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        cfg_mod._settings = None
        r = client.post("/api/setup", json={
            "title": "Test Dashboard",
            "default_model": "llama3.2:3b",
            "training_threshold": 50,
            "brain_enabled": False,
            "brain_url": "http://localhost:8000",
            "services": [{"name": "my-agent", "port": 8090}],
            "cpu_threshold": 70,
            "ram_threshold": 75,
            "gpu_temp_threshold": 85,
            "offline_notify": True,
        })
    assert r.status_code == 200
    assert r.json()["saved"] is True
```

- [x] **Step 2: Run tests to verify they fail**

```powershell
.venv\Scripts\python -m pytest tests/test_api.py::test_setup_get_returns_html tests/test_api.py::test_setup_post_saves_config -v
```
Expected: FAIL â€” 404.

- [x] **Step 3: Create `termmon/setup.html`**

```html
<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Terminal Monitor â€” Setup</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{background:#0d0d0d;color:#c8c8c8;font-family:'Courier New',monospace;font-size:13px;padding:40px 20px}
h1{color:#00ff41;font-size:16px;margin-bottom:24px;letter-spacing:2px}
h2{color:#888;font-size:11px;margin:24px 0 8px;text-transform:uppercase;letter-spacing:1px}
.field{margin-bottom:12px}
label{display:block;margin-bottom:4px;color:#888;font-size:11px}
input[type=text],input[type=number],input[type=url]{width:100%;max-width:400px;background:#111;border:1px solid #333;color:#c8c8c8;font-family:inherit;font-size:13px;padding:6px 8px;border-radius:2px}
input:focus{outline:none;border-color:#00ff41}
.toggle{display:flex;align-items:center;gap:8px}
.toggle input[type=checkbox]{width:14px;height:14px;accent-color:#00ff41}
#svc-list{margin:8px 0}
.svc-row{display:flex;gap:8px;margin-bottom:6px;align-items:center}
.svc-row input{flex:1;max-width:none}
.svc-row button{background:#1a1a1a;border:1px solid #333;color:#888;cursor:pointer;font-size:11px;padding:4px 8px;border-radius:2px}
.svc-row button:hover{color:#e74c3c}
#add-svc{background:none;border:1px dashed #333;color:#00ff41;cursor:pointer;font-family:inherit;font-size:11px;padding:4px 10px;margin-top:4px}
#add-svc:hover{border-color:#00ff41}
.submit{margin-top:24px}
#save-btn{background:#00ff41;border:none;color:#000;cursor:pointer;font-family:inherit;font-size:13px;font-weight:bold;padding:8px 24px;letter-spacing:1px}
#save-btn:hover{background:#00cc35}
#status{margin-top:12px;font-size:11px;color:#888}
.section{border-left:2px solid #1a1a1a;padding-left:12px}
#brain-url-row{margin-top:8px;display:none}
</style>
</head>
<body>
<h1>&gt; TERMINAL MONITOR SETUP</h1>

<h2>Dashboard</h2>
<div class="section">
  <div class="field"><label>Title</label><input id="title" type="text" value="Ops Dashboard"></div>
  <div class="field"><label>Default Ollama model</label><input id="model" type="text" value="ops-brain"></div>
  <div class="field"><label>Training pair threshold</label><input id="threshold" type="number" value="100" min="1"></div>
</div>

<h2>Brain Sync</h2>
<div class="section">
  <div class="field toggle">
    <input type="checkbox" id="brain-enabled"
      onchange="document.getElementById('brain-url-row').style.display=this.checked?'block':'none'">
    <label for="brain-enabled" style="margin:0">Enable NeuroLinked brain sync</label>
  </div>
  <div id="brain-url-row" class="field">
    <label>Brain URL</label>
    <input id="brain-url" type="url" value="http://localhost:8000">
  </div>
</div>

<h2>Services</h2>
<div class="section">
  <div id="svc-list"></div>
  <button id="add-svc" onclick="addSvc()">+ add service</button>
</div>

<h2>Alert Thresholds</h2>
<div class="section">
  <div class="field"><label>CPU % threshold</label><input id="cpu-t" type="number" value="80" min="1" max="100"></div>
  <div class="field"><label>RAM % threshold</label><input id="ram-t" type="number" value="80" min="1" max="100"></div>
  <div class="field"><label>GPU temp Â°C threshold</label><input id="gpu-t" type="number" value="80" min="1"></div>
  <div class="field toggle">
    <input type="checkbox" id="offline-notify" checked>
    <label for="offline-notify" style="margin:0">Notify when services go offline</label>
  </div>
</div>

<div class="submit">
  <button id="save-btn" onclick="save()">SAVE CONFIG</button>
  <div id="status"></div>
</div>

<script>
var _n = 0;
function addSvc(name, port, cmd) {
  var id = ++_n;
  var row = document.createElement('div'); row.className='svc-row'; row.id='svc-'+id;
  row.innerHTML='<input type="text" placeholder="service name" value="'+(name||'')+'">'
    +'<input type="number" placeholder="port" value="'+(port||'')+'" style="max-width:80px">'
    +'<input type="text" placeholder="start command (optional)" value="'+(cmd||'')+'">'
    +'<button onclick="document.getElementById(\'svc-'+id+'\').remove()">x</button>';
  document.getElementById('svc-list').appendChild(row);
}
function getSvcs() {
  var out=[];
  document.querySelectorAll('.svc-row').forEach(function(row) {
    var ins=row.querySelectorAll('input');
    var name=ins[0].value.trim(), port=parseInt(ins[1].value,10), cmd=ins[2].value.trim();
    if(name&&port){var s={name:name,port:port}; if(cmd)s.start_command=cmd; out.push(s);}
  });
  return out;
}
async function save() {
  var btn=document.getElementById('save-btn'), st=document.getElementById('status');
  btn.disabled=true; btn.textContent='SAVING...';
  var body={
    title:document.getElementById('title').value.trim()||'Ops Dashboard',
    default_model:document.getElementById('model').value.trim()||'ops-brain',
    training_threshold:parseInt(document.getElementById('threshold').value,10)||100,
    brain_enabled:document.getElementById('brain-enabled').checked,
    brain_url:document.getElementById('brain-url').value.trim()||'http://localhost:8000',
    services:getSvcs(),
    cpu_threshold:parseInt(document.getElementById('cpu-t').value,10)||80,
    ram_threshold:parseInt(document.getElementById('ram-t').value,10)||80,
    gpu_temp_threshold:parseInt(document.getElementById('gpu-t').value,10)||80,
    offline_notify:document.getElementById('offline-notify').checked,
  };
  try {
    var r=await fetch('/api/setup',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
    var data=await r.json();
    if(data.saved){
      st.style.color='#00ff41'; st.textContent='Config saved â€” redirecting...';
      setTimeout(function(){window.location.href='/dashboard';},1200);
    } else {
      st.style.color='#e74c3c'; st.textContent='Save failed.';
      btn.disabled=false; btn.textContent='SAVE CONFIG';
    }
  } catch(e) {
    st.style.color='#e74c3c'; st.textContent='Error: '+e.message;
    btn.disabled=false; btn.textContent='SAVE CONFIG';
  }
}
// Pre-populate when editing existing config
(async function() {
  try {
    var r=await fetch('/api/config'); if(!r.ok)return;
    var cfg=await r.json();
    if(cfg.title)document.getElementById('title').value=cfg.title;
    if(cfg.default_model)document.getElementById('model').value=cfg.default_model;
    if(cfg.training_threshold)document.getElementById('threshold').value=cfg.training_threshold;
    if(cfg.brain_enabled){
      document.getElementById('brain-enabled').checked=true;
      document.getElementById('brain-url-row').style.display='block';
    }
    if(cfg.alerts){
      if(cfg.alerts.cpu_threshold)document.getElementById('cpu-t').value=cfg.alerts.cpu_threshold;
      if(cfg.alerts.ram_threshold)document.getElementById('ram-t').value=cfg.alerts.ram_threshold;
      if(cfg.alerts.gpu_temp_threshold)document.getElementById('gpu-t').value=cfg.alerts.gpu_temp_threshold;
      document.getElementById('offline-notify').checked=cfg.alerts.offline_notify!==false;
    }
    (cfg.services||[]).forEach(function(s){addSvc(s.name,s.port,s.start_command);});
  } catch(_){}
})();
</script>
</body>
</html>
```

- [x] **Step 4: Add `/setup` and `/api/setup` to `termmon/main.py`**

Add Pydantic model (near `ChatRequest`):
```python
class SetupRequest(BaseModel):
    title: str = "Ops Dashboard"
    default_model: str = "ops-brain"
    training_threshold: int = 100
    brain_enabled: bool = False
    brain_url: str = "http://localhost:8000"
    services: list[dict] = []
    cpu_threshold: int = 80
    ram_threshold: int = 80
    gpu_temp_threshold: int = 80
    offline_notify: bool = True
```

Add path constant (near `_DASHBOARD`):
```python
_SETUP = pathlib.Path(__file__).parent / "setup.html"
```

Add endpoints (before the `/dashboard` route):
```python
@app.get("/setup")
async def setup_page():
    return FileResponse(_SETUP, media_type="text/html")


@app.post("/api/setup")
async def setup_post(req: SetupRequest):
    from termmon.config import (
        Settings, DashboardConfig, BrainConfig, ServiceConfig, AlertsConfig,
    )
    settings = Settings(
        dashboard=DashboardConfig(
            title=req.title,
            default_model=req.default_model,
            training_threshold=req.training_threshold,
        ),
        brain=BrainConfig(enabled=req.brain_enabled, url=req.brain_url),
        services=[
            ServiceConfig(name=s["name"], port=s["port"], start_command=s.get("start_command"))
            for s in req.services
            if s.get("name") and s.get("port")
        ],
        alerts=AlertsConfig(
            cpu_threshold=req.cpu_threshold,
            ram_threshold=req.ram_threshold,
            gpu_temp_threshold=req.gpu_temp_threshold,
            offline_notify=req.offline_notify,
        ),
    )
    write_settings(settings)
    return {"saved": True}
```

- [x] **Step 5: Create `config.example.yaml`**

```yaml
# Terminal Monitor â€” config.example.yaml
# Copy to config.yaml and fill in your values.
# config.yaml is gitignored â€” personal data never ships.

dashboard:
  title: "Ops Dashboard"        # shown in browser tab
  default_model: "ops-brain"    # default Ollama model for CHAT tab
  training_threshold: 100       # fine-tune "ready" badge threshold

brain:
  enabled: false                # set true to sync scans to NeuroLinked
  url: "http://localhost:8000"  # NeuroLinked base URL

services:                       # services to track on MCP / Services tab
  - name: "my-agent"
    port: 8090
    start_command: "cd /path/to/my-agent && python -m uvicorn main:app --port 8090"
  # - name: "another-service"
  #   port: 8091

alerts:
  cpu_threshold: 80             # % CPU before browser notification fires
  ram_threshold: 80             # % RAM before browser notification fires
  gpu_temp_threshold: 80        # degrees C GPU temp before alert fires
  offline_notify: true          # notify when a listed service goes offline
```

- [x] **Step 6: Run new tests to verify they pass**

```powershell
.venv\Scripts\python -m pytest tests/test_api.py::test_setup_get_returns_html tests/test_api.py::test_setup_post_saves_config -v
```
Expected: 2 PASSED.

- [x] **Step 7: Run full test suite**

```powershell
.venv\Scripts\python -m pytest -v
```
Expected: All tests pass.

- [x] **Step 8: Commit**

```powershell
git add termmon/setup.html termmon/main.py config.example.yaml tests/test_api.py
git commit -m "feat: web setup wizard, /api/setup POST, config.example.yaml"
```

---

## Self-Review

**Spec coverage:**

| Spec section | Tasks |
|---|---|
| Config module (`termmon/config.py`) | 1 |
| Security fixes (brain.py URL, MCP_PORT_MAP, proc_desc.json duplicate) | 2, 3 |
| `/api/config` endpoint (dashboard-safe, no brain URL) | 3 |
| Auto-redirect `/dashboard` â†’ `/setup` when no config.yaml | 3 |
| History module (NDJSON, 500-entry cap) | 4 |
| `/api/history` endpoint + scan/resource wiring | 5 |
| Frontend history seed on page load | 6 |
| Alerts evaluator (`evaluate_alerts`) | 7 |
| `/api/alerts/current` endpoint with cached state | 8 |
| Browser Notification API + 30s poller | 9 |
| CLI setup wizard (`setup.py`) | 10 |
| Web setup wizard (`/setup` + `/api/setup`) | 11 |
| `config.example.yaml` buyer template | 11 |
| `.gitignore` additions (config.yaml, data/, model artifacts) | 2 |

**Placeholder scan:** None found â€” every step has complete code.

**Type consistency:** `Settings`, `DashboardConfig`, `BrainConfig`, `ServiceConfig`, `AlertsConfig` defined in Task 1 and used consistently across Tasks 2, 3, 7, 8, 10, 11. `evaluate_alerts(scan, resources, settings)` signature defined in Task 7, called in Task 8. `write_settings(settings: Settings)` defined in Task 1, used in Tasks 10 (via pyyaml) and 11 (via endpoint). All consistent.
