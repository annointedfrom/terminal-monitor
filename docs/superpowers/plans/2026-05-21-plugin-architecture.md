# Plugin Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a plugin system to Terminal Monitor that lets buyers install purchased plugins (each validated via a per-plugin RS256 JWT key) which are discovered at startup, loaded via importlib, and registered as live API + dashboard tab endpoints.

**Architecture:** `termmon/plugin_loader.py` (new) handles discovery and loading; `termmon/licensing.py` gains `verify_plugin_key()` reusing the existing RS256 public key with a plugin-scoped `sub` claim; `termmon/main.py` loads plugins in lifespan and registers per-plugin routes; the dashboard client-side `_loadPlugins()` injects plugin tabs dynamically; `termmon-keygen.py` gets a `--plugin` flag.

**Tech Stack:** FastAPI, PyJWT[cryptography] (already installed), importlib.util (stdlib), Pydantic v2, pytest + pytest-asyncio

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `termmon/licensing.py` | Modify | Add `verify_plugin_key(token, plugin_name) -> bool` |
| `termmon/plugin_loader.py` | Create | `PluginMeta`, `LoadedPlugin`, `load_plugins`, `_resolve_plugins_dir` |
| `termmon/config.py` | Modify | Add `plugins_dir: Optional[str] = None` to `Settings` |
| `termmon/main.py` | Modify | Lifespan plugin loading, `_register_plugin_endpoints`, `GET /api/plugins` |
| `termmon/dashboard.html` | Modify | `_loadPlugins()`, lazy tab injection, `switchTab()` update |
| `termmon-keygen.py` | Modify | `issue_plugin_key()`, `--plugin` CLI flag |
| `tests/test_plugin_loader.py` | Create | Loader unit tests + API endpoint tests via mini test app |
| `tests/test_keygen.py` | Modify | Add plugin key generation tests |

---

## Context: Codebase patterns to follow

- `termmon/licensing.py` holds `PUBLIC_KEY` (hardcoded PEM) and `verify_license()` using `jwt.decode(..., algorithms=["RS256"], options={"verify_exp": False})`. `verify_plugin_key` follows the same pattern.
- Tests use `patch.object(lic_mod, "PUBLIC_KEY", public_pem)` to inject a test keypair — follow this same pattern.
- `test_keygen.py` uses `importlib.util.spec_from_file_location` to load `termmon-keygen.py` since it has a hyphen in the filename.
- `termmon/main.py` lifespan currently: `app.state.license = verify_license(settings.license_key)` then `app.state.update_cache = None`. Add plugin loading after these two lines.
- `main.py` imports: `from fastapi.responses import FileResponse, JSONResponse, RedirectResponse` — add `HTMLResponse` to this import.

---

### Task 1: `verify_plugin_key` in `termmon/licensing.py`

**Files:**
- Modify: `termmon/licensing.py` (add after `verify_license`, before `require_tier`)
- Test: `tests/test_licensing.py` (append to existing file)

- [ ] **Step 1: Write the failing tests**

Append to the bottom of `tests/test_licensing.py`:

```python
def test_verify_plugin_key_valid(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = pyjwt.encode(
        {"sub": "termmon-plugin-docker", "email": "buyer@test.com", "issued_at": "2026-05-21"},
        private_pem,
        algorithm="RS256",
    )
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert lic_mod.verify_plugin_key(token, "docker") is True


def test_verify_plugin_key_wrong_plugin_name(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = pyjwt.encode(
        {"sub": "termmon-plugin-docker", "email": "buyer@test.com", "issued_at": "2026-05-21"},
        private_pem,
        algorithm="RS256",
    )
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert lic_mod.verify_plugin_key(token, "redis") is False


def test_verify_plugin_key_garbage_returns_false():
    assert lic_mod.verify_plugin_key("not.a.jwt", "docker") is False


def test_verify_plugin_key_empty_returns_false():
    assert lic_mod.verify_plugin_key("", "docker") is False


def test_verify_plugin_key_main_license_token_rejected(rsa_keypair):
    """A main app license key must NOT pass as a plugin key."""
    private_pem, public_pem = rsa_keypair
    token = pyjwt.encode(
        {"sub": "terminal-monitor", "tier": "mid", "email": "b@t.com", "issued_at": "2026-05-21"},
        private_pem,
        algorithm="RS256",
    )
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert lic_mod.verify_plugin_key(token, "docker") is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_licensing.py -k "plugin_key" -v
```
Expected: FAIL — `AttributeError: module 'termmon.licensing' has no attribute 'verify_plugin_key'`

- [ ] **Step 3: Add `verify_plugin_key` to `termmon/licensing.py`**

Insert after the closing `return None` of `verify_license` (after line 65, before `def require_tier`):

```python
def verify_plugin_key(token: str, plugin_name: str) -> bool:
    if not token or not PUBLIC_KEY:
        return False
    try:
        payload = jwt.decode(
            token,
            PUBLIC_KEY,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        return payload.get("sub") == f"termmon-plugin-{plugin_name}"
    except Exception:
        return False
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_licensing.py -k "plugin_key" -v
```
Expected: 5 PASSED

- [ ] **Step 5: Run full test suite to check nothing is broken**

```
pytest --tb=short -q
```
Expected: all previously passing tests still pass

- [ ] **Step 6: Commit**

```
git add termmon/licensing.py tests/test_licensing.py
git commit -m "feat: add verify_plugin_key to licensing.py"
```

---

### Task 2: Create `termmon/plugin_loader.py`

**Files:**
- Create: `termmon/plugin_loader.py`
- Create: `tests/test_plugin_loader.py`

- [ ] **Step 1: Write failing tests in `tests/test_plugin_loader.py`**

Create `tests/test_plugin_loader.py` with this full content:

```python
import json
import pytest
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from pathlib import Path
from unittest.mock import patch

import termmon.licensing as lic_mod


@pytest.fixture
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def _make_plugin_token(private_pem: str, plugin_name: str) -> str:
    return pyjwt.encode(
        {"sub": f"termmon-plugin-{plugin_name}", "email": "buyer@test.com", "issued_at": "2026-05-21"},
        private_pem,
        algorithm="RS256",
    )


def _write_plugin(
    plugin_dir: Path,
    *,
    private_pem: str,
    name: str,
    has_manifest: bool = True,
    has_init: bool = True,
    has_key: bool = True,
    scan_body: str = "def scan():\n    return {'ok': True}\n",
    has_tab: bool = False,
    key_sub_name: str | None = None,
) -> None:
    """Write a minimal plugin folder. key_sub_name overrides the sub claim for mismatch tests."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    if has_manifest:
        (plugin_dir / "manifest.json").write_text(json.dumps({
            "name": name, "label": name.title(), "version": "1.0.0",
            "description": "Test plugin", "min_tier": "base",
            "has_tab": has_tab, "author": "test",
        }))
    if has_init:
        (plugin_dir / "__init__.py").write_text(scan_body)
    if has_key:
        sub_name = key_sub_name if key_sub_name is not None else name
        token = _make_plugin_token(private_pem, sub_name)
        (plugin_dir / "plugin.key").write_text(token)
    if has_tab:
        (plugin_dir / "tab.html").write_text("<div>Hello from plugin</div>")


# ─── Loader discovery tests ────────────────────────────────────────────────────

def test_load_plugins_returns_empty_when_dir_missing(tmp_path):
    from termmon.plugin_loader import load_plugins
    result = load_plugins(tmp_path / "no-such-dir")
    assert result == []


def test_load_plugins_skips_missing_manifest(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    d.mkdir()
    (d / "__init__.py").write_text("def scan(): return {}")
    (d / "plugin.key").write_text(_make_plugin_token(private_pem, "myplugin"))
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_skips_missing_key(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin", has_key=False)
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_skips_invalid_jwt(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin")
    (d / "plugin.key").write_text("not.a.valid.jwt")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_skips_wrong_sub(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin", key_sub_name="otherplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_skips_missing_scan(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin", scan_body="x = 1\n")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_skips_bad_import(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin",
                  scan_body="def scan(\n    return {}\n")  # syntax error
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_loads_valid_plugin(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = load_plugins(tmp_path)
    assert len(result) == 1
    assert result[0].meta.name == "myplugin"


# ─── LoadedPlugin method tests ────────────────────────────────────────────────

def test_loaded_plugin_scan_returns_data(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    assert plugins[0].scan() == {"ok": True}


def test_loaded_plugin_tab_html_returns_content(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin", has_tab=True)
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    assert plugins[0].tab_html() == "<div>Hello from plugin</div>"


def test_loaded_plugin_tab_html_none_when_file_missing(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    assert plugins[0].tab_html() is None


def test_loaded_plugin_has_router_false_without_router(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    assert plugins[0].has_router() is False


def test_loaded_plugin_has_router_true_with_router(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(
        d, private_pem=private_pem, name="myplugin",
        scan_body=(
            "def scan():\n    return {}\n"
            "def router():\n    from fastapi import APIRouter\n    return APIRouter()\n"
        ),
    )
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    assert plugins[0].has_router() is True


# ─── _resolve_plugins_dir tests ───────────────────────────────────────────────

def test_resolve_plugins_dir_default():
    from termmon.plugin_loader import _resolve_plugins_dir
    import termmon.plugin_loader as _pl
    expected = Path(_pl.__file__).parent.parent / "plugins"
    assert _resolve_plugins_dir(None) == expected


def test_resolve_plugins_dir_custom(tmp_path):
    from termmon.plugin_loader import _resolve_plugins_dir
    assert _resolve_plugins_dir(str(tmp_path)) == tmp_path
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_plugin_loader.py -v
```
Expected: FAIL — `ModuleNotFoundError: No module named 'termmon.plugin_loader'`

- [ ] **Step 3: Create `termmon/plugin_loader.py`**

Create `termmon/plugin_loader.py` with this full content:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_plugin_loader.py -v
```
Expected: 17 PASSED

- [ ] **Step 5: Run full test suite**

```
pytest --tb=short -q
```
Expected: all previously passing tests still pass

- [ ] **Step 6: Commit**

```
git add termmon/plugin_loader.py tests/test_plugin_loader.py
git commit -m "feat: add plugin_loader module with discovery and validation"
```

---

### Task 3: Add `plugins_dir` to `termmon/config.py`

**Files:**
- Modify: `termmon/config.py` (add one field to `Settings`)

This is a small additive change. No new tests needed — the existing `tests/test_config.py` will confirm the field has a working default.

- [ ] **Step 1: Add the field to `Settings`**

In `termmon/config.py`, find the `Settings` class (currently ends at `license_key: str = ""`).
Add `plugins_dir` as the last field:

```python
class Settings(BaseModel):
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    brain: BrainConfig = Field(default_factory=BrainConfig)
    services: list[ServiceConfig] = Field(default_factory=list)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    license_key: str = ""
    plugins_dir: Optional[str] = None
```

- [ ] **Step 2: Verify existing tests still pass**

```
pytest tests/test_config.py -v
```
Expected: all PASSED

- [ ] **Step 3: Commit**

```
git add termmon/config.py
git commit -m "feat: add plugins_dir config field"
```

---

### Task 4: Wire plugins into `termmon/main.py` + API endpoint tests

**Files:**
- Modify: `termmon/main.py`
- Modify: `tests/test_plugin_loader.py` (append API endpoint tests)

- [ ] **Step 1: Write failing API tests**

Append to `tests/test_plugin_loader.py` after the last existing test:

```python
# ─── API endpoint tests ────────────────────────────────────────────────────────
# These tests use a minimal FastAPI app (not termmon.main.app) to avoid
# polluting the main app's route table across test runs.

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _endpoint_client(plugin) -> TestClient:
    """Minimal app with plugin routes registered via _register_plugin_endpoints."""
    from termmon.main import _register_plugin_endpoints
    from termmon.licensing import LicenseInfo, Tier

    mini = FastAPI()
    mini.state.license = LicenseInfo(tier=Tier.BASE, email="t@test.com", issued_at="2026-05-21")
    mini.state.plugins = [plugin]
    _register_plugin_endpoints(mini, plugin)

    @mini.get("/api/plugins")
    async def _list():
        return [
            {
                "name": p.meta.name,
                "label": p.meta.label,
                "version": p.meta.version,
                "description": p.meta.description,
                "has_tab": p.meta.has_tab,
            }
            for p in mini.state.plugins
        ]

    return TestClient(mini)


def test_get_plugins_returns_metadata(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "endplugin"
    _write_plugin(d, private_pem=private_pem, name="endplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    client = _endpoint_client(plugins[0])
    r = client.get("/api/plugins")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["name"] == "endplugin"
    assert "label" in body[0]
    assert "has_tab" in body[0]


def test_plugin_data_returns_scan_result(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "dataplugin"
    _write_plugin(d, private_pem=private_pem, name="dataplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    client = _endpoint_client(plugins[0])
    r = client.get("/api/plugins/dataplugin/data")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_plugin_data_returns_500_when_scan_raises(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "errplugin"
    _write_plugin(d, private_pem=private_pem, name="errplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    plugin = plugins[0]
    with patch.object(plugin.module, "scan", side_effect=RuntimeError("boom")):
        client = _endpoint_client(plugin)
        r = client.get("/api/plugins/errplugin/data")
    assert r.status_code == 500


def test_plugin_tab_returns_html(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "tabplugin"
    _write_plugin(d, private_pem=private_pem, name="tabplugin", has_tab=True)
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    client = _endpoint_client(plugins[0])
    r = client.get("/api/plugins/tabplugin/tab")
    assert r.status_code == 200
    assert "<div>" in r.text


def test_plugin_tab_returns_404_when_has_tab_false(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "notabplugin"
    _write_plugin(d, private_pem=private_pem, name="notabplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    client = _endpoint_client(plugins[0])
    # No /tab route registered when has_tab=False → FastAPI returns 404
    r = client.get("/api/plugins/notabplugin/tab")
    assert r.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_plugin_loader.py -k "endpoint or metadata or tab or data_return" -v
```
Expected: FAIL — `ImportError: cannot import name '_register_plugin_endpoints' from 'termmon.main'`

- [ ] **Step 3: Add imports to `termmon/main.py`**

Find this line in `termmon/main.py`:
```python
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
```
Replace with:
```python
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
```

Find this line:
```python
from termmon.updater import check_updates, ollama_pull
```
Add after it:
```python
from termmon.plugin_loader import load_plugins, _resolve_plugins_dir, LoadedPlugin
```

- [ ] **Step 4: Add `_register_plugin_endpoints` helper to `termmon/main.py`**

Add this function before the `lifespan` function (before `@asynccontextmanager`):

```python
def _register_plugin_endpoints(app: FastAPI, plugin: LoadedPlugin) -> None:
    name = plugin.meta.name

    async def _data(request: Request, _p=plugin):
        try:
            return _p.scan()
        except Exception as exc:
            logger.warning("Plugin %s scan() raised: %s", name, exc)
            return JSONResponse(status_code=500, content={"detail": "Plugin error"})

    app.add_api_route(f"/api/plugins/{name}/data", _data, methods=["GET"])

    if plugin.meta.has_tab:
        async def _tab(_p=plugin):
            html = _p.tab_html()
            if html is None:
                return JSONResponse(status_code=404, content={"detail": "tab.html not found"})
            return HTMLResponse(html)

        app.add_api_route(f"/api/plugins/{name}/tab", _tab, methods=["GET"])

    if plugin.has_router():
        app.include_router(plugin.get_router(), prefix=f"/api/plugins/{name}")
```

- [ ] **Step 5: Update `lifespan` to load plugins**

Find this block in `termmon/main.py`:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.license = verify_license(settings.license_key)
    app.state.update_cache = None
    tasks = []
    if settings.brain.enabled:
        tasks.append(asyncio.create_task(_brain_loop()))
    yield
    for t in tasks:
        t.cancel()
```

Replace with:
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.license = verify_license(settings.license_key)
    app.state.update_cache = None
    plugins_dir = _resolve_plugins_dir(settings.plugins_dir)
    app.state.plugins = load_plugins(plugins_dir)
    for plugin in app.state.plugins:
        _register_plugin_endpoints(app, plugin)
    tasks = []
    if settings.brain.enabled:
        tasks.append(asyncio.create_task(_brain_loop()))
    yield
    for t in tasks:
        t.cancel()
```

- [ ] **Step 6: Add `GET /api/plugins` route to `termmon/main.py`**

Find this route in `termmon/main.py`:
```python
@app.get("/api/update/check")
async def update_check(request: Request):
```

Add the new route just before it:

```python
@app.get("/api/plugins")
async def list_plugins(request: Request):
    plugins = getattr(request.app.state, "plugins", [])
    return [
        {
            "name": p.meta.name,
            "label": p.meta.label,
            "version": p.meta.version,
            "description": p.meta.description,
            "has_tab": p.meta.has_tab,
        }
        for p in plugins
    ]


```

- [ ] **Step 7: Run the new API tests**

```
pytest tests/test_plugin_loader.py -k "endpoint or metadata or returns_html or returns_scan or returns_500 or returns_404" -v
```
Expected: 5 PASSED

- [ ] **Step 8: Run full test suite**

```
pytest --tb=short -q
```
Expected: all previously passing tests still pass

- [ ] **Step 9: Commit**

```
git add termmon/main.py tests/test_plugin_loader.py
git commit -m "feat: integrate plugin loader into main.py with API endpoints"
```

---

### Task 5: Plugin tab injection in `termmon/dashboard.html`

**Files:**
- Modify: `termmon/dashboard.html`

No automated test — verify manually by running the app. The spec says plugin tabs appear after the 6 existing tabs and are lazy-loaded when first clicked.

- [ ] **Step 1: Add `_loadPlugins()` JS function**

Find this line in `termmon/dashboard.html`:
```javascript
async function _loadConfig() {
```

Insert `_loadPlugins()` immediately before it:

```javascript
async function _loadPlugins() {
  try {
    var r = await fetch('/api/plugins');
    if (!r.ok) return;
    var plugins = await r.json();
    if (!plugins.length) return;
    var tabBar = document.getElementById('tab-bar');
    var tabContent = document.getElementById('tab-content');
    plugins.forEach(function(p) {
      var tabId = 'plugin-' + p.name;
      var paneId = 'pane-plugin-' + p.name;
      var tab = document.createElement('div');
      tab.className = 'tab';
      tab.setAttribute('data-plugin', esc(p.name));
      tab.textContent = esc(p.label);
      tab.onclick = (function(id) { return function() { switchTab(id); }; })(tabId);
      tabBar.appendChild(tab);
      var pane = document.createElement('div');
      pane.id = paneId;
      pane.className = 'tab-pane';
      pane.setAttribute('data-plugin-loaded', 'false');
      tabContent.appendChild(pane);
    });
  } catch(e) {}
}

```

- [ ] **Step 2: Modify `switchTab()` to handle plugin tabs**

Find this exact block in `termmon/dashboard.html`:
```javascript
function switchTab(name) {
  var tabs = document.querySelectorAll('.tab');
  var names = ['processes','mcp','resources','history','energy','ai'];
  tabs.forEach(function(t, i) { t.classList.toggle('active', names[i] === name); });
  document.querySelectorAll('.tab-pane').forEach(function(p) {
    p.classList.toggle('active', p.id === 'pane-' + name);
  });
  document.getElementById('tab-content').classList.toggle('chat-active', name === 'ai');
  if (name === 'history') renderHistory();
  if (name === 'energy') renderEnergy();
  if (name === 'ai') { renderChat(); fetchTrainingStatus(); loadModels(); }
}
```

Replace with:
```javascript
function switchTab(name) {
  var tabs = document.querySelectorAll('.tab');
  var names = ['processes','mcp','resources','history','energy','ai'];
  tabs.forEach(function(t, i) {
    if (i < names.length) {
      t.classList.toggle('active', names[i] === name);
    } else {
      t.classList.toggle('active', 'plugin-' + t.getAttribute('data-plugin') === name);
    }
  });
  document.querySelectorAll('.tab-pane').forEach(function(p) {
    p.classList.toggle('active', p.id === 'pane-' + name);
  });
  document.getElementById('tab-content').classList.toggle('chat-active', name === 'ai');
  if (name === 'history') renderHistory();
  if (name === 'energy') renderEnergy();
  if (name === 'ai') { renderChat(); fetchTrainingStatus(); loadModels(); }
  if (name.startsWith('plugin-')) {
    var pane = document.getElementById('pane-' + name);
    if (pane && pane.getAttribute('data-plugin-loaded') === 'false') {
      var pluginName = name.slice('plugin-'.length);
      fetch('/api/plugins/' + encodeURIComponent(pluginName) + '/tab')
        .then(function(r) { return r.text(); })
        .then(function(html) { pane.innerHTML = html; pane.setAttribute('data-plugin-loaded', 'true'); })
        .catch(function() {});
    }
  }
}
```

- [ ] **Step 3: Call `_loadPlugins()` at page load**

Find this line in `termmon/dashboard.html` (near the bottom of the script):
```javascript
    _loadConfig().then(function() {
      _checkUpdates();
    });
```

Replace with:
```javascript
    _loadConfig().then(function() {
      _checkUpdates();
      _loadPlugins();
    });
```

- [ ] **Step 4: Verify the app still starts and renders correctly**

```
.\.venv\Scripts\uvicorn termmon.main:app --port 8084
```

Open http://localhost:8084/dashboard — confirm the 6 original tabs all appear and no JS errors in console. (No plugins will show unless a valid plugin folder exists.)

- [ ] **Step 5: Commit**

```
git add termmon/dashboard.html
git commit -m "feat: add plugin tab injection to dashboard"
```

---

### Task 6: `--plugin` flag in `termmon-keygen.py`

**Files:**
- Modify: `termmon-keygen.py`
- Modify: `tests/test_keygen.py` (append tests)

- [ ] **Step 1: Write failing tests**

Append to `tests/test_keygen.py`:

```python
def test_issue_plugin_key_correct_sub(tmp_path):
    kg = _load_keygen()
    public_pem = kg.generate_keypair(tmp_path)
    token = kg.issue_plugin_key("docker", "buyer@example.com", tmp_path / "private_key.pem")
    payload = pyjwt.decode(token, public_pem, algorithms=["RS256"], options={"verify_exp": False})
    assert payload["sub"] == "termmon-plugin-docker"
    assert payload["email"] == "buyer@example.com"
    assert "tier" not in payload
    assert "issued_at" in payload


def test_issue_plugin_key_different_plugins(tmp_path):
    kg = _load_keygen()
    public_pem = kg.generate_keypair(tmp_path)
    for name in ("docker", "redis", "nginx"):
        token = kg.issue_plugin_key(name, "buyer@example.com", tmp_path / "private_key.pem")
        payload = pyjwt.decode(token, public_pem, algorithms=["RS256"], options={"verify_exp": False})
        assert payload["sub"] == f"termmon-plugin-{name}"
        assert "tier" not in payload
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_keygen.py -k "plugin_key" -v
```
Expected: FAIL — `AttributeError: module 'termmon_keygen' has no attribute 'issue_plugin_key'`

- [ ] **Step 3: Add `issue_plugin_key` and `--plugin` flag to `termmon-keygen.py`**

Find this function in `termmon-keygen.py`:
```python
def issue_key(tier: str, email: str, private_key_path: pathlib.Path) -> str:
```

Add a new function after it (after the closing `return jwt.encode(...)`):

```python
def issue_plugin_key(plugin_name: str, email: str, private_key_path: pathlib.Path) -> str:
    """Sign a JWT plugin key for the given plugin name and email. No tier field."""
    private_pem = private_key_path.read_text()
    return jwt.encode(
        {
            "sub": f"termmon-plugin-{plugin_name}",
            "email": email,
            "issued_at": date.today().isoformat(),
        },
        private_pem,
        algorithm="RS256",
    )
```

Find this line in `main()`:
```python
    parser.add_argument("--key-dir", type=pathlib.Path, default=_default_key_dir(),
```

Add `--plugin` argument before it:
```python
    parser.add_argument("--plugin", help="Plugin name to issue a plugin key for (ignores --tier)")
    parser.add_argument("--key-dir", type=pathlib.Path, default=_default_key_dir(),
```

Find this block in `main()`:
```python
    if args.tier and args.email:
        private_key_path = args.key_dir / "private_key.pem"
        if not private_key_path.exists():
            print(f"[error] Private key not found at {private_key_path}", file=sys.stderr)
            print("Run: python termmon-keygen.py --generate-keypair", file=sys.stderr)
            sys.exit(1)
        token = issue_key(args.tier, args.email, private_key_path)
        print(token)
        return
```

Insert a new block BEFORE it (plugin check comes first since it ignores `--tier`):
```python
    if args.plugin and args.email:
        private_key_path = args.key_dir / "private_key.pem"
        if not private_key_path.exists():
            print(f"[error] Private key not found at {private_key_path}", file=sys.stderr)
            print("Run: python termmon-keygen.py --generate-keypair", file=sys.stderr)
            sys.exit(1)
        token = issue_plugin_key(args.plugin, args.email, private_key_path)
        print(token)
        return

    if args.tier and args.email:
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_keygen.py -v
```
Expected: all PASSED (including the 2 new plugin tests)

- [ ] **Step 5: Run full test suite**

```
pytest --tb=short -q
```
Expected: all tests pass

- [ ] **Step 6: Commit**

```
git add termmon-keygen.py tests/test_keygen.py
git commit -m "feat: add --plugin flag to termmon-keygen.py"
```

---

## Acceptance Criteria

After all 6 tasks complete:

1. `pytest` passes all tests (122 existing + ~27 new ≈ 149 total)
2. `GET /api/plugins` returns `[]` when no `plugins/` directory exists
3. A valid plugin folder with correct `plugin.key` and `scan()` function is loaded and accessible at `GET /api/plugins/<name>/data`
4. An invalid or missing key causes the plugin to be skipped with a logged warning (app still starts)
5. Dashboard shows plugin tabs after the 6 existing tabs; clicking a plugin tab fetches and injects its `tab.html`
6. `python termmon-keygen.py --plugin docker --email buyer@example.com` produces a JWT with `sub: "termmon-plugin-docker"` and no `tier` field
