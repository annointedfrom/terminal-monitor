from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Optional

import psutil
import yaml

logger = logging.getLogger(__name__)


def _load_labels(hub_config_path: Path) -> dict[int, str]:
    try:
        with open(hub_config_path, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        return {a["port"]: a["name"] for a in data.get("agents", [])}
    except (FileNotFoundError, OSError, yaml.YAMLError, KeyError, TypeError) as exc:
        logger.debug("Could not load labels from %s: %s", hub_config_path, exc)
        return {}


def scan_ports(hub_config_path: Optional[Path] = None) -> list[dict]:
    if hub_config_path is None:
        hub_config_path = (
            Path(__file__).parent.parent.parent.parent / "agent-hub" / "hub-config.yaml"
        )
    labels = _load_labels(hub_config_path)

    results = []
    seen_ports: set[int] = set()

    for conn in psutil.net_connections(kind="inet"):
        if conn.status != "LISTEN":
            continue
        port = conn.laddr.port
        if port in seen_ports:
            continue
        seen_ports.add(port)

        pid = conn.pid
        process_name = "unknown"
        memory_mb = 0.0
        uptime_s = 0

        if pid:
            try:
                proc = psutil.Process(pid)
                process_name = proc.name()
                memory_mb = round(proc.memory_info().rss / 1024 / 1024, 1)
                uptime_s = int(time.time() - proc.create_time())
            except (psutil.NoSuchProcess, psutil.AccessDenied):
                pass

        results.append({
            "port": port,
            "pid": pid,
            "process": process_name,
            "memory_mb": memory_mb,
            "uptime_s": uptime_s,
            "healthy": False,
            "label": labels.get(port, ""),
        })

    return sorted(results, key=lambda x: x["port"])
