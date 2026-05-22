# Memory Server — Design Spec

**Date:** 2026-05-21
**Project:** Terminal Monitor (ops-platform feature 5 of 5)
**Status:** Approved — ready for implementation planning

---

## Goal

Give buyers a local, persistent knowledge store that makes Terminal Monitor progressively smarter over time — chat transcripts survive page reloads, command history is searchable, machine snapshots show how the layout evolves, and notes capture project context. For personal use, memory entries sync to NeuroLinked via the existing brain sync pipeline.

---

## Business Model

- Memory storage + chat auto-save: **MID+** ($29 one-time at launch)
- LLM context injection (memory makes AI smarter): **MID+**
- Shell history import + manual notes + machine snapshots: **MID+**
- Brain sync of memory entries + AI suggestions from history: **DIAMOND only** ($59 one-time at launch)
- Early adopter pricing — raise after establishing user base and social proof

---

## Architecture

### Approach

SQLite embedded in Terminal Monitor. No new process, no external dependency. `data/memory.db` lives alongside `data/history.ndjson` (already gitignored). New `termmon/memory.py` owns all DB access. Existing brain sync (`termmon/brain.py`) extended to push memory entries to NeuroLinked for Diamond users.

### Storage

**File:** `data/memory.db` (gitignored via `data/` entry)

**Table: `entries`**

| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PRIMARY KEY | autoincrement |
| `type` | TEXT | `chat`, `command`, `snapshot`, `note` |
| `content` | TEXT | the text content |
| `metadata` | TEXT | JSON blob — role, source, model, action, port_count, etc. |
| `source` | TEXT | `shell_import`, `termmon`, `user`, `auto` |
| `created_at` | TEXT | ISO 8601 timestamp |

Cap: `max_entries` total across all types (default 10,000). When the cap is hit, the oldest entry by `created_at` is pruned first, regardless of type.

### `config.yaml` addition

```yaml
memory:
  enabled: true
  max_entries: 10000
  shell_history_import: true   # auto-import on first startup if true
```

---

## Data Collection

### Chat transcripts (`type: "chat"`)

- **Auto-save:** every message sent or received in the AI tab is written immediately to `memory.db`. `source: "auto"`. Metadata: `{"role": "you"|"ai", "model": "<model-name>"}`.
- **Manual save:** "Save session" button in the MEMORY tab writes a session-boundary marker entry (`type: "note"`, `content: "--- session saved ---"`, `source: "user"`).
- Each message is its own row — not a whole conversation blob — so search works at message level.
- Requires MID+ license; if BASE license, chat still works but nothing is persisted.

### Command history (`type: "command"`)

- **Shell import:** on first startup with `shell_history_import: true`, reads:
  - `~/.bash_history` (Linux/Mac)
  - PowerShell history file at `(Get-PSReadLineOption).HistorySavePath` (Windows)
  - Deduplicates by `content` before inserting. `source: "shell_import"`.
  - Re-import available via `POST /api/memory/import-shell` (skips duplicates).
- **TM action logging:** when the user kills a process, restarts a service, or pulls an Ollama model through the dashboard — auto-logged. `source: "termmon"`. Metadata: `{"action": "kill"|"restart"|"model_pull", "target": "<name>", "result": "ok"|"error"}`.

### Machine snapshots (`type: "snapshot"`)

- **Auto-snapshot on startup:** one entry capturing `port_count`, `process_count`, `mcp_count`, `cpu_percent`, `ram_percent`. `source: "auto"`.
- **Manual snapshot:** "Snapshot now" button in MEMORY tab. `source: "user"`.
- Useful for tracking how machine layout changes over time.

### Notes (`type: "note"`)

- Freeform text written by the user in the MEMORY tab NOTES sub-tab.
- `source: "user"`. No metadata required.
- Listed below the editor, editable in-place.

---

## LLM Context Injection

On every `POST /api/chat` request, before building the system prompt, Terminal Monitor pulls from `memory.db`:

- Last 10 chat messages (`type: "chat"`)
- Last 20 commands (`type: "command"`, any source)
- Most recent machine snapshot (`type: "snapshot"`)

These are appended to the existing ops system prompt:

```
Recent conversation:
  [you] what is lsass.exe?
  [ai] lsass.exe is the Windows Local Security Authority process...

Recent commands:
  git push origin master
  python -m uvicorn main:app --port 8084
  ...

Last snapshot: ports=12, processes=47, MCP=3, CPU=34%, RAM=61%
```

Context is bounded — total injection capped at ~2,000 tokens to avoid breaking Ollama's context window.

Requires MID+ license. If BASE, `/api/chat` continues to work with no memory injection.

---

## Brain Sync Extension (Diamond)

The existing `brain.sync()` call in `termmon/brain.py` is extended:

- After pushing the scan snapshot to NeuroLinked, also push new memory entries added since the last sync.
- Only entries created after `app.state.last_memory_sync_ts` are sent.
- Each entry → `POST /api/claude/remember` with `{"text": entry.content, "source": "terminal-monitor", "tags": ["terminal-monitor", entry.type]}`.
- `app.state.last_memory_sync_ts` updated after successful push.
- Runs on the existing 60-second brain loop — no new background task needed.
- Diamond-only: if tier < DIAMOND, brain sync runs as before (scan only, no memory entries).

**AI suggestions from history (Diamond):** `GET /api/memory/insights` — queries NeuroLinked `/api/claude/search` for patterns in stored command and chat history, returns top suggestions. Falls back to local heuristics if brain is unavailable.

---

## Components

### `termmon/memory.py` (new)

- `init_db(db_path: Path) -> sqlite3.Connection` — creates table if not exists
- `add_entry(conn, type, content, metadata, source) -> int` — inserts, prunes if over cap
- `get_recent(conn, type: str | None, limit: int) -> list[dict]` — newest first
- `search(conn, query: str, limit: int) -> list[dict]` — LIKE search on `content`
- `delete_entry(conn, id: int) -> bool`
- `import_shell_history(conn) -> int` — returns count of new entries added
- `_get_shell_history_paths() -> list[Path]` — platform-aware, returns existing paths only

### `termmon/config.py` (modified)

Add `MemoryConfig` dataclass and `memory: MemoryConfig` field to `Settings`:

```python
class MemoryConfig(BaseModel):
    enabled: bool = True
    max_entries: int = 10000
    shell_history_import: bool = True
```

### `termmon/main.py` (modified)

**Lifespan** — after plugin loader init:
```python
if settings.memory.enabled:
    app.state.memory_conn = init_db(Path("data/memory.db"))
    if settings.memory.shell_history_import:
        import_shell_history(app.state.memory_conn)
    app.state.last_memory_sync_ts = datetime.utcnow().isoformat()
```

**`/api/chat` modification** — inject memory context into system prompt before Ollama/Claude call (MID+ only).

**New routes (all MID+):**

| Endpoint | Method | Description |
|---|---|---|
| `GET /api/memory` | GET | List entries — params: `type`, `limit`, `search` |
| `POST /api/memory` | POST | Add note: `{"type": "note", "content": "..."}` |
| `DELETE /api/memory/{id}` | DELETE | Remove single entry |
| `POST /api/memory/import-shell` | POST | Re-trigger shell history import |
| `GET /api/memory/export` | GET | Download full store as JSON |
| `GET /api/memory/insights` | GET | AI suggestions from history (Diamond only) |

**TM action logging** — existing kill/restart/model-pull handlers call `add_entry()` after their action completes.

### `termmon/brain.py` (modified)

Extend `sync()` to push new memory entries when tier == DIAMOND. New helper: `_push_memory_entries(conn, since_ts: str) -> str` — returns new timestamp after push.

### `termmon/dashboard.html` (modified)

**New MEMORY tab** added after AI tab, before plugin tabs.

Three sub-tabs:
- **HISTORY** — chronological feed, type badge, timestamp, search box, "Save session" button
- **NOTES** — text editor + save button + list of existing notes
- **COMMANDS** — deduplicated command log, "Re-import shell history" button

**`sendChat()` modification** — after successful AI response, call `_saveMessageToMemory("you", msg)` and `_saveMessageToMemory("ai", reply)` via `POST /api/memory`.

**`switchTab()` modification** — when switching to `"memory"` tab, load `GET /api/memory?limit=50` and render HISTORY sub-tab.

### `termmon-keygen.py` (not modified)

No changes — memory uses the same MID/Diamond tier gates already enforced by the license middleware.

---

## Runtime API

| Endpoint | Auth | Description |
|---|---|---|
| `GET /api/memory` | MID+ | List/search entries |
| `POST /api/memory` | MID+ | Add note |
| `DELETE /api/memory/{id}` | MID+ | Delete entry |
| `POST /api/memory/import-shell` | MID+ | Re-import shell history |
| `GET /api/memory/export` | MID+ | Export all as JSON |
| `GET /api/memory/insights` | DIAMOND | AI suggestions from history |

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `data/memory.db` cannot be created | Log warning, `app.state.memory_conn = None`; all memory routes return 503 |
| `memory.enabled: false` in config | Memory routes return 404; no DB opened |
| Shell history file does not exist | Skip silently — not all platforms have both |
| Shell history line is not valid UTF-8 | Skip line, continue import |
| `add_entry()` raises | Log warning, return without crashing caller |
| Brain sync memory push fails | Log warning, next sync retries from same timestamp |
| BASE license hits memory route | 403 via require_tier route dependency — same as other MID+ routes |

---

## Files Created / Modified

| File | Action |
|---|---|
| `termmon/memory.py` | Create |
| `termmon/config.py` | Modify — add `MemoryConfig`, `memory` field to `Settings` |
| `termmon/main.py` | Modify — lifespan init, `/api/memory` routes, chat injection, action logging |
| `termmon/brain.py` | Modify — push memory entries in Diamond sync |
| `termmon/dashboard.html` | Modify — MEMORY tab, sub-tabs, `sendChat()` save, `switchTab()` |
| `tests/test_memory.py` | Create |

---

## Testing

`tests/test_memory.py` covers:

- `init_db` creates table and returns connection
- `add_entry` inserts and returns id
- `add_entry` prunes oldest when `max_entries` exceeded
- `get_recent` returns newest first, filtered by type
- `search` returns entries matching content query
- `delete_entry` removes entry, returns True; returns False for missing id
- `import_shell_history` adds entries, deduplicates on re-run
- `import_shell_history` skips missing history files gracefully
- `GET /api/memory` returns entries (MID+), 403 for BASE
- `GET /api/memory?type=chat` filters by type
- `GET /api/memory?search=uvicorn` filters by content
- `POST /api/memory` stores a note, returns id
- `DELETE /api/memory/{id}` removes entry
- `POST /api/memory/import-shell` returns count of new entries
- `GET /api/memory/export` returns all entries as JSON list
- `GET /api/memory/insights` requires Diamond, returns suggestion list
- `/api/chat` system prompt includes recent memory context (MID+)
- `/api/chat` has no memory injection when BASE license
- Brain sync pushes memory entries when Diamond, skips when MID

---

## Security Notes

- `data/memory.db` is gitignored — personal command history and chat transcripts never reach the repo
- Shell history import reads only the user's own history files — no elevated permissions required
- Memory routes are behind existing license middleware — unauthenticated requests never reach DB
- `search` parameter uses parameterized SQL (`LIKE ? ` with `%query%`) — no SQL injection
- Chat transcripts may contain sensitive content; buyers are informed in docs that memory is local-only

---

## Out of Scope (v1)

- Semantic search / embeddings across memory entries
- Per-entry encryption
- Cross-agent memory sharing (standalone microservice — future project)
- Goal command (`/goal`) — sets active project context injected into AI (noted in Ideas/ops-brain-product.md)
- Memory export to training_seed.jsonl pipeline
- UI to edit existing notes in-place (create and delete only in v1)
