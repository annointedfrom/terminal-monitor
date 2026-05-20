from __future__ import annotations

import os
import subprocess
from datetime import datetime, timezone

import psutil


def _nvidia_smi() -> list[dict] | None:
    try:
        r = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,temperature.gpu,utilization.gpu,memory.used,memory.total,power.draw",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=4,
        )
        if r.returncode != 0 or not r.stdout.strip():
            return None
        gpus = []
        for line in r.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) < 6:
                continue
            def _f(v):
                try:
                    return float(v)
                except (ValueError, TypeError):
                    return None
            gpus.append({
                "name": parts[0],
                "temp_c": _f(parts[1]),
                "util_pct": _f(parts[2]),
                "vram_used_mb": _f(parts[3]),
                "vram_total_mb": _f(parts[4]),
                "power_w": _f(parts[5]),
            })
        return gpus or None
    except Exception:
        return None


def get_resources() -> dict:
    per_core = psutil.cpu_percent(percpu=True, interval=None)
    cpu_overall = round(sum(per_core) / len(per_core), 1) if per_core else 0.0

    freq = psutil.cpu_freq()
    mem = psutil.virtual_memory()
    disk_path = "C:\\" if os.name == "nt" else "/"
    disk = psutil.disk_usage(disk_path)

    result: dict = {
        "cpu_percent": cpu_overall,
        "cpu_freq_mhz": round(freq.current) if freq else None,
        "cpu_freq_max_mhz": round(freq.max) if freq else None,
        "cpu_cores": len(per_core),
        "cpu_per_core": [round(v, 1) for v in per_core],
        "memory": {
            "total": mem.total,
            "available": mem.available,
            "percent": mem.percent,
            "used": mem.used,
        },
        "disk": {
            "total": disk.total,
            "used": disk.used,
            "free": disk.free,
            "percent": disk.percent,
        },
    }

    gpus = _nvidia_smi()
    if gpus:
        result["gpus"] = gpus

    result["recorded_at"] = datetime.now(timezone.utc).isoformat()

    return result
