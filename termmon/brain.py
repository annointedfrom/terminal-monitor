from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timezone

import httpx

from termmon.config import get_settings
from termmon.memory import get_recent

logger = logging.getLogger(__name__)


async def _push_memory_entries(
    brain_url: str,
    conn: sqlite3.Connection,
    since_ts: str,
) -> str:
    """Fetch entries created after since_ts and POST each to the brain.

    Returns a new ISO timestamp representing the sync time.
    """
    all_entries = get_recent(conn, None, 200)
    # ISO 8601 strings sort correctly as strings — no datetime parsing needed
    to_push = [e for e in all_entries if e["created_at"] >= since_ts]

    async with httpx.AsyncClient() as client:
        for entry in to_push:
            try:
                resp = await client.post(
                    f"{brain_url}/api/claude/remember",
                    json={
                        "text": entry["content"],
                        "source": "terminal-monitor",
                        "tags": ["terminal-monitor", entry["type"]],
                    },
                    timeout=5.0,
                )
                resp.raise_for_status()
            except Exception as exc:
                logger.warning("Brain memory-entry push failed for entry %s: %s", entry.get("id"), exc)

    return datetime.now(timezone.utc).isoformat()


async def sync(
    scan_result: dict,
    conn: sqlite3.Connection | None = None,
    since_ts: str | None = None,
) -> str | None:
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
            new_ts = await _push_memory_entries(brain_url, conn, since_ts)
            return new_ts
        except Exception as exc:
            logger.warning("Brain memory-entries push failed: %s", exc)

    return None
