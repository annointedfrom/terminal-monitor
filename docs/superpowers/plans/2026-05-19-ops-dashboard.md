# Ops Room Dashboard â€” Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add a live ops dashboard at `GET /dashboard` (terminal-monitor) with process kill controls, MCP status, and resource bars, replacing the `/docs` link in hub-config.

**Architecture:** Terminal-monitor serves a self-contained HTML file via FastAPI FileResponse. Vanilla JS polls `/api/scan` and the new `/api/resources` every 5 seconds. A new `termmon/scanner/resources.py` module provides CPU/RAM/disk stats; the existing `POST /api/kill/{pid}` stub is replaced with a real psutil implementation. Hub action D URL is updated from `/docs` to `/dashboard`.

**Tech Stack:** FastAPI, psutil, vanilla JS/HTML/CSS, pytest + TestClient, unittest.mock

---

### Task 1: resources scanner module

**Files:**
- Create: `termmon/scanner/resources.py`
- Modify: `tests/test_api.py`

**Context:** `termmon/scanner/` has three existing modules (`ports.py`, `mcp.py`, `health.py`). Each exports one public function. Follow the same pattern. `tests/test_api.py` uses `TestClient(app)` and patches with `unittest.mock.patch`. Windows needs `"C:\\"` for disk_usage, not `"/"`.

- [x] **Step 1: Write the failing test**

Add to `tests/test_api.py`:

```python
from unittest.mock import MagicMock

def test_get_resources_structure():
    mock_mem = MagicMock()
    mock_mem.total = 17179869184
    mock_mem.available = 9000000000
    mock_mem.percent = 47.6
    mock_mem.used = 8179869184

    mock_disk = MagicMock()
    mock_disk.total = 512000000000
    mock_disk.used = 200000000000
    mock_disk.free = 312000000000
    mock_disk.percent = 39.1

    with patch("termmon.scanner.resources.psutil.cpu_percent", return_value=22.5), \
         patch("termmon.scanner.resources.psutil.virtual_memory", return_value=mock_mem), \
         patch("termmon.scanner.resources.psutil.disk_usage", return_value=mock_disk):
        r = client.get("/api/resources")

    assert r.status_code == 200
    data = r.json()
    assert data["cpu_percent"] == 22.5
    assert data["memory"]["total"] == 17179869184
    assert data["memory"]["percent"] == 47.6
    assert data["disk"]["percent"] == 39.1
```

- [x] **Step 2: Run test to verify it fails**

```
cd C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor
.venv\Scripts\activate
pytest tests/test_api.py::test_get_resources_structure -v
```

Expected: FAIL â€” `404` or `ImportError`

- [x] **Step 3: Create `termmon/scanner/resources.py`**

```python
from __future__ import annotations

import os

import psutil


def get_resources() -> dict:
    mem = psutil.virtual_memory()
    disk_path = "C:\\" if os.name == "nt" else "/"
    disk = psutil.disk_usage(disk_path)
    return {
        "cpu_percent": psutil.cpu_percent(interval=0.1),
        "memory": {
            "total": mem.total,
            "available": mem.available,
            "percent": mem.percent,
            "used": mem.used,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        },
    }
```

- [x] **Step 4: Add `/api/resources` route to `termmon/main.py`**

Add import at top of `termmon/main.py` (after the other scanner imports):

```python
from termmon.scanner.resources import get_resources
```

Add route (anywhere after the existing stat routes):

```python
@app.get("/api/resources")
async def get_resources_endpoint():
    return get_resources()
```

- [x] **Step 5: Run test to verify it passes**

```
pytest tests/test_api.py::test_get_resources_structure -v
```

Expected: PASS

- [x] **Step 6: Run full suite**

```
pytest tests/ -v
```

Expected: all existing tests pass, 1 new test passes

- [x] **Step 7: Commit**

```
git add termmon/scanner/resources.py termmon/main.py tests/test_api.py
git commit -m "feat: add /api/resources endpoint with CPU/RAM/disk stats"
```

---

### Task 2: implement kill endpoint + add dashboard route

**Files:**
- Modify: `termmon/main.py`
- Modify: `tests/test_api.py`

**Context:** `termmon/main.py` line 95-97 has a kill stub returning 501. Replace it. `asyncio` is already imported. `psutil` is already imported indirectly via scanner modules but needs a direct import in main for `psutil.Process`, `psutil.NoSuchProcess`, `psutil.AccessDenied`. The dashboard route serves `termmon/dashboard.html` via `FileResponse` â€” the file doesn't exist yet (Task 3 creates it), but the route and its test can be written now. The test just checks status 200 + content-type `text/html`, and only works once the file exists, so write it after Task 3 OR mark it with a note. **Write the route now; skip the dashboard HTML test until after Task 3.**

- [x] **Step 1: Write kill tests (replace the 501 stub test)**

In `tests/test_api.py`, remove the existing `test_kill_stub_returns_501` test and replace with:

```python
def test_kill_process_success():
    mock_proc = MagicMock()
    mock_proc.is_running.return_value = False
    with patch("termmon.main.psutil.Process", return_value=mock_proc):
        r = client.post("/api/kill/12345")
    assert r.status_code == 200
    assert r.json() == {"killed": True, "pid": 12345}
    mock_proc.terminate.assert_called_once()


def test_kill_process_not_found():
    import psutil as _psutil
    with patch("termmon.main.psutil.Process", side_effect=_psutil.NoSuchProcess(pid=99999)):
        r = client.post("/api/kill/99999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_kill_process_access_denied():
    import psutil as _psutil
    with patch("termmon.main.psutil.Process", side_effect=_psutil.AccessDenied(pid=1)):
        r = client.post("/api/kill/1")
    assert r.status_code == 403
    assert "denied" in r.json()["detail"].lower()
```

- [x] **Step 2: Run new kill tests to verify they fail**

```
pytest tests/test_api.py::test_kill_process_success tests/test_api.py::test_kill_process_not_found tests/test_api.py::test_kill_process_access_denied -v
```

Expected: all 3 FAIL â€” endpoint still returns 501

- [x] **Step 3: Replace the kill stub + add imports to `termmon/main.py`**

Add `import psutil` as a direct top-level import (after `from fastapi.responses import JSONResponse`):

```python
import psutil
```

Replace lines 95-97 (the kill stub):

```python
@app.post("/api/kill/{pid}")
async def kill_process(pid: int):
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        await asyncio.sleep(0.5)
        if proc.is_running():
            proc.kill()
        return {"killed": True, "pid": pid}
    except psutil.NoSuchProcess:
        return JSONResponse(status_code=404, content={"detail": "Process not found"})
    except psutil.AccessDenied:
        return JSONResponse(status_code=403, content={"detail": "Access denied"})
```

- [x] **Step 4: Run kill tests to verify they pass**

```
pytest tests/test_api.py::test_kill_process_success tests/test_api.py::test_kill_process_not_found tests/test_api.py::test_kill_process_access_denied -v
```

Expected: all 3 PASS

- [x] **Step 5: Add dashboard route to `termmon/main.py`**

Add import at top (after `from fastapi.responses import JSONResponse`):

```python
import pathlib
from fastapi.responses import FileResponse
```

Add route (at the end of the file, after the restart stub):

```python
_DASHBOARD = pathlib.Path(__file__).parent / "dashboard.html"

@app.get("/dashboard")
async def dashboard():
    return FileResponse(_DASHBOARD, media_type="text/html")
```

- [x] **Step 6: Run full suite**

```
pytest tests/ -v
```

Expected: all tests pass (dashboard route returns 404 until Task 3 creates the file â€” that's fine, the route test is added in Task 3)

- [x] **Step 7: Commit**

```
git add termmon/main.py tests/test_api.py
git commit -m "feat: implement kill endpoint and add /dashboard route"
```

---

### Task 3: dashboard HTML

**Files:**
- Create: `termmon/dashboard.html`
- Modify: `tests/test_api.py`

**Context:** Self-contained single file. Dark terminal theme matching the ops mockup (compact stat header, tabs, process table with kill buttons, MCP status, resource bars). Polls `/api/scan` and `/api/resources` every 5 seconds. No external CDN dependencies â€” all CSS/JS inline.

- [x] **Step 1: Add the dashboard HTML test**

Add to `tests/test_api.py`:

```python
def test_dashboard_returns_html():
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
```

- [x] **Step 2: Run test to verify it fails**

```
pytest tests/test_api.py::test_dashboard_returns_html -v
```

Expected: FAIL â€” 404 (file not found)

- [x] **Step 3: Create `termmon/dashboard.html`**

Create the file at `C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor\termmon\dashboard.html` with this exact content:

```html
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Ops Dashboard</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: #0d0d0d; color: #ccc; font-family: monospace; font-size: 12px; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
#top-bar { background: #111; border-bottom: 1px solid #333; padding: 5px 12px; display: flex; align-items: center; justify-content: space-between; flex-shrink: 0; }
#top-bar-left { color: #3498db; font-size: 11px; letter-spacing: 2px; }
#top-bar-right { display: flex; gap: 10px; align-items: center; }
#live-indicator { color: #2ecc71; font-size: 10px; }
#updated-label { color: #555; font-size: 10px; }
#scan-btn { background: #1a3a1a; border: 1px solid #2a5a2a; color: #2ecc71; font-size: 9px; padding: 2px 8px; border-radius: 2px; cursor: pointer; }
#scan-btn:hover { background: #1f4a1f; }
#error-bar { display: none; background: #1a0a0a; border-bottom: 1px solid #4a2a2a; padding: 3px 12px; color: #e67e22; font-size: 9px; flex-shrink: 0; }
#stat-header { display: grid; grid-template-columns: 1fr 1fr 1fr 1fr; gap: 1px; background: #1a1a1a; border-bottom: 2px solid #1a3a5a; flex-shrink: 0; }
.stat-tile { background: #0d0d0d; padding: 6px 10px; }
.stat-label { color: #555; font-size: 8px; letter-spacing: 1px; margin-bottom: 3px; }
.stat-value { display: flex; align-items: baseline; gap: 4px; }
.stat-num { color: #fff; font-size: 18px; font-weight: bold; }
.stat-unit { font-size: 8px; }
.stat-sub { color: #555; font-size: 8px; margin-top: 1px; }
.ok { color: #2ecc71; }
.warn { color: #e67e22; }
.high { color: #e74c3c; }
#tab-bar { display: flex; align-items: stretch; border-bottom: 1px solid #1a1a1a; background: #0a0a0a; flex-shrink: 0; }
.tab { padding: 5px 12px; font-size: 9px; color: #555; cursor: pointer; border-bottom: 2px solid transparent; margin-bottom: -1px; }
.tab:hover { color: #888; }
.tab.active { color: #3498db; border-bottom-color: #3498db; background: #0d0d0d; }
.tab.soon { color: #333; cursor: default; }
.soon-badge { font-size: 7px; border: 1px solid #333; padding: 0 2px; border-radius: 2px; margin-left: 3px; }
#tab-content { flex: 1; overflow-y: auto; padding: 8px 10px; }
.tab-pane { display: none; }
.tab-pane.active { display: block; }
.tbl-header { gap: 4px; margin-bottom: 4px; border-bottom: 1px solid #1a1a1a; padding-bottom: 3px; }
.tbl-header span { color: #444; font-size: 8px; letter-spacing: 1px; }
.proc-grid { display: grid; grid-template-columns: 1fr 80px 65px 60px auto; gap: 4px; }
.proc-row { display: grid; grid-template-columns: 1fr 80px 65px 60px auto; gap: 4px; align-items: center; margin-bottom: 5px; }
.mem-cell { display: flex; flex-direction: column; gap: 1px; }
.mem-bar-bg { background: #1a1a1a; height: 3px; border-radius: 1px; }
.mem-bar { height: 100%; border-radius: 1px; }
.kill-btn { background: #2a1a1a; border: 1px solid #4a2a2a; color: #e74c3c; font-size: 8px; padding: 1px 5px; border-radius: 2px; cursor: pointer; white-space: nowrap; }
.kill-btn:hover { background: #3a1a1a; }
.kill-btn:disabled { opacity: 0.5; cursor: default; }
.mcp-row { display: grid; grid-template-columns: 1fr 100px 60px; gap: 4px; align-items: center; margin-bottom: 5px; }
.res-section { margin-bottom: 12px; }
.res-label-row { display: flex; justify-content: space-between; margin-bottom: 2px; }
.res-bar-bg { background: #1a1a1a; height: 6px; border-radius: 3px; }
.res-bar { height: 100%; border-radius: 3px; transition: width 0.3s; }
.coming-soon { display: flex; align-items: center; justify-content: center; height: 120px; color: #333; font-size: 10px; letter-spacing: 2px; }
</style>
</head>
<body>

<div id="top-bar">
  <span id="top-bar-left">&#128421; OPS DASHBOARD</span>
  <div id="top-bar-right">
    <span id="live-indicator">&#9679; LIVE</span>
    <span id="updated-label">scanning&#8230;</span>
    <button id="scan-btn" onclick="doScan()">&#8634; Scan</button>
  </div>
</div>

<div id="error-bar"></div>

<div id="stat-header">
  <div class="stat-tile">
    <div class="stat-label">PORTS</div>
    <div class="stat-value"><span class="stat-num" id="stat-ports">&#8212;</span><span class="stat-unit ok">active</span></div>
    <div class="stat-sub" id="stat-ports-sub">&#8212;</div>
  </div>
  <div class="stat-tile">
    <div class="stat-label">PROCESSES</div>
    <div class="stat-value"><span class="stat-num" id="stat-procs">&#8212;</span><span class="stat-unit ok">unique</span></div>
    <div class="stat-sub" id="stat-procs-sub">&#8212;</div>
  </div>
  <div class="stat-tile">
    <div class="stat-label">MCP</div>
    <div class="stat-value"><span class="stat-num" id="stat-mcp">&#8212;</span><span class="stat-unit" id="stat-mcp-unit">running</span></div>
    <div class="stat-sub" id="stat-mcp-sub">&#8212;</div>
  </div>
  <div class="stat-tile">
    <div class="stat-label">ENERGY</div>
    <div class="stat-value"><span class="stat-num ok" id="stat-energy">&#8212;</span></div>
    <div class="stat-sub" id="stat-energy-sub">&#8212;</div>
  </div>
</div>

<div id="tab-bar">
  <div class="tab active" onclick="switchTab('processes')">PROCESSES</div>
  <div class="tab" onclick="switchTab('mcp')">MCP</div>
  <div class="tab" onclick="switchTab('resources')">RESOURCES</div>
  <div class="tab soon">HISTORY<span class="soon-badge">SOON</span></div>
  <div class="tab soon">ENERGY<span class="soon-badge">SOON</span></div>
</div>

<div id="tab-content">
  <div id="pane-processes" class="tab-pane active">
    <div class="tbl-header proc-grid">
      <span>PROCESS</span><span>MEMORY</span><span>PORT</span><span>PID</span><span>ACTION</span>
    </div>
    <div id="proc-rows"></div>
  </div>
  <div id="pane-mcp" class="tab-pane">
    <div class="tbl-header mcp-row">
      <span>SERVER</span><span>STATUS</span><span>PID</span>
    </div>
    <div id="mcp-rows"></div>
  </div>
  <div id="pane-resources" class="tab-pane">
    <div id="res-content"></div>
  </div>
  <div id="pane-history" class="tab-pane">
    <div class="coming-soon">COMING SOON</div>
  </div>
  <div id="pane-energy" class="tab-pane">
    <div class="coming-soon">COMING SOON</div>
  </div>
</div>

<script>
var _secondsSinceUpdate = 0;

function switchTab(name) {
  var tabs = document.querySelectorAll('.tab:not(.soon)');
  var names = ['processes','mcp','resources'];
  tabs.forEach(function(t, i) { t.classList.toggle('active', names[i] === name); });
  document.querySelectorAll('.tab-pane').forEach(function(p) {
    p.classList.toggle('active', p.id === 'pane-' + name);
  });
}

function setError(msg) {
  var el = document.getElementById('error-bar');
  if (msg) { el.style.display = 'block'; el.textContent = 'âš  ' + msg; }
  else { el.style.display = 'none'; }
}

async function fetchScan() {
  try {
    var r = await fetch('/api/scan');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    var data = await r.json();
    _secondsSinceUpdate = 0;
    setError(null);
    renderStatHeader(data);
    renderProcesses(data.ports || []);
    renderMCP(data.mcp_servers || []);
  } catch(e) {
    setError('Scan failed â€” ' + e.message);
  }
}

function renderStatHeader(data) {
  var ports = data.ports || [];
  var mcps = data.mcp_servers || [];
  var summary = data.summary || {};
  document.getElementById('stat-ports').textContent = ports.length;
  var agentCount = ports.filter(function(p) { return p.label; }).length;
  document.getElementById('stat-ports-sub').textContent = agentCount + ' agent' + (agentCount !== 1 ? 's' : '') + ' Â· ' + (ports.length - agentCount) + ' other';
  document.getElementById('stat-procs').textContent = summary.process_count || 0;
  var topProc = ports.slice().sort(function(a,b) { return (b.memory_mb||0) - (a.memory_mb||0); })[0];
  document.getElementById('stat-procs-sub').textContent = topProc ? 'top: ' + topProc.process + ' ' + Math.round(topProc.memory_mb||0) + 'MB' : 'none';
  var running = mcps.filter(function(m) { return m.running; }).length;
  var mcpEl = document.getElementById('stat-mcp');
  var mcpUnit = document.getElementById('stat-mcp-unit');
  mcpEl.textContent = running + '/' + mcps.length;
  mcpEl.className = 'stat-num ' + (running === mcps.length ? 'ok' : 'warn');
  mcpUnit.className = 'stat-unit ' + (running === mcps.length ? 'ok' : 'warn');
  var runningNames = mcps.filter(function(m) { return m.running; }).map(function(m) { return m.name; }).join(', ');
  document.getElementById('stat-mcp-sub').textContent = runningNames || 'none running';
}

function renderProcesses(ports) {
  var seen = {};
  var deduped = ports.slice().sort(function(a,b) { return (b.memory_mb||0) - (a.memory_mb||0); }).filter(function(p) {
    if (seen[p.process]) return false;
    seen[p.process] = true;
    return true;
  });
  var maxMem = deduped.length ? (deduped[0].memory_mb || 1) : 1;
  var container = document.getElementById('proc-rows');
  container.innerHTML = '';
  deduped.forEach(function(p) {
    var pct = Math.max(1, Math.round(((p.memory_mb||0) / maxMem) * 100));
    var memColor = p.memory_mb > 1000 ? '#e67e22' : p.memory_mb > 300 ? '#f0e68c' : '#2ecc71';
    var row = document.createElement('div');
    row.className = 'proc-row';
    row.dataset.pid = p.pid;
    var nameEl = document.createElement('span');
    nameEl.style.cssText = 'color:#ccc;font-size:9px;';
    nameEl.textContent = p.process;
    var memCell = document.createElement('div');
    memCell.className = 'mem-cell';
    var memVal = document.createElement('span');
    memVal.style.cssText = 'color:' + memColor + ';font-size:8px;';
    memVal.textContent = Math.round(p.memory_mb||0) + ' MB';
    var barBg = document.createElement('div');
    barBg.className = 'mem-bar-bg';
    var bar = document.createElement('div');
    bar.className = 'mem-bar';
    bar.style.cssText = 'width:' + pct + '%;background:' + memColor + ';';
    barBg.appendChild(bar);
    memCell.appendChild(memVal);
    memCell.appendChild(barBg);
    var portEl = document.createElement('span');
    portEl.style.cssText = 'color:#555;font-size:8px;';
    portEl.textContent = p.port || 'â€”';
    var pidEl = document.createElement('span');
    pidEl.style.cssText = 'color:#555;font-size:8px;';
    pidEl.textContent = p.pid || 'â€”';
    var killBtn = document.createElement('button');
    killBtn.className = 'kill-btn';
    killBtn.textContent = 'kill';
    killBtn.onclick = (function(pid, r, btn) { return function() { killProcess(pid, r, btn); }; })(p.pid, row, killBtn);
    row.appendChild(nameEl);
    row.appendChild(memCell);
    row.appendChild(portEl);
    row.appendChild(pidEl);
    row.appendChild(killBtn);
    container.appendChild(row);
  });
}

function renderMCP(mcps) {
  var container = document.getElementById('mcp-rows');
  container.innerHTML = '';
  mcps.forEach(function(m) {
    var row = document.createElement('div');
    row.className = 'mcp-row';
    var nameEl = document.createElement('span');
    nameEl.style.cssText = 'color:#ccc;font-size:9px;';
    nameEl.textContent = m.name;
    var statusEl = document.createElement('span');
    statusEl.style.fontSize = '8px';
    statusEl.style.color = m.running ? '#2ecc71' : '#e74c3c';
    statusEl.textContent = m.running ? 'âœ“ running' : 'âœ— stopped';
    var pidEl = document.createElement('span');
    pidEl.style.cssText = 'color:#555;font-size:8px;';
    pidEl.textContent = m.pid || 'â€”';
    row.appendChild(nameEl);
    row.appendChild(statusEl);
    row.appendChild(pidEl);
    container.appendChild(row);
  });
}

async function killProcess(pid, row, btn) {
  btn.disabled = true;
  btn.textContent = 'killingâ€¦';
  try {
    var r = await fetch('/api/kill/' + pid, { method: 'POST' });
    if (r.status === 403) {
      btn.textContent = 'denied';
      btn.style.color = '#e67e22';
      setTimeout(function() { btn.textContent = 'kill'; btn.style.color = ''; btn.disabled = false; }, 2000);
      return;
    }
    if (r.status === 404) { row.style.opacity = '0.3'; return; }
    if (!r.ok) throw new Error('HTTP ' + r.status);
    row.remove();
    await fetchScan();
  } catch(e) {
    btn.textContent = 'error';
    setTimeout(function() { btn.textContent = 'kill'; btn.disabled = false; }, 2000);
  }
}

async function fetchResources() {
  try {
    var r = await fetch('/api/resources');
    if (!r.ok) throw new Error('HTTP ' + r.status);
    var data = await r.json();
    renderResources(data);
    var cpu = data.cpu_percent || 0;
    var energyEl = document.getElementById('stat-energy');
    var energySub = document.getElementById('stat-energy-sub');
    if (cpu > 70) { energyEl.textContent = 'HIGH'; energyEl.className = 'stat-num high'; }
    else if (cpu > 40) { energyEl.textContent = 'BUSY'; energyEl.className = 'stat-num warn'; }
    else { energyEl.textContent = 'OK'; energyEl.className = 'stat-num ok'; }
    energySub.textContent = 'cpu ' + cpu.toFixed(1) + '%';
  } catch(e) { /* non-fatal */ }
}

function renderResources(data) {
  var container = document.getElementById('res-content');
  container.innerHTML = '';
  function fmtBytes(b) { return b >= 1073741824 ? (b/1073741824).toFixed(1) + ' GB' : (b/1048576).toFixed(0) + ' MB'; }
  function barColor(pct) { return pct > 70 ? '#e74c3c' : pct > 40 ? '#e67e22' : '#2ecc71'; }
  function addBar(label, pct, subLabel) {
    var color = barColor(pct);
    var sec = document.createElement('div');
    sec.className = 'res-section';
    var labelRow = document.createElement('div');
    labelRow.className = 'res-label-row';
    var lSpan = document.createElement('span');
    lSpan.style.cssText = 'color:#888;font-size:9px;';
    lSpan.textContent = label;
    var rSpan = document.createElement('span');
    rSpan.style.cssText = 'color:' + color + ';font-size:9px;';
    rSpan.textContent = subLabel;
    labelRow.appendChild(lSpan);
    labelRow.appendChild(rSpan);
    var barBg = document.createElement('div');
    barBg.className = 'res-bar-bg';
    var bar = document.createElement('div');
    bar.className = 'res-bar';
    bar.style.cssText = 'width:' + Math.min(pct,100) + '%;background:' + color + ';';
    barBg.appendChild(bar);
    sec.appendChild(labelRow);
    sec.appendChild(barBg);
    container.appendChild(sec);
  }
  addBar('CPU', data.cpu_percent || 0, (data.cpu_percent||0).toFixed(1) + '%');
  if (data.memory) {
    var m = data.memory;
    addBar('RAM', m.percent || 0, fmtBytes(m.used) + ' / ' + fmtBytes(m.total) + ' (' + (m.percent||0).toFixed(1) + '%)');
  }
  if (data.disk) {
    var d = data.disk;
    addBar('DISK', d.percent || 0, fmtBytes(d.used) + ' / ' + fmtBytes(d.total) + ' (' + (d.percent||0).toFixed(1) + '%)');
  }
}

function tickUpdated() {
  _secondsSinceUpdate++;
  document.getElementById('updated-label').textContent = 'updated ' + _secondsSinceUpdate + 's ago';
}

async function doScan() {
  _secondsSinceUpdate = 0;
  await Promise.all([fetchScan(), fetchResources()]);
}

doScan();
setInterval(fetchScan, 5000);
setInterval(fetchResources, 5000);
setInterval(tickUpdated, 1000);
</script>
</body>
</html>
```

- [x] **Step 4: Run dashboard test**

```
pytest tests/test_api.py::test_dashboard_returns_html -v
```

Expected: PASS

- [x] **Step 5: Run full test suite**

```
pytest tests/ -v
```

Expected: all tests pass

- [x] **Step 6: Commit**

```
git add termmon/dashboard.html tests/test_api.py
git commit -m "feat: add ops dashboard HTML"
```

---

### Task 4: update hub-config action D URL

**Files:**
- Modify: `C:\Users\hms16\Me\MyWords\Sandbox\projects\agent-hub\hub-config.yaml` (line 206)

**Context:** The terminal-monitor agent block is at lines 171â€“212 in `hub-config.yaml`. Action D (line 203â€“206) points to `http://localhost:8084/docs`. Change the URL to `http://localhost:8084/dashboard`. Also update the `dashboard:` field at line 176.

- [x] **Step 1: Update hub-config.yaml**

In `C:\Users\hms16\Me\MyWords\Sandbox\projects\agent-hub\hub-config.yaml`, change:

```yaml
  dashboard: http://localhost:8084/docs
```
to:
```yaml
  dashboard: http://localhost:8084/dashboard
```

And change:
```yaml
      - key: D
        label: Open Dashboard
        type: link
        url: http://localhost:8084/docs
```
to:
```yaml
      - key: D
        label: Open Dashboard
        type: link
        url: http://localhost:8084/dashboard
```

- [x] **Step 2: Run agent-hub tests**

```
cd C:\Users\hms16\Me\MyWords\Sandbox\projects\agent-hub
.venv\Scripts\activate
pytest tests/ -v
```

Expected: all tests pass

- [x] **Step 3: Commit (from agent-hub repo)**

```
git add hub-config.yaml
git commit -m "feat: point terminal-monitor dashboard link to /dashboard"
```

- [x] **Step 4: Manual verification**

Start terminal-monitor: `uvicorn termmon.main:app --port 8084`  
Open browser: `http://localhost:8084/dashboard`  
Verify: compact stat header loads, PROCESSES tab shows real data, kill buttons present, tabs switch correctly.

Start agent-hub: `uvicorn hub.main:app --port 8090`  
Navigate to Ops Room, press D on Terminal Monitor.  
Verify: browser opens `http://localhost:8084/dashboard`.
