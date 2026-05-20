# Tiered Licensing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Gate Terminal Monitor features behind Base / Mid / Diamond tiers using offline RS256-signed JWT license keys verified at startup, enforced by HTTP middleware and per-route FastAPI dependencies.

**Architecture:** `termmon/licensing.py` owns the `Tier` enum, `LicenseInfo` dataclass, `verify_license()`, and the `require_tier()` dependency factory. App startup validates the key from `settings.license_key` and stores the result in `app.state.license`. An HTTP middleware blocks all non-exempt routes when `app.state.license` is None; per-route dependencies enforce MID/DIAMOND minimums. `termmon-keygen.py` (developer-only, not shipped) generates the RSA keypair and signs buyer JWTs using the private key.

**Tech Stack:** `PyJWT[cryptography]` (RS256 JWT signing/verification), `cryptography` (RSA key generation in keygen tool), FastAPI middleware + `Depends()`, Pydantic v2 Settings, pytest + `unittest.mock.patch`

**Spec:** `docs/superpowers/specs/2026-05-20-tiered-licensing-design.md`

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `requirements.txt` | Modify | Add PyJWT[cryptography] |
| `termmon/licensing.py` | Create | Tier enum, LicenseInfo, PUBLIC_KEY, verify_license, require_tier |
| `termmon/config.py` | Modify | Add `license_key: str = ""` to Settings |
| `termmon/main.py` | Modify | Lifespan license check, middleware, /api/config tier, tier guards, setup_post update |
| `termmon/setup.html` | Modify | Add License Key field |
| `termmon-keygen.py` | Create | RSA keypair generation, JWT signing (developer tool only) |
| `.dockerignore` | Modify | Add termmon-keygen.py |
| `tests/test_licensing.py` | Create | verify_license, tier ordering, middleware, tier guard tests |
| `tests/test_config.py` | Modify | Add license_key field test |
| `tests/test_keygen.py` | Create | generate_keypair, issue_key function tests |

---

## Task 1: Create `termmon/licensing.py` and install PyJWT

**Files:**
- Modify: `requirements.txt`
- Create: `termmon/licensing.py`
- Create: `tests/test_licensing.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_licensing.py`:

```python
import pytest
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from unittest.mock import patch
import termmon.licensing as lic_mod
from termmon.licensing import Tier, LicenseInfo, verify_license


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


def _make_token(private_pem: str, tier: str, email: str = "buyer@example.com", sub: str = "terminal-monitor") -> str:
    return pyjwt.encode(
        {"tier": tier, "email": email, "issued_at": "2026-05-20", "sub": sub},
        private_pem,
        algorithm="RS256",
    )


def test_verify_license_empty_returns_none():
    assert verify_license("") is None


def test_verify_license_garbage_returns_none():
    assert verify_license("not.a.jwt") is None


def test_verify_license_base_tier(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = _make_token(private_pem, "base")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = verify_license(token)
    assert result is not None
    assert result.tier == Tier.BASE
    assert result.email == "buyer@example.com"
    assert result.issued_at == "2026-05-20"


def test_verify_license_mid_tier(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = _make_token(private_pem, "mid")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = verify_license(token)
    assert result is not None
    assert result.tier == Tier.MID


def test_verify_license_diamond_tier(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = _make_token(private_pem, "diamond")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = verify_license(token)
    assert result is not None
    assert result.tier == Tier.DIAMOND


def test_verify_license_wrong_sub_returns_none(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = _make_token(private_pem, "mid", sub="other-product")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = verify_license(token)
    assert result is None


def test_verify_license_wrong_signature_returns_none(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_public_pem = other_private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    token = _make_token(private_pem, "diamond")
    with patch.object(lic_mod, "PUBLIC_KEY", other_public_pem):
        result = verify_license(token)
    assert result is None


def test_tier_ordering():
    assert Tier.BASE < Tier.MID
    assert Tier.MID < Tier.DIAMOND
    assert Tier.BASE < Tier.DIAMOND
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
cd C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor
.venv\Scripts\pytest tests\test_licensing.py -v
```

Expected: `ModuleNotFoundError: No module named 'termmon.licensing'`

- [ ] **Step 3: Add PyJWT to requirements.txt**

Add this line after `pyyaml>=6.0.1`:

```
PyJWT[cryptography]>=2.8.0
```

Then install:

```powershell
.venv\Scripts\pip install "PyJWT[cryptography]>=2.8.0"
```

- [ ] **Step 4: Create `termmon/licensing.py`**

```python
from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import jwt

PUBLIC_KEY = ""  # Replaced during Task 7 with output of: python termmon-keygen.py --generate-keypair


class Tier(IntEnum):
    BASE = 1
    MID = 2
    DIAMOND = 3


@dataclass
class LicenseInfo:
    tier: Tier
    email: str
    issued_at: str


def verify_license(key_string: str) -> LicenseInfo | None:
    if not key_string or not PUBLIC_KEY:
        return None
    try:
        payload = jwt.decode(
            key_string,
            PUBLIC_KEY,
            algorithms=["RS256"],
            options={"verify_exp": False},
        )
        if payload.get("sub") != "terminal-monitor":
            return None
        tier = Tier[payload["tier"].upper()]
        return LicenseInfo(
            tier=tier,
            email=payload.get("email", ""),
            issued_at=payload.get("issued_at", ""),
        )
    except Exception:
        return None


def require_tier(minimum: Tier):
    from fastapi import Depends, HTTPException, Request

    async def _check(request: Request) -> LicenseInfo:
        info: LicenseInfo | None = getattr(request.app.state, "license", None)
        if info is None or info.tier < minimum:
            raise HTTPException(
                status_code=403,
                detail={"error": "insufficient_tier", "required": minimum.name.lower()},
            )
        return info

    return Depends(_check)
```

- [ ] **Step 5: Run tests to verify they pass**

```powershell
.venv\Scripts\pytest tests\test_licensing.py -v
```

Expected: all 9 tests PASS

- [ ] **Step 6: Commit**

```powershell
git add requirements.txt termmon/licensing.py tests/test_licensing.py
git commit -m "feat: add licensing module with RS256 JWT verification and tier enum"
```

---

## Task 2: Add `license_key` field to Settings

**Files:**
- Modify: `termmon/config.py` (line 36 — the `Settings` class)
- Modify: `tests/test_config.py`

- [ ] **Step 1: Write the failing test**

Add to the end of `tests/test_config.py`:

```python
def test_license_key_defaults_to_empty(tmp_path):
    config_path = tmp_path / "config.yaml"
    import termmon.config as cfg_mod
    cfg_mod._settings = None
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        s = cfg_mod._load()
    assert s.license_key == ""


def test_license_key_loads_from_yaml(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("license_key: 'eyJtest'\n", encoding="utf-8")
    import termmon.config as cfg_mod
    cfg_mod._settings = None
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        s = cfg_mod._load()
    assert s.license_key == "eyJtest"
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.venv\Scripts\pytest tests\test_config.py::test_license_key_defaults_to_empty -v
```

Expected: `FAIL — Settings has no field 'license_key'`

- [ ] **Step 3: Add `license_key` to Settings in `termmon/config.py`**

In the `Settings` class (currently line 36), add the new field:

```python
class Settings(BaseModel):
    dashboard: DashboardConfig = Field(default_factory=DashboardConfig)
    brain: BrainConfig = Field(default_factory=BrainConfig)
    services: list[ServiceConfig] = Field(default_factory=list)
    alerts: AlertsConfig = Field(default_factory=AlertsConfig)
    license_key: str = ""
```

- [ ] **Step 4: Add `license_key` to `config.example.yaml`**

Add at the end of `config.example.yaml`:

```yaml
# License key issued after purchase — paste your JWT here
license_key: ""
```

- [ ] **Step 5: Run all config tests to verify they pass**

```powershell
.venv\Scripts\pytest tests\test_config.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 6: Commit**

```powershell
git add termmon/config.py termmon/../config.example.yaml tests/test_config.py
git commit -m "feat: add license_key field to Settings and config.example.yaml"
```

---

## Task 3: Startup license check, HTTP middleware, and `/api/config` tier

**Files:**
- Modify: `termmon/main.py`
- Modify: `tests/test_licensing.py`

- [ ] **Step 1: Write the failing integration tests**

Add to `tests/test_licensing.py` (below all existing tests):

```python
import yaml
import pytest
from fastapi.testclient import TestClient
from termmon.main import app


@pytest.fixture
def no_license_client(rsa_keypair, tmp_path, monkeypatch):
    """TestClient with no license key in config."""
    import termmon.config as cfg_mod
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("", encoding="utf-8")
    cfg_mod._settings = None
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_path)
    with TestClient(app) as client:
        yield client
    cfg_mod._settings = None


@pytest.fixture
def base_license_client(rsa_keypair, tmp_path, monkeypatch):
    """TestClient with a valid Base license."""
    import termmon.config as cfg_mod
    private_pem, public_pem = rsa_keypair
    monkeypatch.setattr(lic_mod, "PUBLIC_KEY", public_pem)
    token = _make_token(private_pem, "base")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump({"license_key": token}), encoding="utf-8")
    cfg_mod._settings = None
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_path)
    with TestClient(app) as client:
        yield client
    cfg_mod._settings = None


def test_health_always_accessible(no_license_client):
    r = no_license_client.get("/health")
    assert r.status_code == 200


def test_setup_page_accessible_without_license(no_license_client):
    r = no_license_client.get("/setup")
    assert r.status_code == 200


def test_api_scan_blocked_without_license(no_license_client):
    r = no_license_client.get("/api/scan")
    assert r.status_code == 403
    assert r.json()["error"] == "license_required"


def test_api_scan_accessible_with_base_license(base_license_client):
    r = base_license_client.get("/api/scan")
    assert r.status_code == 200


def test_api_config_returns_tier_field(base_license_client):
    r = base_license_client.get("/api/config")
    assert r.status_code == 200
    assert r.json()["tier"] == "base"


def test_api_config_returns_tier_none_without_license(no_license_client):
    r = no_license_client.get("/api/config")
    assert r.status_code == 403
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.venv\Scripts\pytest tests\test_licensing.py::test_api_scan_blocked_without_license -v
```

Expected: FAIL — `/api/scan` returns 200 (no gate yet)

- [ ] **Step 3: Add license check to lifespan and HTTP middleware in `termmon/main.py`**

Add this import at the top of `termmon/main.py` (with the other imports):

```python
from fastapi import Request
from termmon.licensing import verify_license, LicenseInfo
```

Replace the existing `lifespan` function (currently lines 84-93) with:

```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.license = verify_license(settings.license_key)
    tasks = []
    if settings.brain.enabled:
        tasks.append(asyncio.create_task(_brain_loop()))
    yield
    for t in tasks:
        t.cancel()
```

Add this middleware immediately after `app = FastAPI(title="Terminal Monitor", lifespan=lifespan)` (currently line 95):

```python
_LICENSE_EXEMPT = {"/health", "/setup", "/api/setup", "/dashboard"}

@app.middleware("http")
async def license_gate(request: Request, call_next):
    if request.url.path in _LICENSE_EXEMPT:
        return await call_next(request)
    if getattr(request.app.state, "license", None) is None:
        from fastapi.responses import JSONResponse
        return JSONResponse(
            status_code=403,
            content={"error": "license_required", "detail": "A valid license key is required"},
        )
    return await call_next(request)
```

- [ ] **Step 4: Update `/api/config` to include `tier` field**

Replace the `get_config` function body (currently lines 154-164) with:

```python
@app.get("/api/config")
async def get_config():
    settings = get_settings()
    license_info: LicenseInfo | None = getattr(app.state, "license", None)
    return {
        "title": settings.dashboard.title,
        "default_model": settings.dashboard.default_model,
        "training_threshold": settings.dashboard.training_threshold,
        "services": [s.model_dump() for s in settings.services],
        "alerts": settings.alerts.model_dump(),
        "brain_enabled": settings.brain.enabled,
        "tier": license_info.tier.name.lower() if license_info else "none",
    }
```

- [ ] **Step 5: Add 403 detection and tier-based tab gating to `termmon/dashboard.html`**

Read `termmon/dashboard.html` to find where `/api/config` is fetched (search for `fetch('/api/config')`). Then make two changes:

**Change A — 403 redirect to /setup:** Immediately after the fetch, add:

```javascript
if (r.status === 403) {
  window.location.href = '/setup';
  return;
}
```

**Change B — Hide/show tabs based on tier:** After parsing the config JSON (the object that includes `tier`), add tab visibility logic. Find where tabs are rendered and add (adapt to match actual tab element IDs in the file):

```javascript
var tier = cfg.tier || 'none';
// Hide Mid+ tabs for Base
if (tier === 'base' || tier === 'none') {
  document.querySelectorAll('[data-tier="mid"]').forEach(function(el){ el.style.display='none'; });
  document.querySelectorAll('[data-tier="diamond"]').forEach(function(el){ el.style.display='none'; });
} else if (tier === 'mid') {
  document.querySelectorAll('[data-tier="diamond"]').forEach(function(el){ el.style.display='none'; });
}
```

Also add `data-tier="mid"` attribute to the AI Chat and Terminal tabs in the HTML, and `data-tier="diamond"` to Brain, Plugins, and Model tabs. (Read the dashboard.html file to find the exact tab elements before editing.)

- [ ] **Step 6: Run integration tests to verify they pass**

```powershell
.venv\Scripts\pytest tests\test_licensing.py -v
```

Expected: all 15 tests PASS

- [ ] **Step 6: Run full test suite to confirm no regressions**

```powershell
.venv\Scripts\pytest -v
```

Expected: all tests PASS (existing tests will need the config fixture to include a license_key — they already use `tmp_path` to control the config path so they'll get `license_key: ""` → `app.state.license = None`. But tests that call API routes through TestClient will now get 403. Check test_api.py and fix any failures by adding a valid license fixture.)

If any existing tests in `tests/test_api.py` fail because routes now return 403, add a `base_license_client` fixture there following the same pattern as in test_licensing.py.

- [ ] **Step 7: Commit**

```powershell
git add termmon/main.py tests/test_licensing.py
git commit -m "feat: add startup license check, HTTP middleware gate, and tier in /api/config"
```

---

## Task 4: Tier guards on `/api/chat`, `/ws/terminal`, `/api/brain/sync`

**Files:**
- Modify: `termmon/main.py`
- Modify: `tests/test_licensing.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_licensing.py`:

```python
@pytest.fixture
def mid_license_client(rsa_keypair, tmp_path, monkeypatch):
    """TestClient with a valid Mid license."""
    import termmon.config as cfg_mod
    private_pem, public_pem = rsa_keypair
    monkeypatch.setattr(lic_mod, "PUBLIC_KEY", public_pem)
    token = _make_token(private_pem, "mid")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump({"license_key": token}), encoding="utf-8")
    cfg_mod._settings = None
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_path)
    with TestClient(app) as client:
        yield client
    cfg_mod._settings = None


@pytest.fixture
def diamond_license_client(rsa_keypair, tmp_path, monkeypatch):
    """TestClient with a valid Diamond license."""
    import termmon.config as cfg_mod
    private_pem, public_pem = rsa_keypair
    monkeypatch.setattr(lic_mod, "PUBLIC_KEY", public_pem)
    token = _make_token(private_pem, "diamond")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump({"license_key": token}), encoding="utf-8")
    cfg_mod._settings = None
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_path)
    with TestClient(app) as client:
        yield client
    cfg_mod._settings = None


def test_chat_blocked_for_base_license(base_license_client):
    r = base_license_client.post("/api/chat", json={"message": "hi", "model": "llama3.2:3b"})
    assert r.status_code == 403


def test_chat_allowed_for_mid_license(mid_license_client, respx_mock):
    respx_mock.post("http://host.docker.internal:11434/api/generate").mock(
        return_value=respx_mock.options(return_value=None)
    )
    # Just confirm the request reaches the handler (not blocked by tier gate)
    # It may fail with 503 (no Ollama) — that's fine, 403 would be wrong
    r = mid_license_client.post("/api/chat", json={"message": "hi", "model": "llama3.2:3b"})
    assert r.status_code != 403


def test_brain_sync_blocked_for_mid_license(mid_license_client):
    r = mid_license_client.post("/api/brain/sync")
    assert r.status_code == 403


def test_brain_sync_allowed_for_diamond_license(diamond_license_client):
    r = diamond_license_client.post("/api/brain/sync")
    assert r.status_code != 403
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.venv\Scripts\pytest tests\test_licensing.py::test_chat_blocked_for_base_license tests\test_licensing.py::test_brain_sync_blocked_for_mid_license -v
```

Expected: FAIL — `/api/chat` and `/api/brain/sync` return wrong status codes (no tier guard yet)

- [ ] **Step 3: Apply `require_tier` to `/api/chat` in `termmon/main.py`**

Add this import at the top of `termmon/main.py` (with the other termmon imports):

```python
from termmon.licensing import verify_license, LicenseInfo, Tier, require_tier
```

Replace the `/api/chat` function signature (currently line 286):

```python
@app.post("/api/chat")
async def chat_with_ai(req: ChatRequest, _: LicenseInfo = require_tier(Tier.MID)):
```

- [ ] **Step 4: Apply tier check to `/ws/terminal` in `termmon/main.py`**

Replace the `/ws/terminal` handler opening (currently lines 362-364) with:

```python
@app.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    info: LicenseInfo | None = getattr(websocket.app.state, "license", None)
    if info is None or info.tier < Tier.MID:
        await websocket.close(code=1008, reason="license_required")
        return
    await websocket.accept()
```

Remove the existing `await websocket.accept()` that was on the original line 365 (it is now in the tier check block).

- [ ] **Step 5: Apply `require_tier` to `/api/brain/sync` in `termmon/main.py`**

Replace the `/api/brain/sync` function signature (currently line 167):

```python
@app.post("/api/brain/sync")
async def brain_sync(_: LicenseInfo = require_tier(Tier.DIAMOND)):
```

- [ ] **Step 6: Run tier guard tests to verify they pass**

```powershell
.venv\Scripts\pytest tests\test_licensing.py -v
```

Expected: all tests PASS

- [ ] **Step 7: Run full suite to confirm no regressions**

```powershell
.venv\Scripts\pytest -v
```

Expected: all tests PASS

- [ ] **Step 8: Commit**

```powershell
git add termmon/main.py tests/test_licensing.py
git commit -m "feat: apply MID tier guard to /api/chat and /ws/terminal, DIAMOND to /api/brain/sync"
```

---

## Task 5: Setup wizard license key field

**Files:**
- Modify: `termmon/main.py` (SetupRequest + setup_post)
- Modify: `termmon/setup.html`
- Modify: `tests/test_setup.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_setup.py`:

```python
def test_setup_post_updates_app_state_license(tmp_path, monkeypatch):
    import yaml
    import termmon.config as cfg_mod
    import termmon.licensing as lic_mod
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    import jwt as pyjwt
    from fastapi.testclient import TestClient
    from termmon.main import app

    # Generate test keypair
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    monkeypatch.setattr(lic_mod, "PUBLIC_KEY", public_pem)

    token = pyjwt.encode(
        {"tier": "mid", "email": "t@t.com", "issued_at": "2026-05-20", "sub": "terminal-monitor"},
        private_pem, algorithm="RS256"
    )

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("", encoding="utf-8")
    cfg_mod._settings = None
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_path)

    with TestClient(app) as client:
        r = client.post("/api/setup", json={"license_key": token})
        assert r.status_code == 200
        assert r.json()["saved"] is True
        assert app.state.license is not None
        assert app.state.license.tier.name == "MID"

    cfg_mod._settings = None
```

- [ ] **Step 2: Run the test to verify it fails**

```powershell
.venv\Scripts\pytest tests\test_setup.py::test_setup_post_updates_app_state_license -v
```

Expected: FAIL — `SetupRequest` has no `license_key` field

- [ ] **Step 3: Update `SetupRequest` and `setup_post` in `termmon/main.py`**

Add `license_key` to the `SetupRequest` model (currently line 273):

```python
class SetupRequest(BaseModel):
    title: str = "Ops Dashboard"
    default_model: str = "ops-brain"
    training_threshold: int = 100
    brain_enabled: bool = False
    brain_url: str = "http://localhost:8000"
    services: list[dict] = []
    cpu_threshold: int = 80
    ram_threshold: int = 80
    gpu_temp_threshold: int = 80
    offline_notify: bool = True
    license_key: str = ""
```

Replace the `setup_post` function (currently lines 402-427) with:

```python
@app.post("/api/setup")
async def setup_post(req: SetupRequest, request: Request):
    from termmon.config import (
        Settings, DashboardConfig, BrainConfig, ServiceConfig, AlertsConfig,
    )
    settings = Settings(
        dashboard=DashboardConfig(
            title=req.title,
            default_model=req.default_model,
            training_threshold=req.training_threshold,
        ),
        brain=BrainConfig(enabled=req.brain_enabled, url=req.brain_url),
        services=[
            ServiceConfig(name=s["name"], port=s["port"], start_command=s.get("start_command"))
            for s in req.services
            if s.get("name") and s.get("port")
        ],
        alerts=AlertsConfig(
            cpu_threshold=req.cpu_threshold,
            ram_threshold=req.ram_threshold,
            gpu_temp_threshold=req.gpu_temp_threshold,
            offline_notify=req.offline_notify,
        ),
        license_key=req.license_key,
    )
    write_settings(settings)
    request.app.state.license = verify_license(req.license_key)
    return {"saved": True}
```

- [ ] **Step 4: Run the test to verify it passes**

```powershell
.venv\Scripts\pytest tests\test_setup.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Add the License Key field to `termmon/setup.html`**

Read `termmon/setup.html` to understand the current structure, then add the License Key section. Insert the following block immediately after `<h1>&gt; TERMINAL MONITOR SETUP</h1>` (line 34) and before `<h2>Dashboard</h2>`:

```html
<h2>License</h2>
<div class="section">
  <div class="field">
    <label>License Key</label>
    <input id="license-key" type="text" placeholder="eyJ..." style="max-width:600px;font-size:11px">
    <div id="license-status" style="margin-top:4px;font-size:11px;color:#888"></div>
  </div>
</div>
```

In the `save()` function in `setup.html`, add `license_key` to the body object (alongside `title`, `default_model`, etc.):

```javascript
license_key: document.getElementById('license-key').value.trim(),
```

In the pre-population block at the bottom of the script, add after `(cfg.services||[]).forEach(...)`:

```javascript
if(cfg.tier && cfg.tier !== 'none'){
  var ls=document.getElementById('license-status');
  ls.style.color='#00ff41';
  ls.textContent='Active tier: '+cfg.tier.charAt(0).toUpperCase()+cfg.tier.slice(1);
}
```

- [ ] **Step 6: Run the full test suite**

```powershell
.venv\Scripts\pytest -v
```

Expected: all tests PASS

- [ ] **Step 7: Commit**

```powershell
git add termmon/main.py termmon/setup.html tests/test_setup.py
git commit -m "feat: add license_key to setup wizard and SetupRequest; update app.state on save"
```

---

## Task 6: Create `termmon-keygen.py` (developer tool)

**Files:**
- Create: `termmon-keygen.py`
- Create: `tests/test_keygen.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_keygen.py`:

```python
import importlib.util
import pathlib
import sys
import jwt as pyjwt


def _load_keygen():
    spec = importlib.util.spec_from_file_location(
        "termmon_keygen",
        pathlib.Path(__file__).parent.parent / "termmon-keygen.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generate_keypair_creates_pem_files(tmp_path):
    kg = _load_keygen()
    public_pem = kg.generate_keypair(tmp_path)
    assert (tmp_path / "private_key.pem").exists()
    assert (tmp_path / "public_key.pem").exists()
    assert "BEGIN PUBLIC KEY" in public_pem


def test_issue_key_produces_valid_jwt(tmp_path):
    kg = _load_keygen()
    public_pem = kg.generate_keypair(tmp_path)
    token = kg.issue_key("mid", "buyer@example.com", tmp_path / "private_key.pem")
    payload = pyjwt.decode(token, public_pem, algorithms=["RS256"], options={"verify_exp": False})
    assert payload["tier"] == "mid"
    assert payload["email"] == "buyer@example.com"
    assert payload["sub"] == "terminal-monitor"
    assert "issued_at" in payload


def test_issue_key_all_tiers(tmp_path):
    kg = _load_keygen()
    public_pem = kg.generate_keypair(tmp_path)
    for tier in ("base", "mid", "diamond"):
        token = kg.issue_key(tier, f"{tier}@test.com", tmp_path / "private_key.pem")
        payload = pyjwt.decode(token, public_pem, algorithms=["RS256"], options={"verify_exp": False})
        assert payload["tier"] == tier


def test_generate_keypair_does_not_overwrite_existing(tmp_path):
    kg = _load_keygen()
    kg.generate_keypair(tmp_path)
    original_mtime = (tmp_path / "private_key.pem").stat().st_mtime
    kg.generate_keypair(tmp_path)  # second call should not overwrite
    assert (tmp_path / "private_key.pem").stat().st_mtime == original_mtime
```

- [ ] **Step 2: Run tests to verify they fail**

```powershell
.venv\Scripts\pytest tests\test_keygen.py -v
```

Expected: `FileNotFoundError` or `ModuleNotFoundError` (termmon-keygen.py doesn't exist)

- [ ] **Step 3: Create `termmon-keygen.py`**

```python
#!/usr/bin/env python3
"""Developer tool for issuing Terminal Monitor license keys. Never ships to buyers."""
from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import date

import jwt


def generate_keypair(key_dir: pathlib.Path) -> str:
    """Generate a 2048-bit RSA keypair in key_dir. Returns public key PEM. No-ops if key exists."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_path = key_dir / "private_key.pem"
    public_path = key_dir / "public_key.pem"

    if private_path.exists():
        print(f"[skip] {private_path} already exists — not overwriting.", file=sys.stderr)
        return public_path.read_text()

    key_dir.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    print(f"[ok] Keypair written to {key_dir}", file=sys.stderr)
    return public_pem.decode()


def issue_key(tier: str, email: str, private_key_path: pathlib.Path) -> str:
    """Sign a JWT license key for the given tier and email."""
    private_pem = private_key_path.read_text()
    return jwt.encode(
        {
            "tier": tier,
            "email": email,
            "issued_at": date.today().isoformat(),
            "sub": "terminal-monitor",
        },
        private_pem,
        algorithm="RS256",
    )


def _default_key_dir() -> pathlib.Path:
    return pathlib.Path.home() / ".termmon"


def main() -> None:
    parser = argparse.ArgumentParser(description="Terminal Monitor license key tool")
    parser.add_argument("--generate-keypair", action="store_true", help="Generate RSA keypair")
    parser.add_argument("--tier", choices=["base", "mid", "diamond"], help="License tier")
    parser.add_argument("--email", help="Buyer email to encode in the key")
    parser.add_argument("--key-dir", type=pathlib.Path, default=_default_key_dir(),
                        help="Directory for keypair files (default: ~/.termmon)")
    args = parser.parse_args()

    if args.generate_keypair:
        public_pem = generate_keypair(args.key_dir)
        print("\nEmbed this PUBLIC_KEY in termmon/licensing.py:\n")
        print(public_pem)
        return

    if args.tier and args.email:
        private_key_path = args.key_dir / "private_key.pem"
        if not private_key_path.exists():
            print(f"[error] Private key not found at {private_key_path}", file=sys.stderr)
            print("Run: python termmon-keygen.py --generate-keypair", file=sys.stderr)
            sys.exit(1)
        token = issue_key(args.tier, args.email, private_key_path)
        print(token)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

```powershell
.venv\Scripts\pytest tests\test_keygen.py -v
```

Expected: all 4 tests PASS

- [ ] **Step 5: Commit**

```powershell
git add termmon-keygen.py tests/test_keygen.py
git commit -m "feat: add termmon-keygen.py developer tool for RSA keypair generation and license key issuance"
```

---

## Task 7: Update `.dockerignore`, generate production keypair, embed public key

**Files:**
- Modify: `.dockerignore`
- Modify: `termmon/licensing.py`

- [ ] **Step 1: Add `termmon-keygen.py` to `.dockerignore`**

Add the following line to `.dockerignore` under the `# Development-only files` section:

```
termmon-keygen.py
```

- [ ] **Step 2: Generate your production RSA keypair**

Run this once. Keep the output safe — the private key file should never leave your machine.

```powershell
python termmon-keygen.py --generate-keypair
```

This writes `~/.termmon/private_key.pem` and `~/.termmon/public_key.pem`, and prints the public key to stdout.

- [ ] **Step 3: Embed the public key in `termmon/licensing.py`**

Copy the entire `-----BEGIN PUBLIC KEY-----` ... `-----END PUBLIC KEY-----` block printed in Step 2.

Replace the `PUBLIC_KEY = ""` line in `termmon/licensing.py` with:

```python
PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
<paste your public key here>
-----END PUBLIC KEY-----"""
```

- [ ] **Step 4: Issue your personal Diamond license key**

```powershell
python termmon-keygen.py --tier diamond --email avaquera@pnw.edu
```

Copy the JWT output.

- [ ] **Step 5: Add your license key to personal `config.yaml`**

Open `config.yaml` (in the project root — it is gitignored, so this stays local) and add:

```yaml
license_key: "eyJ..."   # paste your Diamond JWT here
```

- [ ] **Step 6: Run the full test suite**

```powershell
.venv\Scripts\pytest -v
```

Expected: all tests PASS. The tests patch `PUBLIC_KEY` with their own test key, so they are not affected by the production key you embedded.

- [ ] **Step 7: Start the app and verify the license resolves**

```powershell
.venv\Scripts\python -m uvicorn termmon.main:app --host 127.0.0.1 --port 8084
```

Open `http://localhost:8084/api/config` in a browser. Expected response includes `"tier": "diamond"`.

- [ ] **Step 8: Add `*.pem` to `.gitignore`**

Open `.gitignore` in the project root and add under the secrets section:

```
*.pem
```

This ensures the private key is never accidentally committed even if someone runs `--generate-keypair` inside the project folder.

- [ ] **Step 9: Commit**

```powershell
git add .dockerignore termmon/licensing.py .gitignore
git commit -m "feat: embed production RSA public key, add termmon-keygen.py to dockerignore, guard *.pem in gitignore"
```

- [ ] **Step 10: Push to both repos**

```powershell
git push origin master
git push dev master
```

---

## Done

The licensing system is fully implemented when:
- `pytest` is green
- `http://localhost:8084/api/config` returns `"tier": "diamond"` with your personal license key
- A request to `http://localhost:8084/api/chat` with an empty or Base-tier config returns 403
- The setup wizard at `/setup` shows the License Key field
