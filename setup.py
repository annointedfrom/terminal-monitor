#!/usr/bin/env python
"""First-run setup wizard — writes config.yaml. Run: python setup.py"""
from __future__ import annotations

import pathlib
import sys

_CONFIG_PATH = pathlib.Path(__file__).parent / "config.yaml"


def _build_config(
    title: str, default_model: str, training_threshold: int,
    brain_enabled: bool, brain_url: str, services: list[dict],
    cpu_threshold: int, ram_threshold: int, gpu_temp_threshold: int,
    offline_notify: bool,
) -> dict:
    return {
        "dashboard": {
            "title": title,
            "default_model": default_model,
            "training_threshold": training_threshold,
        },
        "brain": {"enabled": brain_enabled, "url": brain_url},
        "services": services,
        "alerts": {
            "cpu_threshold": cpu_threshold,
            "ram_threshold": ram_threshold,
            "gpu_temp_threshold": gpu_temp_threshold,
            "offline_notify": offline_notify,
        },
    }


def _write_config(cfg: dict, path: pathlib.Path) -> None:
    try:
        import yaml
        text = yaml.dump(cfg, default_flow_style=False, allow_unicode=True)
    except ImportError:
        lines = [
            "dashboard:",
            f'  title: "{cfg["dashboard"]["title"]}"',
            f'  default_model: "{cfg["dashboard"]["default_model"]}"',
            f'  training_threshold: {cfg["dashboard"]["training_threshold"]}',
            "brain:",
            f'  enabled: {str(cfg["brain"]["enabled"]).lower()}',
            f'  url: "{cfg["brain"]["url"]}"',
            "services: []",
            "alerts:",
            f'  cpu_threshold: {cfg["alerts"]["cpu_threshold"]}',
            f'  ram_threshold: {cfg["alerts"]["ram_threshold"]}',
            f'  gpu_temp_threshold: {cfg["alerts"]["gpu_temp_threshold"]}',
            f'  offline_notify: {str(cfg["alerts"]["offline_notify"]).lower()}',
        ]
        text = "\n".join(lines) + "\n"
    path.write_text(text, encoding="utf-8")


def _ask(prompt: str, default: str) -> str:
    val = input(f"{prompt} [{default}]: ").strip()
    return val if val else default


def _ask_int(prompt: str, default: int) -> int:
    while True:
        val = input(f"{prompt} [{default}]: ").strip()
        if not val:
            return default
        try:
            return int(val)
        except ValueError:
            print("  Enter a whole number.")


def _ask_bool(prompt: str, default: bool) -> bool:
    val = input(f"{prompt} [{'Y/n' if default else 'y/N'}]: ").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


def _collect_services() -> list[dict]:
    services: list[dict] = []
    print("\nServices to monitor (blank name to finish):")
    while True:
        name = input("  Name: ").strip()
        if not name:
            break
        port = _ask_int("  Port", 8080)
        cmd = input("  Start command (optional): ").strip() or None
        entry: dict = {"name": name, "port": port}
        if cmd:
            entry["start_command"] = cmd
        services.append(entry)
    return services


def main(config_path: pathlib.Path = _CONFIG_PATH) -> None:
    print("=" * 50)
    print("  Terminal Monitor — First-Run Setup")
    print("=" * 50)

    if config_path.exists():
        if not _ask_bool("config.yaml exists. Overwrite?", False):
            print("Cancelled — existing config kept.")
            sys.exit(0)

    print()
    title = _ask("Dashboard title", "Ops Dashboard")
    model = _ask("Default Ollama model", "ops-brain")
    threshold = _ask_int("Training pair threshold", 100)

    print()
    brain = _ask_bool("Enable brain sync?", False)
    brain_url = "http://localhost:8000"
    if brain:
        brain_url = _ask("Brain URL", "http://localhost:8000")

    services = _collect_services()

    print("\nAlert thresholds:")
    cpu_t = _ask_int("  CPU %", 80)
    ram_t = _ask_int("  RAM %", 80)
    gpu_t = _ask_int("  GPU temp degC", 80)
    offline_n = _ask_bool("  Notify when services go offline?", True)

    cfg = _build_config(
        title=title, default_model=model, training_threshold=threshold,
        brain_enabled=brain, brain_url=brain_url, services=services,
        cpu_threshold=cpu_t, ram_threshold=ram_t, gpu_temp_threshold=gpu_t,
        offline_notify=offline_n,
    )
    _write_config(cfg, config_path)

    print(f"\n  Written to {config_path}")
    print("  Start: python -m uvicorn termmon.main:app --port 8084")
    print("  Open:  http://localhost:8084/dashboard")


if __name__ == "__main__":
    main()
