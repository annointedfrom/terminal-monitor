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
