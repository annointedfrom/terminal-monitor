from __future__ import annotations

import pathlib
from typing import Optional

import yaml
from pydantic import BaseModel, Field

_CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.yaml"


class DashboardConfig(BaseModel):
    title: str = "Ops Dashboard"
    default_model: str = "ops-brain"
    training_threshold: int = 100


class BrainConfig(BaseModel):
    enabled: bool = False
    url: str = "http://localhost:8000"


class ServiceConfig(BaseModel):
    name: str
    port: int
    start_command: Optional[str] = None


class AlertsConfig(BaseModel):
    cpu_threshold: int = 80
    ram_threshold: int = 80
    gpu_temp_threshold: int = 80
    offline_notify: bool = True


class Settings(BaseModel):
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    brain: BrainConfig = Field(default_factory=BrainConfig)
    services: list[ServiceConfig] = Field(default_factory=list)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    license_key: str = ""


_settings: Optional[Settings] = None


def _load() -> Settings:
    if not _CONFIG_PATH.exists():
        return Settings()
    raw = yaml.safe_load(_CONFIG_PATH.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raw = {}
    return Settings.model_validate(raw)


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = _load()
    return _settings


def reload_settings() -> Settings:
    global _settings
    _settings = _load()
    return _settings


def write_settings(settings: Settings) -> None:
    _CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    data = settings.model_dump()
    _CONFIG_PATH.write_text(
        yaml.dump(data, default_flow_style=False, allow_unicode=True),
        encoding="utf-8",
    )
    reload_settings()
