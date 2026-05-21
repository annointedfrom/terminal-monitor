from __future__ import annotations

import importlib.util
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType

from termmon.licensing import verify_plugin_key

logger = logging.getLogger(__name__)


@dataclass
class PluginMeta:
    name: str
    label: str
    version: str
    description: str
    min_tier: str
    has_tab: bool
    author: str


class LoadedPlugin:
    def __init__(self, meta: PluginMeta, module: ModuleType, plugin_dir: Path) -> None:
        self.meta = meta
        self.module = module
        self.plugin_dir = plugin_dir

    def scan(self) -> dict:
        return self.module.scan()

    def tab_html(self) -> str | None:
        tab_path = self.plugin_dir / "tab.html"
        if tab_path.exists():
            return tab_path.read_text(encoding="utf-8")
        return None

    def has_router(self) -> bool:
        return hasattr(self.module, "router")

    def get_router(self):
        if self.has_router():
            return self.module.router()
        return None


def _resolve_plugins_dir(config_plugins_dir: str | None) -> Path:
    if config_plugins_dir:
        return Path(config_plugins_dir)
    return Path(__file__).parent.parent / "plugins"


def load_plugins(plugins_dir: Path) -> list[LoadedPlugin]:
    if not plugins_dir.exists():
        return []

    results: list[LoadedPlugin] = []
    for entry in sorted(plugins_dir.iterdir()):
        if not entry.is_dir():
            continue
        plugin_name = entry.name

        manifest_path = entry / "manifest.json"
        init_path = entry / "__init__.py"
        key_path = entry / "plugin.key"

        if not manifest_path.exists() or not init_path.exists():
            logger.warning("Plugin %s: missing manifest.json or __init__.py — skipped", plugin_name)
            continue

        if not key_path.exists():
            logger.warning("Plugin %s: missing plugin.key — skipped", plugin_name)
            continue

        token = key_path.read_text(encoding="utf-8").strip()
        if not verify_plugin_key(token, plugin_name):
            logger.warning("Plugin %s: invalid or mismatched plugin.key — skipped", plugin_name)
            continue

        try:
            manifest_data = json.loads(manifest_path.read_text(encoding="utf-8"))
            meta = PluginMeta(
                name=manifest_data["name"],
                label=manifest_data["label"],
                version=manifest_data["version"],
                description=manifest_data["description"],
                min_tier=manifest_data["min_tier"],
                has_tab=bool(manifest_data["has_tab"]),
                author=manifest_data["author"],
            )
        except (json.JSONDecodeError, KeyError) as exc:
            logger.warning("Plugin %s: manifest parse error: %s — skipped", plugin_name, exc)
            continue

        try:
            spec = importlib.util.spec_from_file_location(
                f"termmon_plugin_{plugin_name}", init_path
            )
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
        except Exception as exc:
            logger.warning("Plugin %s: import error: %s — skipped", plugin_name, exc)
            continue

        if not hasattr(module, "scan"):
            logger.warning("Plugin %s: no scan() function — skipped", plugin_name)
            continue

        results.append(LoadedPlugin(meta=meta, module=module, plugin_dir=entry))
        logger.info("Plugin %s loaded (v%s)", plugin_name, meta.version)

    return results
