# Terminal Monitor — Design Spec

**Date:** 2026-05-18
**Status:** Approved

---

## Goal

A standalone FastAPI agent that gives a live view of everything running on the local machine: all listening localhost ports, process health, and which MCP servers configured in Claude Code are actually alive. Appears in the Agent Hub as the `🖥️` character in the Ops Room. Feeds snapshots to the NeuroLinked brain every 60 seconds. Control actions (kill, restart) are stubbed for v2.

---

## Architecture

### Overview

```
Browser (Agent Hub) → Terminal Monitor /api/scan
                    → psutil: enumerate all listening ports + process info
                    → httpx: ping each port for health response
                    → ~/.claude/settings.json: read configured MCP servers
                    → Windows process list: match MCP server executables
                    → NeuroLinked brain: POST snapshot every 60s
```

### Backend — FastAPI (`termmon/main.py`)

- Port **8084**
- `GET /health` — always 200
- `GET /api/scan` — full scan: ports + health + MCP servers
- `GET /api/mcp` — MCP server list with running/stopped per server
- `GET /api/stats/port_count` — integer count of listening ports
- `GET /api/stats/mcp_count` — integer count of running MCP servers
- `GET /api/stats/process_count` — integer count of unique processes on listening ports
- `POST /api/brain/sync` — push current snapshot to NeuroLinked brain
- `POST /api/kill/{pid}` — **stub, returns 501** (v2)
- `POST /api/restart/{id}` — **stub, returns 501** (v2)

Background task: `asyncio` periodic task fires every 60s, calls `brain.sync()`.

### Scanner modules (`termmon/scanner/`)

**`ports.py`** — Uses `psutil.net_connections(kind="inet")` to list all `LISTEN` state connections on localhost. For each port, resolves the owning process: name, PID, RSS memory (MB), and process create time (used to compute uptime). Cross-references the Agent Hub `hub-config.yaml` at `../agent-hub/hub-config.yaml` (relative path, falls back gracefully if not found) to attach human-readable labels to known agent ports.

**`health.py`** — For each port discovered by `ports.py`, fires an async httpx GET to `http://localhost:{port}/health` (timeout 1.5s). Falls back to `http://localhost:{port}/` if `/health` returns 404. Records `healthy: true` if status < 500, `healthy: false` on connection error or timeout. All pings run concurrently via `asyncio.gather`.

**`mcp.py`** — Reads `~/.claude/settings.json` (Windows path: `C:\Users\{username}\.claude\settings.json`). Parses the `mcpServers` object — each key is a server name, each value has a `command` and `args` array. For each configured server, scans the live Windows process list (via `psutil.process_iter`) for a running process whose executable path or command line contains a matching token (e.g., `playwright`, `chrome-devtools-mcp`, server script name). Records `running: true/false` and `pid` if found.

### Brain integration (`termmon/brain.py`)

On each sync (manual via `POST /api/brain/sync` or automatic every 60s):

1. `POST http://localhost:8000/api/claude/remember` — stores the scan summary:
   ```json
   {
     "text": "Terminal Monitor snapshot: 7 ports active, 3 MCP servers running. Ports: [8082 Job Agent healthy, 8084 Terminal Monitor healthy, ...]",
     "source": "terminal-monitor",
     "tags": ["terminal-monitor", "system-state", "ports", "mcp-servers"]
   }
   ```
2. `POST http://localhost:8000/api/claude/observe` — logs the sync action:
   ```json
   {
     "type": "action",
     "content": "Terminal Monitor auto-sync: 7 ports, 3 MCP online",
     "source": "terminal-monitor"
   }
   ```

Brain sync failures are logged but do not crash the agent (fire-and-forget with timeout 5s).

---

## Scan Result Shape

`GET /api/scan` response:

```json
{
  "scanned_at": "2026-05-18T14:23:00",
  "ports": [
    {
      "port": 8082,
      "pid": 30072,
      "process": "python.exe",
      "memory_mb": 56.4,
      "uptime_s": 3600,
      "healthy": true,
      "label": "Job Agent"
    }
  ],
  "mcp_servers": [
    {
      "name": "playwright",
      "command": "npx @playwright/mcp@latest",
      "running": true,
      "pid": 12345
    },
    {
      "name": "chrome-devtools-mcp",
      "command": "npx chrome-devtools-mcp",
      "running": false,
      "pid": null
    }
  ],
  "summary": {
    "port_count": 7,
    "mcp_count": 3,
    "process_count": 5
  }
}
```

---

## Agent Hub Integration

### New Room: Ops Room

The Scout HQ row (currently full-width) is split 50/50:

```
┌──────────────────┬───────────────┐
│  JOB OFFICE      │  NEURAL CORE  │
│  💼 Job Agent    │  🧠 Brain     │
├─────────┬────────┴───────────────┤
│  STUDIO │  ROBLOX STUDIO         │
│  📱     │  🎮                    │
├─────────┴────┬───────────────────┤
│  SCOUT HQ    │  OPS ROOM         │
│  🧑‍💻        │  🖥️              │
└──────────────┴───────────────────┘
```

CSS grid change: row 3 uses `grid-template-columns` split instead of `grid-column: 1 / 3` span.

### `hub-config.yaml` entry

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

---

## File Structure

```
terminal-monitor/
├── termmon/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, background brain sync task
│   ├── scanner/
│   │   ├── __init__.py
│   │   ├── ports.py         # psutil port + process enumeration
│   │   ├── health.py        # httpx concurrent health pings
│   │   └── mcp.py           # ~/.claude/settings.json + process matching
│   └── brain.py             # NeuroLinked POST helpers
├── tests/
│   ├── test_ports.py
│   ├── test_health.py
│   ├── test_mcp.py
│   └── test_api.py
├── docs/
│   └── superpowers/
│       └── specs/
│           └── 2026-05-18-terminal-monitor-design.md
├── requirements.txt
├── pytest.ini
└── README.md
```

---

## Tech Stack

- Python 3.12 + FastAPI + uvicorn
- psutil (process + port enumeration)
- httpx (async health pings + brain sync)
- PyYAML (read hub-config.yaml for port labels)
- pytest + pytest-asyncio + respx (tests)

---

## Deferred (v2)

- `POST /api/kill/{pid}` — send SIGTERM to a process by PID
- `POST /api/restart/{id}` — kill + re-launch a known agent by hub config id
- WebSocket stream of port state changes into Agent Hub activity log
- Alert to brain when a known agent goes offline unexpectedly
