# Plugin Architecture — Design Spec

**Date:** 2026-05-21
**Project:** Terminal Monitor (ops-platform feature 4 of 5)
**Status:** Approved — ready for implementation planning

---

## Goal

Give buyers a way to extend Terminal Monitor with purchased plugins (custom scanner data, dashboard tabs, action endpoints) while giving the developer a clean path to ship new features as paid plugins distributed via Gumroad or GitHub Releases.

---

## Business Model

- Plugins are sold individually — buyer purchases a plugin, receives an RS256 JWT key, drops it in the plugin folder
- Plugin keys are issued with `termmon-keygen.py --plugin <name>` — same infrastructure as the main license
- Plugin `manifest.json` declares `min_tier` (informational) — the plugin key itself is the gate; if Terminal Monitor loaded it, the buyer paid for it
- Free plugins (distributed without a key) are out of scope for v1 — every plugin folder must have a `plugin.key`

---

## Architecture

### Plugin Folder Structure

```
plugins/
  docker/
    manifest.json     ← metadata
    plugin.key        ← RS256 JWT: {"sub": "termmon-plugin-docker", "email": "...", "issued_at": "..."}
    __init__.py       ← scan() required; router() optional
    tab.html          ← dashboard tab panel HTML (required if has_tab: true in manifest)
```

Default location: `plugins/` adjacent to the app root (one level above `termmon/`).
Override: `plugins_dir:` field in `config.yaml`.

### `manifest.json`

```json
{
  "name": "docker",
  "label": "Docker",
  "version": "1.0.0",
  "description": "Monitor running Docker containers",
  "min_tier": "mid",
  "has_tab": true,
  "author": "annointedfrom"
}
```

All fields required. `min_tier` is informational — it is not enforced at runtime (the key is the gate).

### `__init__.py` Protocol (duck typing — no base class)

```python
# Required
def scan() -> dict:
    """Return plugin data. Called on every GET /api/plugins/<name>/data."""
    ...

# Optional — only needed for action endpoints (restart, flush, kill, etc.)
def router():
    from fastapi import APIRouter
    r = APIRouter()

    @r.post("/restart/{container_id}")
    async def restart(container_id: str):
        ...

    return r
```

### `tab.html`

A self-contained HTML fragment (no `<html>`, `<head>`, or `<body>` tags). May contain inline `<script>` and `<style>`. The script fetches `GET /api/plugins/<name>/data` on an interval and renders into the panel. Terminal Monitor injects it once when the buyer first clicks the tab.

---

## Components

### `termmon/plugin_loader.py` (new)

**`verify_plugin_key(token: str, plugin_name: str) -> bool`**
Reuses the existing RSA signature check from `licensing.py` but validates `sub == f"termmon-plugin-{plugin_name}"` instead of `"terminal-monitor"`. Returns `False` on any failure.

**`PluginMeta` (dataclass)**
Holds deserialized `manifest.json` fields.

**`LoadedPlugin` (dataclass)**
Holds `meta: PluginMeta`, `module: ModuleType`, `plugin_dir: Path`.
Methods: `scan() -> dict`, `tab_html() -> str | None`, `has_router() -> bool`, `get_router() -> APIRouter | None`.

**`load_plugins(plugins_dir: Path) -> list[LoadedPlugin]`**
Discovery loop — for each subdirectory:
1. Check `manifest.json` and `__init__.py` exist — skip with `logger.warning` if not
2. Check `plugin.key` exists — skip with warning if not
3. Call `verify_plugin_key` — skip with warning if invalid or wrong plugin name
4. Parse `manifest.json` into `PluginMeta` — skip with warning on parse error
5. Import module via `importlib.util.spec_from_file_location` — skip with warning on import error
6. Check `hasattr(module, "scan")` — skip with warning if missing
7. Append `LoadedPlugin` to results

A bad plugin is always skipped — never crashes the app.

**`_resolve_plugins_dir(config_plugins_dir: str | None) -> Path`**
Returns `Path(config_plugins_dir)` if set, else `Path(__file__).parent.parent / "plugins"`.

### `termmon/licensing.py` (modified)

Add `verify_plugin_key(token: str, plugin_name: str) -> bool`:
- Decodes and verifies JWT signature against `PUBLIC_KEY` (RS256)
- Checks `sub == f"termmon-plugin-{plugin_name}"`
- Returns `False` on any exception

### `termmon/config.py` (modified)

Add to `Settings`:
```python
plugins_dir: Optional[str] = None
```

`null` in `config.yaml` means use the default `plugins/` path.

### `termmon/main.py` (modified)

**Lifespan** — after existing license and update cache init:
```python
plugins_dir = _resolve_plugins_dir(settings.plugins_dir)
app.state.plugins = load_plugins(plugins_dir)
for plugin in app.state.plugins:
    _register_plugin_endpoints(app, plugin)
```

**`_register_plugin_endpoints(app, plugin)`** (module-level helper):
- Registers `GET /api/plugins/<name>/data` → calls `plugin.scan()`, returns result, logs warning and returns 500 on exception
- If `plugin.meta.has_tab`: registers `GET /api/plugins/<name>/tab` → returns `HTMLResponse(plugin.tab_html())`
- If `plugin.has_router()`: calls `app.include_router(plugin.get_router(), prefix=f"/api/plugins/{name}")`

**New route `GET /api/plugins`** (static, not per-plugin):
Returns list of loaded plugin metadata — `name`, `label`, `version`, `description`, `has_tab` for each.

All plugin endpoints are behind the existing HTTP middleware license gate (BASE+ required). No additional tier check.

### `termmon/dashboard.html` (modified)

**New JS function `_loadPlugins()`** — called after `_loadConfig()` at page load:
1. `GET /api/plugins` — fetch loaded plugin list
2. For each plugin: append a tab button to `#tab-bar`, append a hidden panel div to the tab panels container
3. Plugin panel has `data-plugin-loaded="false"` attribute

**`switchTab()` modification** — when switching to a plugin tab (`id` starts with `plugin-`):
- If `data-plugin-loaded="false"`: fetch `GET /api/plugins/<name>/tab`, inject HTML into panel, set `data-plugin-loaded="true"`
- Show/hide panels same as existing tabs

Plugin tabs appear after all existing tabs (PROCESSES, MCP, RESOURCES, HISTORY, ENERGY, AI). Existing tabs are not modified.

### `termmon-keygen.py` (modified)

Add `--plugin <name>` flag:
```bash
# Plugin key (no tier field, sub is plugin-specific)
python termmon-keygen.py --email buyer@example.com --plugin docker
# → JWT: {"sub": "termmon-plugin-docker", "email": "buyer@...", "issued_at": "..."}

# Main app key (unchanged)
python termmon-keygen.py --tier mid --email buyer@example.com
# → JWT: {"sub": "terminal-monitor", "tier": "mid", "email": "...", "issued_at": "..."}
```

When `--plugin` is provided, `--tier` is ignored (plugin keys have no tier).

---

## Runtime API

| Endpoint | Auth | Description |
|---|---|---|
| `GET /api/plugins` | BASE+ | List all loaded plugins |
| `GET /api/plugins/<name>/data` | BASE+ | Call plugin's `scan()` |
| `GET /api/plugins/<name>/tab` | BASE+ | Return tab HTML fragment |
| `POST /api/plugins/<name>/*` | BASE+ | Plugin action routes (if `router()` defined) |

---

## Error Handling

| Scenario | Behavior |
|---|---|
| `plugins/` dir does not exist | `load_plugins` returns `[]` — no error |
| Plugin missing `manifest.json` or `__init__.py` | Skip with `logger.warning` |
| Missing or invalid `plugin.key` | Skip with `logger.warning` |
| Key `sub` doesn't match plugin folder name | Skip — wrong key for this plugin |
| Module import raises | Skip with `logger.warning` |
| Plugin has no `scan()` | Skip with `logger.warning` |
| `scan()` raises at runtime | `GET /api/plugins/<name>/data` returns 500; logged |
| `tab.html` missing when `has_tab: true` | `GET /api/plugins/<name>/tab` returns 404 |

---

## Files Created / Modified

| File | Action |
|---|---|
| `termmon/plugin_loader.py` | Create |
| `termmon/licensing.py` | Modify — add `verify_plugin_key` |
| `termmon/config.py` | Modify — add `plugins_dir` field |
| `termmon/main.py` | Modify — lifespan, `_register_plugin_endpoints`, `GET /api/plugins` |
| `termmon/dashboard.html` | Modify — `_loadPlugins()`, lazy tab load, `switchTab()` update |
| `termmon-keygen.py` | Modify — add `--plugin` flag |
| `tests/test_plugin_loader.py` | Create |

---

## Testing

`tests/test_plugin_loader.py` covers:
- `load_plugins` returns `[]` when directory does not exist
- Skips plugin with missing `manifest.json`
- Skips plugin with missing `plugin.key`
- Skips plugin with invalid JWT signature
- Skips plugin with key issued for wrong plugin name (`sub` mismatch)
- Skips plugin with no `scan()` function
- Skips plugin whose module raises on import
- Successfully loads a valid plugin with correct key
- `GET /api/plugins` returns loaded plugin metadata
- `GET /api/plugins/<name>/data` calls `scan()` and returns result
- `GET /api/plugins/<name>/data` returns 500 when `scan()` raises
- `GET /api/plugins/<name>/tab` returns tab HTML
- `GET /api/plugins/<name>/tab` returns 404 when `has_tab: false`
- Plugin key generation: `--plugin` flag produces correct `sub` claim

---

## Security Notes

- Plugin keys validated offline via RS256 — no network call required
- `sub` claim is scoped per plugin name — a docker key cannot activate a redis plugin
- Plugin modules run in the same process as the app — a malicious plugin could do anything a Python process can do. Mitigation: you control which plugins are distributed; buyers can audit source before installing
- Plugin action routes (`router()`) are behind the existing license middleware — unauthenticated requests never reach plugin code
- `tab.html` is injected as raw HTML — plugin author is trusted (you distribute the plugins); no additional sanitization applied

---

## Out of Scope (v1)

- Hot-reload without restart
- Free plugins (no key required)
- Plugin marketplace UI inside the dashboard
- Per-plugin tier enforcement at runtime (key is the gate)
- Plugin sandboxing / subprocess isolation
- Plugin dependencies / `requirements.txt` per plugin
