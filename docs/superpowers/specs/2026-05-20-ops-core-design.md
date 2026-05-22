# ops-core Design Spec

**Goal:** Complete Terminal Monitor as a shippable, personal-data-free base product with config-driven personalization, persistent history, proactive alerts, and a first-run setup wizard.

**Architecture:** Single `config.yaml` drives all personal values. A Pydantic config module loads it at startup and exposes non-sensitive settings to the frontend via `/api/config`. Personal files are gitignored. Buyers get `config.example.yaml` and a setup wizard.

**Tech Stack:** FastAPI, Pydantic, psutil, NDJSON (stdlib), Browser Notification API, Python CLI (stdlib only)

---

## 1. Config Layer

### Files

| File | Ships? | Purpose |
|---|---|---|
| `config.yaml` | No (gitignored) | Personal values — ports, model, brain URL |
| `config.example.yaml` | Yes | Safe defaults, buyer template |
| `termmon/config.py` | Yes | Pydantic model, loader, singleton |

### Schema

```yaml
dashboard:
  title: "Ops Dashboard"
  default_model: "ops-brain"
  training_threshold: 100

brain:
  enabled: false
  url: "http://localhost:8000"

services:
  - name: "my-agent"
    port: 8090

alerts:
  cpu_threshold: 80
  ram_threshold: 80
  gpu_temp_threshold: 80
  offline_notify: true
```

### Implementation

`termmon/config.py` defines a `Settings` Pydantic model with nested models for each block. All fields have defaults — a missing or empty `config.yaml` produces a fully working app. The module exposes a `get_settings()` function that loads once and caches. `main.py` calls it during lifespan startup.

A new `/api/config` GET endpoint returns dashboard-safe settings (title, default_model, services list). The frontend loads this once on startup and replaces the hardcoded `MCP_PORT_MAP`.

### Security Fixes Included

- `dashboard.html`: remove hardcoded `MCP_PORT_MAP = { 'neurolinked-brain': 8000, 'obsidian': 27123 }`. Replace with values fetched from `/api/config` on load.
- `brain.py`: URL reads from `settings.brain.url`. The sync loop in `main.py` only starts if `settings.brain.enabled` is true.
- `proc_desc.json`: remove duplicate `Obsidian.exe` entry.

---

## 2. First-Run Setup Wizard

### CLI (`setup.py`)

- Runs in the terminal: `python setup.py`
- Prompts: dashboard title, Ollama model, brain sync on/off (if yes, URL), services (name + port, repeatable)
- Writes `config.yaml` on completion
- If `config.yaml` already exists, asks before overwriting
- No external dependencies — stdlib only

### Web Wizard (`/setup`)

- FastAPI serves a self-contained HTML setup page at `/setup`
- Auto-redirects from `/dashboard` if no `config.yaml` exists
- Form fields mirror the CLI questions
- `POST /api/setup` receives form data, validates, writes `config.yaml`, returns redirect to `/dashboard`
- If `config.yaml` exists, `/setup` shows current values as an edit form (not just first-run)

### Shared Output

Both write identical `config.yaml`. Either path produces the same result.

---

## 3. History Persistence

### Storage

- `data/` directory at project root, created automatically, gitignored
- `data/scan_history.jsonl` — one JSON object per line, appended each scan
- `data/resource_history.jsonl` — one JSON object per line, appended each resource poll
- Rolling cap: 500 entries per file (oldest dropped when limit reached)

### Startup Load

`termmon/scanner/history.py` exposes:
- `load_scan_history(n=30) -> list[dict]`
- `load_resource_history(n=30) -> list[dict]`
- `append_scan(entry: dict) -> None`
- `append_resource(entry: dict) -> None`

A `/api/history` GET endpoint returns `{ scan: [...last 30], resources: [...last 30] }`. The frontend calls it once on page load alongside the first `/api/scan`, merging the results into `_scanHistory` and `_resHistory` before rendering. This means the HISTORY and ENERGY tabs have data immediately on first load.

### Frontend

No structural changes. The seed data from `/api/scan` populates `_scanHistory` and `_resHistory` the same way live scans do. The HISTORY tab and ENERGY sparklines work from first page load.

---

## 4. Proactive Alerts

### Backend

`GET /api/alerts/current` evaluates the latest cached scan and resource data against thresholds from `config.yaml`. Returns:

```json
{
  "alerts": [
    { "id": "service_offline_agent-hub", "severity": "high", "message": "Agent Hub offline" },
    { "id": "ram_87", "severity": "warn", "message": "RAM at 87%" }
  ]
}
```

Alert IDs are deterministic (based on condition + subject) so the frontend can deduplicate across polls.

### Frontend

On first dashboard load, request `Notification.requestPermission()`. Store grant/deny in localStorage — don't ask again if denied.

A background poller runs `setInterval` every 30 seconds regardless of active tab. On each poll:
1. Fetch `/api/alerts/current`
2. Compare returned alert IDs to `_activeAlertIds` (Set)
3. For any new ID: fire `new Notification(message)`, add to Set
4. For any ID no longer present: remove from Set (condition cleared)

Result: one notification per condition per occurrence. No repeat spam. Works when dashboard is minimized.

Thresholds come from `/api/config`. `offline_notify: false` skips service offline checks entirely.

---

## 5. Clean Build

### `.gitignore` Additions

```
config.yaml
data/
models/Modelfile
models/training_seed.jsonl
models/checkpoints/
models/*.gguf
models/Modelfile.generated
```

### Ships

- `config.example.yaml` — blank template with inline comments
- `models/Modelfile.template` — buyer personalizes via `generate_modelfile.py`
- `models/README.md`
- `setup.py` CLI wizard
- All source code (zero personal references after fixes above)
- `docs/` — user-facing documentation

### Buyer Flow

1. Download zip / clone repo
2. Run `python setup.py` or open `http://localhost:8084/setup`
3. Answer 4-5 questions → `config.yaml` written
4. Start server: `python -m uvicorn termmon.main:app --port 8084`
5. Open dashboard — personal to their machine, zero of your data present

---

## Out of Scope (future ops-platform)

- Docker packaging
- Tiered licensing (Base / Mid / Diamond)
- Update server for LLM model pushes
- Plugin architecture for third-party agents
- Custom memory server (replacement for NeuroLinked dependency)
