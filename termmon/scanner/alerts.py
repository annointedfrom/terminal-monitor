from __future__ import annotations

from termmon.config import Settings

_HIGH_SEVERITY_CUTOFF = 90


def evaluate_alerts(scan: dict, resources: dict, settings: Settings) -> list[dict]:
    alerts: list[dict] = []
    cfg = settings.alerts

    cpu = resources.get("cpu_percent", 0.0)
    if cpu >= cfg.cpu_threshold:
        alerts.append({
            "id": f"cpu_{int(cpu)}",
            "severity": "high" if cpu >= _HIGH_SEVERITY_CUTOFF else "warn",
            "message": f"CPU at {cpu:.1f}%",
        })

    ram = (resources.get("memory") or {}).get("percent", 0.0)
    if ram >= cfg.ram_threshold:
        alerts.append({
            "id": f"ram_{int(ram)}",
            "severity": "high" if ram >= _HIGH_SEVERITY_CUTOFF else "warn",
            "message": f"RAM at {ram:.1f}%",
        })

    gpu_temp = resources.get("gpu_temp_c")
    if isinstance(gpu_temp, (int, float)) and gpu_temp >= cfg.gpu_temp_threshold:
        alerts.append({
            "id": f"gpu_temp_{int(gpu_temp)}",
            "severity": "high" if gpu_temp >= _HIGH_SEVERITY_CUTOFF else "warn",
            "message": f"GPU temp at {gpu_temp:.0f}°C",
        })

    if cfg.offline_notify:
        healthy_ports = {
            p["port"]
            for p in scan.get("ports", [])
            if p.get("healthy", False)
        }
        for svc in settings.services:
            if svc.port not in healthy_ports:
                slug = svc.name.lower().replace(" ", "-")
                alerts.append({
                    "id": f"service_offline_{slug}",
                    "severity": "high",
                    "message": f"{svc.name} offline",
                })

    return alerts
