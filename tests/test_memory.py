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
