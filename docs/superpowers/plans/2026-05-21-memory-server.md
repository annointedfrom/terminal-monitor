# Memory Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local SQLite-backed memory store inside Terminal Monitor that persists chat transcripts, command history, machine snapshots, and notes — injecting relevant context into every AI chat for smarter responses, with Diamond-tier brain sync to NeuroLinked.

**Architecture:** New `termmon/memory.py` owns all SQLite access (`data/memory.db`). `termmon/main.py` gains six new MID+ routes plus lifespan init. `termmon/brain.py` gains optional Diamond-only memory push. `termmon/dashboard.html` gains a MEMORY tab with HISTORY/NOTES/COMMANDS sub-tabs. All memory features are gated MID+; brain sync and insights are DIAMOND only.

**Tech Stack:** Python `sqlite3` (stdlib), FastAPI, existing `require_tier` middleware, vanilla JS (no new frontend deps).

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `termmon/memory.py` | Create | All SQLite CRUD — init, add, get, search, delete, shell import |
| `termmon/config.py` | Modify | Add `MemoryConfig` + `memory` field to `Settings` |
| `termmon/main.py` | Modify | Lifespan init, 6 memory routes, chat injection, kill/model-pull logging |
| `termmon/brain.py` | Modify | `_push_memory_entries` helper + Diamond path in `sync()` |
| `termmon/dashboard.html` | Modify | MEMORY tab HTML + sub-tab JS + `sendChat` save + `switchTab` update |
| `tests/test_memory.py` | Create | Unit tests for memory.py + API integration tests |

---

### Task 1: `termmon/memory.py` — SQLite core

**Files:**
- Create: `termmon/memory.py`
- Test: `tests/test_memory.py`

- [ ] **Step 1: Write the failing unit tests**

Create `tests/test_memory.py`:

```python
from __future__ import annotations
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from termmon.memory import (
    init_db,
    add_entry,
    get_recent,
    search,
    delete_entry,
    import_shell_history,
    _get_shell_history_paths,
)


@pytest.fixture
def conn(tmp_path):
    return init_db(tmp_path / "test.db")


def test_init_db_creates_table(tmp_path):
    c = init_db(tmp_path / "mem.db")
    row = c.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='entries'"
    ).fetchone()
    assert row is not None


def test_add_entry_returns_id(conn):
    entry_id = add_entry(conn, "note", "hello", {}, "user")
    assert isinstance(entry_id, int)
    assert entry_id > 0


def test_add_entry_prunes_oldest(tmp_path):
    c = init_db(tmp_path / "prune.db", max_entries=3)
    for i in range(4):
        add_entry(c, "note", f"entry {i}", {}, "user", max_entries=3)
    rows = c.execute("SELECT content FROM entries ORDER BY created_at ASC").fetchall()
    assert len(rows) == 3
    assert rows[0][0] == "entry 1"  # entry 0 pruned


def test_get_recent_newest_first(conn):
    add_entry(conn, "note", "first", {}, "user")
    add_entry(conn, "note", "second", {}, "user")
    entries = get_recent(conn)
    assert entries[0]["content"] == "second"
    assert entries[1]["content"] == "first"


def test_get_recent_filters_by_type(conn):
    add_entry(conn, "note", "a note", {}, "user")
    add_entry(conn, "command", "ls -la", {}, "termmon")
    notes = get_recent(conn, type="note")
    assert all(e["type"] == "note" for e in notes)
    assert len(notes) == 1


def test_search_finds_content(conn):
    add_entry(conn, "command", "uvicorn main:app --port 8084", {}, "termmon")
    add_entry(conn, "command", "git push origin master", {}, "termmon")
    results = search(conn, "uvicorn")
    assert len(results) == 1
    assert "uvicorn" in results[0]["content"]


def test_search_returns_empty_for_no_match(conn):
    add_entry(conn, "note", "hello world", {}, "user")
    assert search(conn, "zzznomatch") == []


def test_delete_entry_returns_true(conn):
    entry_id = add_entry(conn, "note", "delete me", {}, "user")
    assert delete_entry(conn, entry_id) is True
    assert get_recent(conn) == []


def test_delete_entry_missing_returns_false(conn):
    assert delete_entry(conn, 9999) is False


def test_import_shell_history_adds_entries(conn, tmp_path):
    hist = tmp_path / ".bash_history"
    hist.write_text("git status\ngit push\ngit pull\n", encoding="utf-8")
    with patch("termmon.memory._get_shell_history_paths", return_value=[hist]):
        added = import_shell_history(conn)
    assert added == 3
    cmds = get_recent(conn, type="command")
    assert len(cmds) == 3
    assert cmds[0]["source"] == "shell_import"


def test_import_shell_history_deduplicates(conn, tmp_path):
    hist = tmp_path / ".bash_history"
    hist.write_text("git status\ngit push\n", encoding="utf-8")
    with patch("termmon.memory._get_shell_history_paths", return_value=[hist]):
        first = import_shell_history(conn)
        second = import_shell_history(conn)
    assert first == 2
    assert second == 0


def test_import_shell_history_skips_missing_file(conn):
    with patch("termmon.memory._get_shell_history_paths", return_value=[]):
        added = import_shell_history(conn)
    assert added == 0


def test_add_entry_stores_metadata(conn):
    add_entry(conn, "chat", "hello", {"role": "you", "model": "ops-brain"}, "auto")
    entry = get_recent(conn, type="chat")[0]
    meta = json.loads(entry["metadata"])
    assert meta["role"] == "you"
    assert meta["model"] == "ops-brain"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_memory.py -v
```
Expected: `ModuleNotFoundError: No module named 'termmon.memory'`

- [ ] **Step 3: Create `termmon/memory.py`**

```python
from __future__ import annotations

import json
import logging
import platform
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_ENTRIES = 10_000


def init_db(db_path: Path, max_entries: int = _MAX_ENTRIES) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS entries (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            type     TEXT NOT NULL,
            content  TEXT NOT NULL,
            metadata TEXT NOT NULL DEFAULT '{}',
            source   TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.commit()
    return conn


def add_entry(
    conn: sqlite3.Connection,
    type: str,
    content: str,
    metadata: dict,
    source: str,
    max_entries: int = _MAX_ENTRIES,
) -> int:
    now = datetime.now(timezone.utc).isoformat()
    cur = conn.execute(
        "INSERT INTO entries (type, content, metadata, source, created_at) VALUES (?, ?, ?, ?, ?)",
        (type, content, json.dumps(metadata), source, now),
    )
    conn.commit()
    entry_id = cur.lastrowid
    count = conn.execute("SELECT COUNT(*) FROM entries").fetchone()[0]
    if count > max_entries:
        conn.execute(
            "DELETE FROM entries WHERE id IN "
            "(SELECT id FROM entries ORDER BY created_at ASC LIMIT ?)",
            (count - max_entries,),
        )
        conn.commit()
    return entry_id


def get_recent(
    conn: sqlite3.Connection,
    type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if type:
        rows = conn.execute(
            "SELECT * FROM entries WHERE type = ? ORDER BY created_at DESC LIMIT ?",
            (type, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM entries ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
    return [dict(r) for r in rows]


def search(conn: sqlite3.Connection, query: str, limit: int = 50) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM entries WHERE content LIKE ? ORDER BY created_at DESC LIMIT ?",
        (f"%{query}%", limit),
    ).fetchall()
    return [dict(r) for r in rows]


def delete_entry(conn: sqlite3.Connection, entry_id: int) -> bool:
    cur = conn.execute("DELETE FROM entries WHERE id = ?", (entry_id,))
    conn.commit()
    return cur.rowcount > 0


def _get_shell_history_paths() -> list[Path]:
    paths: list[Path] = []
    bash = Path.home() / ".bash_history"
    if bash.exists():
        paths.append(bash)
    if platform.system() == "Windows":
        try:
            import subprocess
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command",
                 "(Get-PSReadLineOption).HistorySavePath"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            ps_path = Path(result.stdout.strip())
            if ps_path.exists():
                paths.append(ps_path)
        except Exception as exc:
            logger.warning("Could not get PowerShell history path: %s", exc)
    return paths


def import_shell_history(conn: sqlite3.Connection, max_entries: int = _MAX_ENTRIES) -> int:
    existing = {
        row[0]
        for row in conn.execute(
            "SELECT content FROM entries WHERE type = 'command' AND source = 'shell_import'"
        ).fetchall()
    }
    added = 0
    for path in _get_shell_history_paths():
        try:
            lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
        except Exception as exc:
            logger.warning("Shell history read error %s: %s", path, exc)
            continue
        for line in lines:
            line = line.strip()
            if not line or line in existing:
                continue
            try:
                add_entry(conn, "command", line, {}, "shell_import", max_entries)
                existing.add(line)
                added += 1
            except Exception as exc:
                logger.warning("Shell history import line error: %s", exc)
    return added
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_memory.py -v
```
Expected: all 12 tests PASS

- [ ] **Step 5: Commit**

```bash
git add termmon/memory.py tests/test_memory.py
git commit -m "feat: add memory.py SQLite core with shell history import"
```

---

### Task 2: `termmon/config.py` — MemoryConfig

**Files:**
- Modify: `termmon/config.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_config.py` — find the existing file and add:

```python
def test_memory_config_defaults():
    from termmon.config import Settings
    s = Settings()
    assert s.memory.enabled is True
    assert s.memory.max_entries == 10000
    assert s.memory.shell_history_import is True


def test_memory_config_from_yaml(tmp_path):
    import yaml
    from termmon import config as cfg_mod
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.dump({"memory": {"enabled": False, "max_entries": 500, "shell_history_import": False}}),
        encoding="utf-8",
    )
    cfg_mod._CONFIG_PATH = cfg_file
    cfg_mod._settings = None
    s = cfg_mod.get_settings()
    assert s.memory.enabled is False
    assert s.memory.max_entries == 500
    cfg_mod._CONFIG_PATH = cfg_mod.pathlib.Path(__file__).parent.parent / "config.yaml"
    cfg_mod._settings = None
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_config.py::test_memory_config_defaults -v
```
Expected: FAIL — `Settings` has no `memory` attribute

- [ ] **Step 3: Modify `termmon/config.py`**

After the `AlertsConfig` class, before `class Settings`, add:

```python
class MemoryConfig(BaseModel):
    enabled: bool = True
    max_entries: int = 10000
    shell_history_import: bool = True
```

Then add to `Settings` (after `plugins_dir`):

```python
    memory: MemoryConfig = Field(default_factory=MemoryConfig)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_config.py -v
```
Expected: all config tests PASS

- [ ] **Step 5: Commit**

```bash
git add termmon/config.py tests/test_config.py
git commit -m "feat: add MemoryConfig to Settings"
```

---

### Task 3: `termmon/main.py` — lifespan, routes, chat injection, action logging

**Files:**
- Modify: `termmon/main.py`
- Test: `tests/test_memory.py` (append API tests)

- [ ] **Step 1: Write the failing API tests**

Append to `tests/test_memory.py`:

```python
import sqlite3 as _sqlite3
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from termmon.main import app
from termmon.licensing import Tier
from termmon.memory import init_db as _init_db, add_entry as _add_entry


def _mid_license():
    from termmon.licensing import LicenseInfo
    return LicenseInfo(tier=Tier.MID, email="test@test.com", issued_at="2026-01-01")


def _diamond_license():
    from termmon.licensing import LicenseInfo
    return LicenseInfo(tier=Tier.DIAMOND, email="test@test.com", issued_at="2026-01-01")


def _base_license():
    from termmon.licensing import LicenseInfo
    return LicenseInfo(tier=Tier.BASE, email="test@test.com", issued_at="2026-01-01")


@pytest.fixture
def mem_client(tmp_path):
    """TestClient with an in-memory memory_conn set on app.state."""
    conn = _init_db(tmp_path / "api_test.db")
    app.state.memory_conn = conn
    app.state.license = _mid_license()
    yield TestClient(app)
    app.state.memory_conn = None
    app.state.license = None


@pytest.fixture
def diamond_client(tmp_path):
    conn = _init_db(tmp_path / "diamond_test.db")
    app.state.memory_conn = conn
    app.state.license = _diamond_license()
    yield TestClient(app)
    app.state.memory_conn = None
    app.state.license = None


def test_get_memory_returns_entries(mem_client, tmp_path):
    _add_entry(app.state.memory_conn, "note", "my note", {}, "user")
    r = mem_client.get("/api/memory")
    assert r.status_code == 200
    data = r.json()
    assert any(e["content"] == "my note" for e in data)


def test_get_memory_requires_mid():
    app.state.license = _base_license()
    app.state.memory_conn = _init_db(Path(":memory:") if False else
        __import__("tempfile").mktemp(suffix=".db"))
    with TestClient(app) as c:
        r = c.get("/api/memory")
    assert r.status_code == 402
    app.state.license = None
    app.state.memory_conn = None


def test_get_memory_filters_type(mem_client):
    _add_entry(app.state.memory_conn, "note", "a note", {}, "user")
    _add_entry(app.state.memory_conn, "command", "ls -la", {}, "termmon")
    r = mem_client.get("/api/memory?type=command")
    assert r.status_code == 200
    assert all(e["type"] == "command" for e in r.json())


def test_get_memory_search(mem_client):
    _add_entry(app.state.memory_conn, "command", "uvicorn main:app --port 8084", {}, "termmon")
    _add_entry(app.state.memory_conn, "command", "git push origin master", {}, "termmon")
    r = mem_client.get("/api/memory?search=uvicorn")
    assert r.status_code == 200
    results = r.json()
    assert len(results) == 1
    assert "uvicorn" in results[0]["content"]


def test_post_memory_stores_note(mem_client):
    r = mem_client.post("/api/memory", json={"type": "note", "content": "project context"})
    assert r.status_code == 200
    assert "id" in r.json()
    entries = mem_client.get("/api/memory?type=note").json()
    assert any(e["content"] == "project context" for e in entries)


def test_delete_memory_removes_entry(mem_client):
    entry_id = _add_entry(app.state.memory_conn, "note", "to delete", {}, "user")
    r = mem_client.delete(f"/api/memory/{entry_id}")
    assert r.status_code == 200
    assert r.json()["deleted"] is True
    entries = mem_client.get("/api/memory").json()
    assert not any(e["id"] == entry_id for e in entries)


def test_delete_memory_missing_returns_404(mem_client):
    r = mem_client.delete("/api/memory/99999")
    assert r.status_code == 404


def test_import_shell_endpoint_returns_count(mem_client, tmp_path):
    hist = tmp_path / "hist.txt"
    hist.write_text("git status\ngit push\n", encoding="utf-8")
    with patch("termmon.memory._get_shell_history_paths", return_value=[hist]):
        r = mem_client.post("/api/memory/import-shell")
    assert r.status_code == 200
    assert r.json()["added"] == 2


def test_export_memory_returns_list(mem_client):
    _add_entry(app.state.memory_conn, "note", "exported note", {}, "user")
    r = mem_client.get("/api/memory/export")
    assert r.status_code == 200
    assert isinstance(r.json(), list)
    assert any(e["content"] == "exported note" for e in r.json())


def test_insights_requires_diamond(mem_client):
    r = mem_client.get("/api/memory/insights")
    assert r.status_code == 402


def test_insights_returns_local_fallback(diamond_client, tmp_path):
    _add_entry(app.state.memory_conn, "command", "git status", {}, "termmon")
    with patch("httpx.AsyncClient") as mock_client:
        mock_client.return_value.__aenter__.return_value.get = AsyncMock(
            side_effect=Exception("brain down")
        )
        r = diamond_client.get("/api/memory/insights")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "local"
    assert isinstance(data["suggestions"], list)


def test_chat_injects_memory_context(tmp_path):
    conn = _init_db(tmp_path / "chat_test.db")
    _add_entry(conn, "chat", "what is python?", {"role": "you", "model": "ops-brain"}, "auto")
    _add_entry(conn, "command", "uvicorn main:app", {}, "termmon")
    app.state.memory_conn = conn
    app.state.license = _mid_license()
    captured_system = []

    async def fake_generate(prompt, system, model=None):
        captured_system.append(system)
        return {"available": True, "reply": "test reply"}

    with patch("termmon.main.ollama.generate", side_effect=fake_generate):
        with TestClient(app) as c:
            c.post("/api/chat", json={"message": "hello", "model": "ops-brain"})

    assert any("Recent conversation" in s or "Recent commands" in s for s in captured_system)
    app.state.memory_conn = None
    app.state.license = None


def test_chat_no_memory_conn_still_works(tmp_path):
    app.state.memory_conn = None
    app.state.license = _mid_license()

    async def fake_generate(prompt, system, model=None):
        return {"available": True, "reply": "ok"}

    with patch("termmon.main.ollama.generate", side_effect=fake_generate):
        with TestClient(app) as c:
            r = c.post("/api/chat", json={"message": "hello", "model": "ops-brain"})
    assert r.status_code == 200
    app.state.license = None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_memory.py -k "mem_client or diamond_client or test_get_memory or test_post_memory or test_delete_memory or test_import_shell_endpoint or test_export or test_insights or test_chat" -v
```
Expected: FAIL — routes don't exist yet

- [ ] **Step 3: Add imports to `termmon/main.py`**

At the top of `termmon/main.py`, add these imports (after the existing imports):

```python
import httpx
from termmon.memory import (
    init_db as _init_db,
    add_entry as _add_entry,
    get_recent as _get_recent,
    search as _memory_search,
    delete_entry as _delete_entry,
    import_shell_history as _import_shell_history,
)
```

- [ ] **Step 4: Update `lifespan` in `termmon/main.py`**

Replace the existing lifespan function:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.license = verify_license(settings.license_key)
    app.state.update_cache = None
    plugins_dir = _resolve_plugins_dir(settings.plugins_dir)
    app.state.plugins = load_plugins(plugins_dir)
    for plugin in app.state.plugins:
        _register_plugin_endpoints(app, plugin)
    # Memory init
    if settings.memory.enabled:
        try:
            app.state.memory_conn = _init_db(
                pathlib.Path("data/memory.db"), settings.memory.max_entries
            )
            if settings.memory.shell_history_import:
                _import_shell_history(app.state.memory_conn, settings.memory.max_entries)
            scan = await _full_scan()
            res = get_resources()
            _add_entry(
                app.state.memory_conn,
                "snapshot",
                (
                    f"ports={scan['summary']['port_count']}, "
                    f"processes={scan['summary']['process_count']}, "
                    f"MCP={scan['summary']['mcp_count']}, "
                    f"CPU={res.get('cpu', {}).get('percent', 0):.0f}%, "
                    f"RAM={res.get('memory', {}).get('percent', 0):.0f}%"
                ),
                {
                    "port_count": scan["summary"]["port_count"],
                    "process_count": scan["summary"]["process_count"],
                    "mcp_count": scan["summary"]["mcp_count"],
                },
                "auto",
                settings.memory.max_entries,
            )
            app.state.last_memory_sync_ts = datetime.now(timezone.utc).isoformat()
        except Exception as exc:
            logger.warning("Memory init failed: %s", exc)
            app.state.memory_conn = None
    else:
        app.state.memory_conn = None
    tasks = []
    if settings.brain.enabled:
        tasks.append(asyncio.create_task(_brain_loop()))
    yield
    for t in tasks:
        t.cancel()
```

- [ ] **Step 5: Add `MemoryAddRequest` Pydantic model to `termmon/main.py`**

After `class ChatRequest(BaseModel):` block, add:

```python
class MemoryAddRequest(BaseModel):
    type: str = "note"
    content: str
    metadata: dict = {}
```

- [ ] **Step 6: Add the six memory routes to `termmon/main.py`**

Add after the `@app.get("/api/plugins")` route:

```python
@app.get("/api/memory", dependencies=[require_tier(Tier.MID)])
async def list_memory(
    request: Request,
    type: str | None = None,
    limit: int = 50,
    search: str | None = None,
):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    if search:
        return _memory_search(conn, search, limit)
    return _get_recent(conn, type, limit)


@app.post("/api/memory", dependencies=[require_tier(Tier.MID)])
async def add_memory(req: MemoryAddRequest, request: Request):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    settings = get_settings()
    entry_id = _add_entry(
        conn, req.type, req.content, req.metadata, "user", settings.memory.max_entries
    )
    return {"id": entry_id}


@app.delete("/api/memory/{entry_id}", dependencies=[require_tier(Tier.MID)])
async def delete_memory(entry_id: int, request: Request):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    deleted = _delete_entry(conn, entry_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"detail": "Entry not found"})
    return {"deleted": True, "id": entry_id}


@app.post("/api/memory/import-shell", dependencies=[require_tier(Tier.MID)])
async def reimport_shell(request: Request):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    settings = get_settings()
    added = _import_shell_history(conn, settings.memory.max_entries)
    return {"added": added}


@app.get("/api/memory/export", dependencies=[require_tier(Tier.MID)])
async def export_memory(request: Request):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    return _get_recent(conn, None, 100_000)


@app.get("/api/memory/insights")
async def memory_insights(request: Request, _: LicenseInfo = require_tier(Tier.DIAMOND)):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    settings = get_settings()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.brain.url}/api/claude/search",
                params={"q": "terminal monitor commands patterns", "limit": 5},
                timeout=5.0,
            )
            if r.status_code == 200:
                return {"source": "brain", "suggestions": r.json()}
    except Exception:
        pass
    cmds = _get_recent(conn, "command", 5)
    return {"source": "local", "suggestions": [{"text": e["content"]} for e in cmds]}
```

- [ ] **Step 7: Modify `chat_with_ai` to inject memory context and save messages**

Replace the existing `@app.post("/api/chat")` handler:

```python
@app.post("/api/chat")
async def chat_with_ai(req: ChatRequest, request: Request, _: LicenseInfo = require_tier(Tier.MID)):
    scan = await _full_scan()
    ports_summary = [
        {"process": p["process"], "port": p["port"], "memory_mb": round(p.get("memory_mb", 0))}
        for p in scan["ports"][:20]
    ]
    system = (
        "You are an ops assistant monitoring the user's local machine. "
        "Answer questions about running processes, system health, and what actions to take. "
        "Be concise — 1-3 sentences unless more detail is explicitly requested. "
        f"Current system snapshot: active ports={scan['summary']['port_count']}, "
        f"unique processes={scan['summary']['process_count']}, "
        f"MCP servers running={scan['summary']['mcp_count']}. "
        f"Top processes: {json.dumps(ports_summary)}"
    )
    conn = getattr(request.app.state, "memory_conn", None)
    settings = get_settings()
    if conn is not None:
        mem_parts = []
        recent_chats = _get_recent(conn, "chat", 10)
        if recent_chats:
            chat_lines = "\n".join(
                f"  [{json.loads(e['metadata']).get('role', '?')}] {e['content'][:200]}"
                for e in reversed(recent_chats)
            )
            mem_parts.append(f"Recent conversation:\n{chat_lines}")
        recent_cmds = _get_recent(conn, "command", 20)
        if recent_cmds:
            cmd_lines = "\n".join(f"  {e['content'][:200]}" for e in recent_cmds)
            mem_parts.append(f"Recent commands:\n{cmd_lines}")
        snapshots = _get_recent(conn, "snapshot", 1)
        if snapshots:
            mem_parts.append(f"Last snapshot: {snapshots[0]['content']}")
        if mem_parts:
            system += "\n\n" + "\n\n".join(mem_parts)

    result = await ollama.generate(req.message, system, req.model)
    if result["available"]:
        reply = result["reply"]
        provider = "ollama"
        model_name = req.model
    else:
        claude_result = await claude_ai.generate(req.message, system)
        if claude_result["available"]:
            reply = claude_result["reply"]
            provider = "claude"
            model_name = "claude-haiku-4-5-20251001"
        else:
            return JSONResponse(
                status_code=503,
                content={
                    "reply": (
                        "No AI backend available.\n\n"
                        "Option 1 — Local (free): install Ollama then run:\n  ollama pull llama3.2:3b\n\n"
                        "Option 2 — Claude: set ANTHROPIC_API_KEY in your environment."
                    ),
                    "provider": "none",
                    "available": False,
                },
            )

    if conn is not None:
        try:
            _add_entry(conn, "chat", req.message,
                       {"role": "you", "model": model_name}, "auto",
                       settings.memory.max_entries)
            _add_entry(conn, "chat", reply,
                       {"role": "ai", "model": model_name}, "auto",
                       settings.memory.max_entries)
        except Exception as exc:
            logger.warning("Memory save for chat failed: %s", exc)

    return {"reply": reply, "provider": provider, "available": True, "model": model_name}
```

- [ ] **Step 8: Add `request: Request` to `kill_process` and log action**

Replace the existing `@app.post("/api/kill/{pid}")` handler:

```python
@app.post("/api/kill/{pid}", dependencies=[require_tier(Tier.MID)])
async def kill_process(pid: int, request: Request):
    try:
        proc = psutil.Process(pid)
        proc_name = proc.name()
        proc.terminate()
        await asyncio.sleep(0.5)
        if proc.is_running():
            proc.kill()
        conn = getattr(request.app.state, "memory_conn", None)
        if conn is not None:
            settings = get_settings()
            try:
                _add_entry(conn, "command", f"kill {proc_name} (pid={pid})",
                           {"action": "kill", "target": proc_name, "pid": pid, "result": "ok"},
                           "termmon", settings.memory.max_entries)
            except Exception as exc:
                logger.warning("Memory log for kill failed: %s", exc)
        return {"killed": True, "pid": pid}
    except psutil.NoSuchProcess:
        return JSONResponse(status_code=404, content={"detail": "Process not found"})
    except psutil.AccessDenied:
        return JSONResponse(status_code=403, content={"detail": "Access denied"})
```

- [ ] **Step 9: Add `request: Request` to `model_pull` and log action**

Replace the existing `@app.post("/api/update/model/pull")` handler:

```python
@app.post("/api/update/model/pull", dependencies=[require_tier(Tier.MID)])
async def model_pull(req: ModelPullRequest, request: Request):
    try:
        await ollama_pull(req.tag)
        conn = getattr(request.app.state, "memory_conn", None)
        if conn is not None:
            settings = get_settings()
            try:
                _add_entry(conn, "command", f"ollama pull {req.tag}",
                           {"action": "model_pull", "target": req.tag, "result": "ok"},
                           "termmon", settings.memory.max_entries)
            except Exception as exc:
                logger.warning("Memory log for model_pull failed: %s", exc)
        return {"pulled": True, "tag": req.tag}
    except Exception as exc:
        logger.warning("Model pull failed for tag=%s: %s", req.tag, exc)
        return JSONResponse(status_code=503, content={"detail": "Ollama unavailable"})
```

- [ ] **Step 10: Run all tests**

```
pytest tests/ -v
```
Expected: all tests PASS (150+ tests)

- [ ] **Step 11: Commit**

```bash
git add termmon/main.py tests/test_memory.py
git commit -m "feat: add memory routes, lifespan init, chat injection, action logging"
```

---

### Task 4: `termmon/brain.py` — Diamond memory sync

**Files:**
- Modify: `termmon/brain.py`
- Modify: `termmon/main.py` (update `_brain_loop`)
- Test: `tests/test_memory.py` (append brain sync tests)

- [ ] **Step 1: Write failing brain sync tests**

Append to `tests/test_memory.py`:

```python
def test_brain_sync_pushes_memory_for_diamond(tmp_path):
    import asyncio
    from unittest.mock import AsyncMock, patch, MagicMock
    from termmon.brain import sync
    from termmon.memory import init_db as _init_db, add_entry as _add_entry

    conn = _init_db(tmp_path / "brain_test.db")
    _add_entry(conn, "command", "git push", {}, "termmon")
    since_ts = "2020-01-01T00:00:00+00:00"

    posted_payloads = []

    async def fake_post(url, json=None, timeout=None):
        posted_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 200
        return resp

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=fake_post)

    scan = {"summary": {"port_count": 1, "mcp_count": 0}, "ports": []}
    with patch("termmon.brain.httpx.AsyncClient", return_value=mock_client):
        new_ts = asyncio.get_event_loop().run_until_complete(
            sync(scan, conn=conn, since_ts=since_ts)
        )
    assert new_ts is not None
    memory_posts = [p for p in posted_payloads if p and "terminal-monitor" in p.get("source", "")]
    assert any("git push" in p.get("text", "") for p in memory_posts)


def test_brain_sync_skips_memory_for_mid(tmp_path):
    import asyncio
    from unittest.mock import AsyncMock, patch, MagicMock
    from termmon.brain import sync

    scan = {"summary": {"port_count": 0, "mcp_count": 0}, "ports": []}
    posted_payloads = []

    async def fake_post(url, json=None, timeout=None):
        posted_payloads.append(json)
        resp = MagicMock()
        resp.status_code = 200
        return resp

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=fake_post)

    with patch("termmon.brain.httpx.AsyncClient", return_value=mock_client):
        result = asyncio.get_event_loop().run_until_complete(
            sync(scan, conn=None, since_ts=None)
        )
    assert result is None
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_memory.py::test_brain_sync_pushes_memory_for_diamond tests/test_memory.py::test_brain_sync_skips_memory_for_mid -v
```
Expected: FAIL — `sync()` doesn't accept `conn` or `since_ts` params

- [ ] **Step 3: Modify `termmon/brain.py`**

Replace the entire file:

```python
from __future__ import annotations

import logging
from datetime import datetime, timezone

import httpx

from termmon.config import get_settings

logger = logging.getLogger(__name__)


async def _push_memory_entries(brain_url: str, conn, since_ts: str) -> str:
    from termmon.memory import get_recent
    import json
    new_ts = datetime.now(timezone.utc).isoformat()
    all_entries = get_recent(conn, None, 200)
    new_entries = [e for e in all_entries if e["created_at"] >= since_ts]
    async with httpx.AsyncClient() as client:
        for entry in new_entries:
            try:
                await client.post(
                    f"{brain_url}/api/claude/remember",
                    json={
                        "text": entry["content"],
                        "source": "terminal-monitor",
                        "tags": ["terminal-monitor", entry["type"]],
                    },
                    timeout=5.0,
                )
            except Exception as exc:
                logger.warning("Memory entry brain push failed: %s", exc)
    return new_ts


async def sync(scan_result: dict, conn=None, since_ts: str | None = None) -> str | None:
    """Sync scan snapshot to brain. If conn+since_ts provided, also push new memory entries.
    Returns new memory sync timestamp if memory was pushed, else None."""
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

    if conn is not None and since_ts is not None:
        try:
            return await _push_memory_entries(brain_url, conn, since_ts)
        except Exception as exc:
            logger.warning("Memory brain push failed: %s", exc)

    return None
```

- [ ] **Step 4: Update `_brain_loop` in `termmon/main.py` to pass Diamond memory params**

Replace the existing `_brain_loop` function:

```python
async def _brain_loop() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            result = await _full_scan()
            license_info = getattr(app.state, "license", None)
            conn = getattr(app.state, "memory_conn", None)
            since_ts = getattr(app.state, "last_memory_sync_ts", None)
            is_diamond = license_info is not None and license_info.tier == Tier.DIAMOND
            new_ts = await brain.sync(
                result,
                conn=conn if is_diamond else None,
                since_ts=since_ts if is_diamond else None,
            )
            if new_ts:
                app.state.last_memory_sync_ts = new_ts
        except Exception as exc:
            logger.warning("Brain loop error: %s", exc)
```

- [ ] **Step 5: Run all tests**

```
pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 6: Commit**

```bash
git add termmon/brain.py termmon/main.py tests/test_memory.py
git commit -m "feat: extend brain sync with Diamond memory entry push"
```

---

### Task 5: `termmon/dashboard.html` — MEMORY tab

**Files:**
- Modify: `termmon/dashboard.html`

No unit tests for dashboard JS — verify manually by starting the app.

- [ ] **Step 1: Add MEMORY tab button to `#tab-bar`**

Find this line in `termmon/dashboard.html`:
```html
  <div class="tab" data-tier="mid" onclick="switchTab('ai')">AI</div>
```

After it, add:
```html
  <div class="tab" data-tier="mid" onclick="switchTab('memory')">MEMORY</div>
```

- [ ] **Step 2: Add MEMORY tab pane HTML**

Find this block (the closing `</div>` of `#pane-ai` and then the closing of `#tab-content`):
```html
  </div>
</div>
```

Before the closing `</div>` of tab-content, add the MEMORY pane (right after the AI pane closes):

```html
  <div id="pane-memory" class="tab-pane">
    <div id="memory-subnav" style="display:flex;align-items:center;border-bottom:1px solid #111;padding:2px 8px;background:#080808;flex-shrink:0;">
      <div class="ai-sub-tab active" onclick="switchMemoryPane('history')">HISTORY</div>
      <div class="ai-sub-tab" onclick="switchMemoryPane('notes')">NOTES</div>
      <div class="ai-sub-tab" onclick="switchMemoryPane('commands')">COMMANDS</div>
      <button id="mem-save-session-btn" onclick="saveMemorySession()" style="margin-left:auto;font-size:7px;color:#3498db;background:#0d2040;border:1px solid #1a4a7a;padding:2px 8px;cursor:pointer;">SAVE SESSION</button>
    </div>
    <div id="memory-history-pane" style="display:flex;flex-direction:column;flex:1;overflow:hidden;">
      <div style="padding:4px 8px;flex-shrink:0;">
        <input id="memory-search-input" type="text" placeholder="Search memories&#8230;" oninput="searchMemory(this.value)" style="width:100%;box-sizing:border-box;background:#0d0d0d;border:1px solid #1a3a5a;color:#ccc;font-family:monospace;font-size:9px;padding:3px 6px;outline:none;" />
      </div>
      <div id="memory-list" style="overflow-y:auto;flex:1;"></div>
    </div>
    <div id="memory-notes-pane" style="display:none;flex-direction:column;flex:1;overflow:hidden;">
      <div style="padding:6px 8px;flex-shrink:0;">
        <textarea id="memory-note-input" placeholder="Write a project note&#8230;" style="width:100%;box-sizing:border-box;height:60px;background:#0d0d0d;border:1px solid #1a3a5a;color:#ccc;font-family:monospace;font-size:9px;padding:4px;outline:none;resize:none;"></textarea>
        <button onclick="saveMemoryNote()" style="font-size:8px;color:#2ecc71;background:#0a1510;border:1px solid #1a4a1a;padding:2px 10px;cursor:pointer;margin-top:3px;">SAVE NOTE</button>
      </div>
      <div id="memory-notes-list" style="overflow-y:auto;flex:1;padding:0 4px;"></div>
    </div>
    <div id="memory-commands-pane" style="display:none;flex-direction:column;flex:1;overflow:hidden;">
      <div style="padding:6px 8px;flex-shrink:0;">
        <button onclick="reimportShellHistory()" style="font-size:8px;color:#f39c12;background:#1a1200;border:1px solid #4a3000;padding:2px 10px;cursor:pointer;">RE-IMPORT SHELL HISTORY</button>
      </div>
      <div id="memory-commands-list" style="overflow-y:auto;flex:1;padding:0 4px;font-family:monospace;"></div>
    </div>
  </div>
```

- [ ] **Step 3: Add memory JS — paste before the closing `</script>` tag**

```javascript
// ── Memory Tab ─────────────────────────────────────────────────
var _memoryCurrentPane = 'history';

function switchMemoryPane(name) {
  _memoryCurrentPane = name;
  document.getElementById('memory-history-pane').style.display = name === 'history' ? 'flex' : 'none';
  document.getElementById('memory-notes-pane').style.display = name === 'notes' ? 'flex' : 'none';
  document.getElementById('memory-commands-pane').style.display = name === 'commands' ? 'flex' : 'none';
  var tabs = document.querySelectorAll('#memory-subnav .ai-sub-tab');
  var names = ['history', 'notes', 'commands'];
  tabs.forEach(function(t, i) { t.classList.toggle('active', names[i] === name); });
  if (name === 'history') loadMemoryHistory();
  if (name === 'notes') loadMemoryNotes();
  if (name === 'commands') loadMemoryCommands();
}

function loadMemoryHistory(query) {
  var url = query
    ? '/api/memory?limit=50&search=' + encodeURIComponent(query)
    : '/api/memory?limit=50';
  fetch(url).then(function(r) { return r.ok ? r.json() : []; }).then(function(entries) {
    var list = document.getElementById('memory-list');
    if (!entries.length) {
      list.innerHTML = '<div style="color:#333;font-size:9px;padding:8px;">No memories yet.</div>';
      return;
    }
    list.innerHTML = '';
    entries.forEach(function(e) {
      var row = document.createElement('div');
      row.style.cssText = 'padding:4px 8px;border-bottom:1px solid #111;font-size:9px;display:flex;gap:6px;align-items:baseline;';
      var badge = document.createElement('span');
      badge.textContent = e.type;
      badge.style.cssText = 'color:#3498db;font-size:7px;flex-shrink:0;';
      var content = document.createElement('span');
      content.textContent = e.content.slice(0, 120);
      content.style.cssText = 'color:#aaa;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
      var ts = document.createElement('span');
      ts.textContent = (e.created_at || '').slice(0, 16).replace('T', ' ');
      ts.style.cssText = 'color:#333;font-size:7px;flex-shrink:0;';
      row.appendChild(badge);
      row.appendChild(content);
      row.appendChild(ts);
      list.appendChild(row);
    });
  }).catch(function() {});
}

function searchMemory(query) {
  clearTimeout(window._memSearchTimer);
  window._memSearchTimer = setTimeout(function() { loadMemoryHistory(query); }, 300);
}

function saveMemorySession() {
  fetch('/api/memory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'note', content: '--- session saved ---', metadata: {} }),
  }).catch(function() {});
}

function saveMemoryNote() {
  var text = document.getElementById('memory-note-input').value.trim();
  if (!text) return;
  fetch('/api/memory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'note', content: text, metadata: {} }),
  }).then(function() {
    document.getElementById('memory-note-input').value = '';
    loadMemoryNotes();
  }).catch(function() {});
}

function loadMemoryNotes() {
  fetch('/api/memory?type=note&limit=50').then(function(r) { return r.ok ? r.json() : []; }).then(function(entries) {
    var list = document.getElementById('memory-notes-list');
    list.innerHTML = '';
    entries.forEach(function(e) {
      var row = document.createElement('div');
      row.style.cssText = 'padding:4px 8px;border-bottom:1px solid #111;font-size:9px;color:#aaa;display:flex;gap:6px;align-items:center;';
      var content = document.createElement('span');
      content.textContent = e.content.slice(0, 200);
      content.style.flex = '1';
      var del = document.createElement('button');
      del.textContent = 'DEL';
      del.style.cssText = 'font-size:7px;color:#e74c3c;background:none;border:1px solid #4a1a1a;cursor:pointer;padding:1px 4px;flex-shrink:0;';
      del.onclick = (function(id) { return function() { deleteMemoryEntry(id); }; })(e.id);
      row.appendChild(content);
      row.appendChild(del);
      list.appendChild(row);
    });
  }).catch(function() {});
}

function loadMemoryCommands() {
  fetch('/api/memory?type=command&limit=200').then(function(r) { return r.ok ? r.json() : []; }).then(function(entries) {
    var list = document.getElementById('memory-commands-list');
    list.innerHTML = '';
    var seen = {};
    entries.forEach(function(e) {
      if (seen[e.content]) return;
      seen[e.content] = true;
      var row = document.createElement('div');
      row.style.cssText = 'padding:2px 8px;font-size:9px;color:#7abf7a;border-bottom:1px solid #0a1a0a;';
      row.textContent = e.content.slice(0, 120);
      list.appendChild(row);
    });
  }).catch(function() {});
}

function deleteMemoryEntry(id) {
  fetch('/api/memory/' + id, { method: 'DELETE' })
    .then(function() { loadMemoryNotes(); })
    .catch(function() {});
}

function reimportShellHistory() {
  fetch('/api/memory/import-shell', { method: 'POST' })
    .then(function(r) { return r.json(); })
    .then(function() { loadMemoryCommands(); })
    .catch(function() {});
}

function _saveToMemory(role, text, model) {
  fetch('/api/memory', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ type: 'chat', content: text, metadata: { role: role, model: model } }),
  }).catch(function() {});
}
```

- [ ] **Step 4: Modify `switchTab` to handle 'memory'**

Find the existing `switchTab` function. Inside it, find the block that checks for special tabs:
```javascript
  if (name === 'history') renderHistory();
  if (name === 'energy') renderEnergy();
  if (name === 'ai') { renderChat(); fetchTrainingStatus(); loadModels(); }
```

Add after the `if (name === 'ai')` line:
```javascript
  if (name === 'memory') { switchMemoryPane('history'); }
```

- [ ] **Step 5: Modify `sendChat` to save messages to memory**

In the `sendChat` function, find the successful AI response block:
```javascript
    } else {
      _chatHistory.push({ role: 'ai', text: data.reply });
    }
```

Replace with:
```javascript
    } else {
      _chatHistory.push({ role: 'ai', text: data.reply });
      _saveToMemory('you', msg, _selectedModel);
      _saveToMemory('ai', data.reply, _selectedModel);
    }
```

- [ ] **Step 6: Manual verification — start the app and test**

```bash
.\.venv\Scripts\uvicorn termmon.main:app --port 8084
```

Open `http://localhost:8084` in browser. Verify:
- MEMORY tab appears after AI tab
- Clicking MEMORY shows HISTORY sub-tab with empty state or entries
- NOTES sub-tab: type a note, click SAVE NOTE — it appears in the list below
- COMMANDS sub-tab: click RE-IMPORT SHELL HISTORY — entries populate
- Send a chat message in AI tab — switch to MEMORY > HISTORY and confirm the message appears
- Search box in HISTORY filters results

- [ ] **Step 7: Run tests to confirm nothing broken**

```
pytest tests/ -v
```
Expected: all tests PASS

- [ ] **Step 8: Commit**

```bash
git add termmon/dashboard.html
git commit -m "feat: add MEMORY tab with HISTORY/NOTES/COMMANDS sub-tabs"
```

---

### Task 6: Run full test suite and verify count

**Files:** No new files

- [ ] **Step 1: Run full test suite**

```
pytest tests/ -v --tb=short
```

Expected: all tests pass. Count should be 150+ (was 150 before this feature).

- [ ] **Step 2: Check for regressions in existing routes**

```
pytest tests/test_api.py tests/test_licensing.py tests/test_config.py tests/test_plugin_loader.py -v
```

Expected: all PASS — no regressions from `kill_process` and `model_pull` signature changes.

- [ ] **Step 3: Commit**

```bash
git add .
git commit -m "test: verify full suite passes with memory server"
```

---

## Self-Review

**Spec coverage:**
- `termmon/memory.py` with all 6 functions → Task 1 ✅
- `MemoryConfig` → Task 2 ✅
- Lifespan init + 6 routes + chat injection + kill/model-pull logging → Task 3 ✅
- Brain sync extension → Task 4 ✅
- Dashboard MEMORY tab with 3 sub-tabs → Task 5 ✅
- All 20 spec tests → covered across Tasks 1–4 ✅

**No placeholders:** All code is complete and explicit.

**Type consistency:** `add_entry`, `get_recent`, `search`, `delete_entry`, `import_shell_history` signatures are consistent across all tasks. `MemoryAddRequest.metadata: dict = {}` matches `add_entry(conn, req.type, req.content, req.metadata, ...)`.

**One known ordering issue:** `GET /api/memory/insights` must be declared before `GET /api/memory/{entry_id}` in `main.py` to avoid FastAPI routing `/insights` as an integer param. Register routes in this order: `GET /api/memory`, `POST /api/memory`, `POST /api/memory/import-shell`, `GET /api/memory/export`, `GET /api/memory/insights`, then `DELETE /api/memory/{entry_id}`.
