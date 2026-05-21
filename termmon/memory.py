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
    entry_id: int = cur.lastrowid  # always non-None after a successful INSERT
    conn.execute(
        "DELETE FROM entries WHERE id NOT IN "
        "(SELECT id FROM entries ORDER BY created_at DESC LIMIT ?)",
        (max_entries,),
    )
    conn.commit()
    return entry_id


def get_recent(
    conn: sqlite3.Connection,
    type: str | None = None,
    limit: int = 50,
) -> list[dict]:
    if type is not None:
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
