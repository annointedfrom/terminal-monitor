from __future__ import annotations

import logging

import httpx

from termmon.config import get_settings

logger = logging.getLogger(__name__)


async def sync(scan_result: dict) -> None:
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
