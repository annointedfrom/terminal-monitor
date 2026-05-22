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


import sqlite3 as _sqlite3
import tempfile
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
    conn = _init_db(tmp_path / "api_test.db")
    app.state.memory_conn = conn
    with patch("termmon.main.verify_license", return_value=_mid_license()):
        with TestClient(app) as client:
            yield client
    app.state.memory_conn = None
    app.state.license = None


@pytest.fixture
def diamond_client(tmp_path):
    conn = _init_db(tmp_path / "diamond_test.db")
    app.state.memory_conn = conn
    with patch("termmon.main.verify_license", return_value=_diamond_license()):
        with TestClient(app) as client:
            yield client
    app.state.memory_conn = None
    app.state.license = None


def test_get_memory_returns_entries(mem_client, tmp_path):
    _add_entry(app.state.memory_conn, "note", "my note", {}, "user")
    r = mem_client.get("/api/memory")
    assert r.status_code == 200
    data = r.json()
    assert any(e["content"] == "my note" for e in data)


def test_get_memory_requires_mid(tmp_path):
    conn = _init_db(tmp_path / "base_test.db")
    app.state.memory_conn = conn
    with patch("termmon.main.verify_license", return_value=_base_license()):
        with TestClient(app) as c:
            r = c.get("/api/memory")
    assert r.status_code == 403
    app.state.memory_conn = None
    app.state.license = None


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
    assert r.status_code == 403


def test_insights_returns_local_fallback(diamond_client):
    _add_entry(app.state.memory_conn, "command", "git status", {}, "termmon")
    with patch("httpx.AsyncClient") as mock_cls:
        mock_inst = MagicMock()
        mock_inst.__aenter__ = AsyncMock(return_value=mock_inst)
        mock_inst.__aexit__ = AsyncMock(return_value=False)
        mock_inst.get = AsyncMock(side_effect=Exception("brain down"))
        mock_cls.return_value = mock_inst
        r = diamond_client.get("/api/memory/insights")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "local"
    assert isinstance(data["suggestions"], list)


def test_chat_injects_memory_context(tmp_path):
    conn = _init_db(tmp_path / "chat_test.db")
    import json as _json
    _add_entry(conn, "chat", "what is python?", {"role": "you", "model": "ops-brain"}, "auto")
    _add_entry(conn, "command", "uvicorn main:app", {}, "termmon")
    app.state.memory_conn = conn
    captured = []

    async def fake_generate(prompt, system, model=None):
        captured.append(system)
        return {"available": True, "reply": "test reply"}

    with patch("termmon.main.verify_license", return_value=_mid_license()):
        with patch("termmon.main.ollama.generate", side_effect=fake_generate):
            with TestClient(app) as c:
                c.post("/api/chat", json={"message": "hello", "model": "ops-brain"})

    assert captured, "ollama.generate was never called"
    assert any(
        "Recent conversation" in s or "Recent commands" in s
        for s in captured
    ), f"Memory context not injected. System prompt: {captured}"
    app.state.memory_conn = None
    app.state.license = None


def test_chat_no_memory_conn_still_works():
    app.state.memory_conn = None

    async def fake_generate(prompt, system, model=None):
        return {"available": True, "reply": "ok"}

    with patch("termmon.main.verify_license", return_value=_mid_license()):
        with patch("termmon.main.ollama.generate", side_effect=fake_generate):
            with TestClient(app) as c:
                r = c.post("/api/chat", json={"message": "hello", "model": "ops-brain"})
    assert r.status_code == 200
    app.state.license = None


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
        new_ts = asyncio.run(sync(scan, conn=conn, since_ts=since_ts))
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
        result = asyncio.run(sync(scan, conn=None, since_ts=None))
    assert result is None
