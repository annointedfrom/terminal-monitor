# Ops Room Dashboard — Design Spec

**Date:** 2026-05-19
**Project:** terminal-monitor (`Sandbox/projects/terminal-monitor/`)

---

## Goal

Add a real-time ops dashboard served at `GET /dashboard` from the terminal-monitor FastAPI app. Clicking "Open Dashboard" in the agent hub opens `http://localhost:8084/dashboard` in a new tab, replacing the useless `/docs` link with an actual tool for monitoring and managing running processes, MCP servers, and system resources.

---

## Architecture

Terminal-monitor serves a single self-contained HTML file at `GET /dashboard` via FastAPI `FileResponse`. The page's vanilla JS polls two existing-plus-new JSON endpoints every 5 seconds to keep data live. No new framework dependencies.

```
browser → GET /dashboard → termmon/dashboard.html (FileResponse)
browser → GET /api/scan  (every 5s) → stat header + PROCESSES tab + MCP tab
browser → GET /api/resources (every 5s) → RESOURCES tab
browser → POST /api/kill/{pid} (on kill button click) → psutil terminate/kill
```

The hub integration is a one-line config change: action D URL in `hub-config.yaml` switches from `http://localhost:8084/docs` to `http://localhost:8084/dashboard`.

---

## Files

| File | Change |
|---|---|
| `termmon/main.py` | Implement `kill_process` endpoint; add `GET /api/resources`; add `GET /dashboard` |
| `termmon/scanner/resources.py` | New module — `get_resources()` returns CPU%, RAM, disk stats |
| `termmon/dashboard.html` | New — single-file HTML/CSS/JS dashboard |
| `hub/hub-config.yaml` | Action D URL → `http://localhost:8084/dashboard` |
| `tests/test_api.py` | Tests for kill (success, not-found, access-denied) and resources |

---

## API additions

### `POST /api/kill/{pid}`

Replaces the existing 501 stub. Sends SIGTERM, waits 0.5s, sends SIGKILL if still running.

**Responses:**
- `200 {"killed": true, "pid": N}` — process terminated
- `404 {"detail": "Process not found"}` — no process with that PID
- `403 {"detail": "Access denied"}` — OS rejected the kill (elevated process)

**Error handling:** never raises unhandled exceptions; always returns a structured JSON response.

### `GET /api/resources`

New endpoint. Returns system-level resource stats from psutil.

```json
{
  "cpu_percent": 14.2,
  "memory": {
    "total": 17179869184,
    "available": 9126805504,
    "percent": 46.9,
    "used": 8053063680
  },
  "disk": {
    "total": 512110190592,
    "used": 210000000000,
    "free": 302110190592,
    "percent": 41.0
  }
}
```

`cpu_percent` uses `interval=0.1` (non-blocking but accurate enough for a dashboard).

### `GET /dashboard`

```python
from fastapi.responses import FileResponse
import pathlib

DASHBOARD_PATH = pathlib.Path(__file__).parent / "dashboard.html"

@app.get("/dashboard")
async def dashboard():
    return FileResponse(DASHBOARD_PATH, media_type="text/html")
```

---

## `termmon/scanner/resources.py`

Single public function, no class needed.

```python
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

---

## Dashboard HTML (`termmon/dashboard.html`)

Self-contained single file. No external CDN dependencies. Inline CSS + JS.

### Visual structure

```
┌─────────────────────────────────────────────────┐
│ OPS DASHBOARD        ● LIVE  updated 3s ago  ↺  │  ← top bar
├──────────┬──────────┬──────────┬────────────────┤
│ PORTS    │ PROCESSES│ MCP      │ ENERGY         │  ← stat header (always visible)
│ 32 active│ 17 unique│ 1/5 run  │ OK             │
├──────────┴──────────┴──────────┴────────────────┤
│ PROCESSES │ MCP │ RESOURCES │ HISTORY · ENERGY  │  ← tab bar
│                                                  │
│  PROCESS      MEMORY   PORT   PID   ACTION       │  ← tab content (scrollable)
│  Obsidian.exe 3202MB   —      4821  [kill]       │
│  python.exe   702MB    8084   6203  [kill]       │
│  uvicorn      84MB     8090   5512  [kill]       │
│  ...                                             │
└─────────────────────────────────────────────────┘
```

### Stat header tiles

| Tile | Data source | Value shown |
|---|---|---|
| PORTS | `scan.ports.length` | count active, sub-label: "N agents · M other" |
| PROCESSES | `scan.summary.process_count` | count unique, sub-label: top process + MB |
| MCP | `scan.mcp_servers` | "running/total", sub-label: names of running ones |
| ENERGY | `resources.cpu_percent` | "OK" / "BUSY" / "HIGH", sub-label: "cpu N%" |

ENERGY thresholds: ≤40% → "OK" green, 40–70% → "BUSY" amber, >70% → "HIGH" red.

### Tab: PROCESSES

Columns: PROCESS | MEMORY (value + bar) | PORT | PID | ACTION  
Data: `scan.ports`, deduplicated by process name, sorted by `memory_mb` descending.  
Kill button calls `POST /api/kill/{pid}`. On success: re-runs scan immediately. On 403: shows "access denied" in row. On 404: row disappears on next scan.

### Tab: MCP

Columns: SERVER | STATUS | PID  
Data: `scan.mcp_servers`.  
Running servers show green "✓ running" + pid. Stopped servers show red "✗ stopped" + "—".

### Tab: RESOURCES

Three bars: CPU%, RAM used/total, Disk used/total.  
Color thresholds (same as ENERGY tile): ≤40% green, 40–70% amber, >70% red.  
Data: `/api/resources`.

### Tab: HISTORY / ENERGY

Both tabs render a centered "Coming soon" placeholder. The tabs are present in the bar to reserve space for future features.

### Refresh behavior

`setInterval` polls both endpoints every 5000ms. "Updated Ns ago" counter ticks up each second via a separate 1s interval. On scan error: header shows "scan failed" in amber, existing data stays visible (stale but not blank).

### Kill safety

Kill button shows a 1-second "killing…" state before re-scanning. No confirmation dialog — the button is intentionally direct. If the process being killed is the terminal-monitor itself (port 8084), the page will lose its data source; this is not guarded against (user's responsibility).

---

## Hub config change

In `hub/hub-config.yaml`, the Terminal Monitor agent's action D:

```yaml
# before
- key: D
  label: Open Dashboard
  url: "http://localhost:8084/docs"

# after
- key: D
  label: Open Dashboard
  url: "http://localhost:8084/dashboard"
```

---

## Testing

### `tests/test_api.py` additions

**Kill endpoint:**
- `test_kill_process_success` — mock `psutil.Process` → assert 200 `{"killed": true, "pid": N}`
- `test_kill_process_not_found` — mock raises `psutil.NoSuchProcess` → assert 404
- `test_kill_process_access_denied` — mock raises `psutil.AccessDenied` → assert 403

**Resources endpoint:**
- `test_get_resources_structure` — mock `psutil.cpu_percent`, `virtual_memory`, `disk_usage` → assert keys present and numeric

**Dashboard route:**
- `test_dashboard_returns_html` — assert status 200, content-type `text/html`

### No new test files needed — all additions go in `tests/test_api.py`.

---

## Out of scope

- Process restart (the `/api/restart/{agent_id}` stub stays as 501 — that's a future feature tied to the energy/CPU saving mode spec)
- Authentication on kill endpoint (localhost-only service, no auth layer planned)
- Scan history persistence (separate spec)
- Energy/CPU saving mode controls (separate spec)
