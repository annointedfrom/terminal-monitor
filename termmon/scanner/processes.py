from __future__ import annotations

import time
from typing import Optional

import psutil

_SKIP_NAMES: frozenset[str] = frozenset({
    "system", "registry", "idle", "system idle process",
    "smss.exe", "csrss.exe", "wininit.exe", "services.exe", "lsass.exe",
    "svchost.exe", "fontdrvhost.exe", "dllhost.exe", "sihost.exe",
    "taskhostw.exe", "runtimebroker.exe", "searchindexer.exe",
    "wudfhost.exe", "wmiprvse.exe", "audiodg.exe", "spoolsv.exe",
    "ctfmon.exe", "dwm.exe", "winlogon.exe", "securityhealthservice.exe",
    "nissrv.exe", "sgrmbroker.exe", "msmpeng.exe", "trustedinstaller.exe",
    "tiworker.exe", "wininit.exe", "wlms.exe", "tabletinputservice.exe",
    "tabtip.exe", "textinputhost.exe",
})
_MIN_MB = 5.0
_MAX_RESULTS = 25


def scan_background_processes(exclude_pids: Optional[set] = None) -> list[dict]:
    if exclude_pids is None:
        exclude_pids = set()

    results: list[dict] = []
    for proc in psutil.process_iter(["pid", "name", "memory_info", "create_time"]):
        try:
            info = proc.info
            pid = info["pid"]
            if not pid or pid in exclude_pids:
                continue
            name: str = info["name"] or ""
            if name.lower() in _SKIP_NAMES:
                continue
            mem_bytes = info["memory_info"].rss if info["memory_info"] else 0
            memory_mb = round(mem_bytes / 1024 / 1024, 1)
            if memory_mb < _MIN_MB:
                continue
            uptime_s = int(time.time() - info["create_time"]) if info["create_time"] else 0
            results.append({
                "port": None,
                "pid": pid,
                "process": name,
                "memory_mb": memory_mb,
                "uptime_s": uptime_s,
                "healthy": None,
                "label": "",
                "background": True,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue

    results.sort(key=lambda x: x["memory_mb"], reverse=True)
    return results[:_MAX_RESULTS]
