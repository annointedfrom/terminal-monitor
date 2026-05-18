from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import psutil

logger = logging.getLogger(__name__)


def _settings_path() -> Path:
    return Path.home() / ".claude" / "settings.json"


def _read_mcp_config(settings_path: Path) -> dict[str, dict]:
    try:
        with open(settings_path, encoding="utf-8") as f:
            data = json.load(f)
        return data.get("mcpServers", {})
    except (FileNotFoundError, OSError, json.JSONDecodeError, KeyError, TypeError) as exc:
        logger.debug("Could not read MCP config from %s: %s", settings_path, exc)
        return {}


def _find_process(token: str) -> tuple[bool, Optional[int]]:
    token_lower = token.lower()
    for proc in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            cmdline = " ".join(proc.info["cmdline"] or []).lower()
            if token_lower in cmdline:
                return True, proc.info["pid"]
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    return False, None


def scan_mcp(settings_path: Optional[Path] = None) -> list[dict]:
    if settings_path is None:
        settings_path = _settings_path()
    servers = _read_mcp_config(settings_path)

    results = []
    for name, config in servers.items():
        command = config.get("command", "")
        args = config.get("args", [])

        search_token = name
        for arg in reversed(args):
            if not arg.startswith("-") and len(arg) > 2:
                search_token = arg
                break

        running, pid = _find_process(search_token)
        full_command = f"{command} {' '.join(str(a) for a in args)}".strip()
        results.append({
            "name": name,
            "command": full_command,
            "running": running,
            "pid": pid,
        })

    return results
