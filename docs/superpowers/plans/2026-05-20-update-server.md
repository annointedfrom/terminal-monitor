# Update Server Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Add passive update discovery (GitHub Pages manifests) and one-click Ollama model pull (MID+ tier) to the Terminal Monitor dashboard.

**Architecture:** Startup-lazy: `app.state.update_cache` is initialized to `None` in lifespan; the first `GET /api/update/check` call fetches both manifests (3s timeout each, silent on failure) and caches the result for the session. `POST /api/update/model/pull` proxies to the local Ollama API, gated at MID tier. The dashboard renders a banner from the cached response.

**Tech Stack:** FastAPI, httpx, respx (test mocks), GitHub Pages (static JSON), Ollama local API

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `termmon/version.py` | Create | Single `__version__` constant |
| `termmon/updater.py` | Create | Manifest fetch, version compare, tier filter, Ollama pull helper |
| `termmon/main.py` | Modify | `/api/update/check`, `/api/update/model/pull`, lifespan cache init |
| `termmon/dashboard.html` | Modify | `#update-bar` banner, `_checkUpdates()` JS, `pullModel()` JS |
| `tests/test_updater.py` | Create | Unit tests: version compare, tier filter, manifest parsing (respx) |
| `tests/test_licensing.py` | Modify | Integration tests for new endpoints |

GitHub Pages (`gh-pages` branch on `annointedfrom/terminal-monitor`):

| File | Action |
|---|---|
| `releases.json` | Create â€” app version manifest |
| `models-manifest.json` | Create â€” model version manifest |

---

### Task 1: `termmon/version.py`

**Files:**
- Create: `termmon/version.py`

- [x] **Step 1: Write the failing test**

```python
# tests/test_updater.py  (create new file)
from termmon.version import __version__


def test_version_is_string():
    assert isinstance(__version__, str)
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)
```

- [x] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_updater.py::test_version_is_string -v`

Expected: `ModuleNotFoundError: No module named 'termmon.version'`

- [x] **Step 3: Create `termmon/version.py`**

```python
__version__ = "1.0.0"
```

- [x] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_updater.py::test_version_is_string -v`

Expected: PASS

- [x] **Step 5: Commit**

```bash
git add termmon/version.py tests/test_updater.py
git commit -m "feat: add version constant"
```

---

### Task 2: `termmon/updater.py`

**Files:**
- Create: `termmon/updater.py`
- Modify: `tests/test_updater.py`

- [x] **Step 1: Write the failing unit tests**

Append to `tests/test_updater.py`:

```python
import httpx
import respx
from termmon.updater import _version_gt, _tier_available, check_updates
from termmon.licensing import LicenseInfo, Tier

# â”€â”€ Version comparison â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_version_gt_newer():
    assert _version_gt("1.1.0", "1.0.0") is True


def test_version_gt_equal():
    assert _version_gt("1.0.0", "1.0.0") is False


def test_version_gt_older():
    assert _version_gt("1.0.0", "1.1.0") is False


def test_version_gt_malformed():
    assert _version_gt("bad", "1.0.0") is False


# â”€â”€ Tier filter â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_tier_available_mid_for_mid_model():
    info = LicenseInfo(tier=Tier.MID, email="t@t.com", issued_at="2026-05-20")
    assert _tier_available(info, "mid") is True


def test_tier_available_base_for_mid_model():
    info = LicenseInfo(tier=Tier.BASE, email="t@t.com", issued_at="2026-05-20")
    assert _tier_available(info, "mid") is False


def test_tier_available_no_license():
    assert _tier_available(None, "mid") is False


def test_tier_available_diamond_for_mid_model():
    info = LicenseInfo(tier=Tier.DIAMOND, email="t@t.com", issued_at="2026-05-20")
    assert _tier_available(info, "mid") is True


# â”€â”€ Manifest fetching (respx mocks) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

_APP_URL = "https://annointedfrom.github.io/terminal-monitor/releases.json"
_MODELS_URL = "https://annointedfrom.github.io/terminal-monitor/models-manifest.json"

_APP_JSON = {
    "latest": "1.1.0",
    "changelog": "Brain sync improvements",
    "download_url": "https://github.com/annointedfrom/terminal-monitor/releases/download/v1.1.0/terminal-monitor-v1.1.0.zip",
    "min_tier": "base",
}
_MODELS_JSON = {
    "models": [
        {
            "name": "ops-brain",
            "tag": "ops-brain:v2",
            "description": "Ops model v2",
            "min_tier": "mid",
            "size_gb": 2.0,
        }
    ]
}


async def test_check_updates_has_update():
    with respx.mock:
        respx.get(_APP_URL).mock(return_value=httpx.Response(200, json=_APP_JSON))
        respx.get(_MODELS_URL).mock(return_value=httpx.Response(200, json=_MODELS_JSON))
        result = await check_updates(None)
    assert result["app"]["has_update"] is True
    assert result["app"]["current"] == "1.0.0"
    assert result["app"]["latest"] == "1.1.0"
    assert result["app"]["changelog"] == "Brain sync improvements"


async def test_check_updates_model_available_for_mid():
    mid = LicenseInfo(tier=Tier.MID, email="t@t.com", issued_at="2026-05-20")
    with respx.mock:
        respx.get(_APP_URL).mock(return_value=httpx.Response(200, json=_APP_JSON))
        respx.get(_MODELS_URL).mock(return_value=httpx.Response(200, json=_MODELS_JSON))
        result = await check_updates(mid)
    assert result["models"][0]["available"] is True


async def test_check_updates_model_unavailable_for_base():
    base = LicenseInfo(tier=Tier.BASE, email="t@t.com", issued_at="2026-05-20")
    with respx.mock:
        respx.get(_APP_URL).mock(return_value=httpx.Response(200, json=_APP_JSON))
        respx.get(_MODELS_URL).mock(return_value=httpx.Response(200, json=_MODELS_JSON))
        result = await check_updates(base)
    assert result["models"][0]["available"] is False


async def test_check_updates_app_manifest_unreachable():
    with respx.mock:
        respx.get(_APP_URL).mock(side_effect=httpx.ConnectError("unreachable"))
        respx.get(_MODELS_URL).mock(return_value=httpx.Response(200, json=_MODELS_JSON))
        result = await check_updates(None)
    assert result["app"] is None
    assert isinstance(result["models"], list)


async def test_check_updates_models_manifest_unreachable():
    with respx.mock:
        respx.get(_APP_URL).mock(return_value=httpx.Response(200, json=_APP_JSON))
        respx.get(_MODELS_URL).mock(side_effect=httpx.ConnectError("unreachable"))
        result = await check_updates(None)
    assert result["app"] is not None
    assert result["models"] == []


async def test_check_updates_malformed_json():
    with respx.mock:
        respx.get(_APP_URL).mock(return_value=httpx.Response(200, text="not-json"))
        respx.get(_MODELS_URL).mock(return_value=httpx.Response(200, text="not-json"))
        result = await check_updates(None)
    assert result["app"] is None
    assert result["models"] == []
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_updater.py -v`

Expected: 15 collected, all fail with `ImportError` (module doesn't exist yet)

- [x] **Step 3: Create `termmon/updater.py`**

```python
from __future__ import annotations

import httpx

from termmon.licensing import LicenseInfo, Tier
from termmon.version import __version__

_APP_MANIFEST_URL = "https://annointedfrom.github.io/terminal-monitor/releases.json"
_MODELS_MANIFEST_URL = "https://annointedfrom.github.io/terminal-monitor/models-manifest.json"

_STR_TO_TIER: dict[str, Tier] = {
    "base": Tier.BASE,
    "mid": Tier.MID,
    "diamond": Tier.DIAMOND,
}


def _version_gt(a: str, b: str) -> bool:
    try:
        return tuple(int(x) for x in a.split(".")) > tuple(int(x) for x in b.split("."))
    except Exception:
        return False


def _tier_available(buyer: LicenseInfo | None, min_tier_str: str) -> bool:
    min_tier = _STR_TO_TIER.get(min_tier_str)
    if min_tier is None or buyer is None:
        return False
    return buyer.tier >= min_tier


async def check_updates(license_info: LicenseInfo | None) -> dict:
    result: dict = {"app": None, "models": []}
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            try:
                r = await client.get(_APP_MANIFEST_URL)
                r.raise_for_status()
                data = r.json()
                latest = data.get("latest", "")
                result["app"] = {
                    "current": __version__,
                    "latest": latest,
                    "has_update": _version_gt(latest, __version__),
                    "changelog": data.get("changelog", ""),
                    "download_url": data.get("download_url", ""),
                }
            except Exception:
                pass
            try:
                r = await client.get(_MODELS_MANIFEST_URL)
                r.raise_for_status()
                data = r.json()
                for m in data.get("models", []):
                    result["models"].append({
                        "name": m["name"],
                        "tag": m["tag"],
                        "has_update": True,
                        "size_gb": m.get("size_gb", 0.0),
                        "available": _tier_available(license_info, m.get("min_tier", "mid")),
                    })
            except Exception:
                pass
    except Exception:
        pass
    return result


async def ollama_pull(tag: str) -> None:
    from termmon.scanner.ollama import _ollama_url
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_ollama_url()}/api/pull",
            json={"name": tag, "stream": False},
            timeout=120.0,
        )
        r.raise_for_status()
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_updater.py -v`

Expected: 15 passed

- [x] **Step 5: Commit**

```bash
git add termmon/updater.py tests/test_updater.py
git commit -m "feat: add updater module â€” manifest fetch, version compare, Ollama pull"
```

---

### Task 3: New endpoints in `termmon/main.py`

**Files:**
- Modify: `termmon/main.py`
- Modify: `tests/test_licensing.py`

- [x] **Step 1: Write the failing endpoint tests**

Append to the bottom of `tests/test_licensing.py` (the file already has `mid_license_client` and `base_license_client` fixtures â€” use those):

```python
# â”€â”€ Update server endpoint tests â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€

def test_update_check_accessible_with_base_license(base_license_client):
    r = base_license_client.get("/api/update/check")
    # Returns 200; manifests unavailable in test env so app/models may be null/[]
    assert r.status_code == 200
    body = r.json()
    assert "app" in body
    assert "models" in body


def test_update_check_blocked_without_license(no_license_client):
    r = no_license_client.get("/api/update/check")
    assert r.status_code == 403


def test_model_pull_blocked_for_base_license(base_license_client):
    r = base_license_client.post("/api/update/model/pull", json={"tag": "ops-brain:v2"})
    assert r.status_code == 403


def test_model_pull_reaches_handler_for_mid_license(mid_license_client):
    # Ollama not running in CI â€” expects 503 (no Ollama), NOT 403 (license block)
    r = mid_license_client.post("/api/update/model/pull", json={"tag": "ops-brain:v2"})
    assert r.status_code != 403
```

- [x] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_licensing.py::test_update_check_accessible_with_base_license tests/test_licensing.py::test_update_check_blocked_without_license tests/test_licensing.py::test_model_pull_blocked_for_base_license tests/test_licensing.py::test_model_pull_reaches_handler_for_mid_license -v`

Expected: 4 failures â€” routes do not exist yet

- [x] **Step 3: Modify `termmon/main.py`**

**3a â€” Add import** (add after the existing `from termmon.licensing import ...` import):

```python
from termmon.updater import check_updates, ollama_pull
```

**3b â€” Add `ModelPullRequest` Pydantic model** (add alongside the other `BaseModel` classes, e.g., after `ChatRequest`):

```python
class ModelPullRequest(BaseModel):
    tag: str
```

**3c â€” Initialize cache in lifespan** (add one line after `app.state.license = verify_license(...)` in the `lifespan` function):

```python
app.state.update_cache = None
```

The full lifespan block becomes:

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

**3d â€” Add the two new routes** (add after the existing `GET /api/config` route):

```python
@app.get("/api/update/check")
async def update_check(request: Request):
    if request.app.state.update_cache is None:
        request.app.state.update_cache = await check_updates(
            getattr(request.app.state, "license", None)
        )
    return request.app.state.update_cache


@app.post("/api/update/model/pull", dependencies=[require_tier(Tier.MID)])
async def model_pull(req: ModelPullRequest):
    try:
        await ollama_pull(req.tag)
        return {"pulled": True, "tag": req.tag}
    except Exception:
        return JSONResponse(status_code=503, content={"detail": "Ollama unavailable"})
```

- [x] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_licensing.py -v`

Expected: all pass (the new 4 tests + the existing 26)

Run full suite to check for regressions:

Run: `pytest tests/ -q`

Expected: all pass

- [x] **Step 5: Commit**

```bash
git add termmon/main.py tests/test_licensing.py
git commit -m "feat: add /api/update/check and /api/update/model/pull endpoints"
```

---

### Task 4: Update banner in `termmon/dashboard.html`

**Files:**
- Modify: `termmon/dashboard.html`

No automated tests for this task â€” manual verification after the server is running.

- [x] **Step 1: Add CSS for `#update-bar`**

Find the existing `#error-bar` CSS rule (line ~20):

```css
#error-bar { display: none; background: #1a0a0a; border-bottom: 1px solid #4a2a2a; padding: 3px 12px; color: #e67e22; font-size: 9px; flex-shrink: 0; }
```

Insert a new rule immediately after it:

```css
#update-bar { display: none; background: #0a1a0a; border-bottom: 1px solid #1a4a1a; padding: 3px 12px; color: #2ecc71; font-size: 9px; flex-shrink: 0; align-items: center; gap: 12px; }
```

- [x] **Step 2: Add `#update-bar` div to the HTML**

Find the existing `#error-bar` div (line ~149):

```html
<div id="error-bar"></div>
```

Insert a new div immediately after it:

```html
<div id="update-bar"></div>
```

- [x] **Step 3: Add `_checkUpdates()` and `pullModel()` JavaScript**

Find the block that starts with `async function _loadConfig()` (line ~252). Insert the two new functions immediately before `_loadConfig`:

```javascript
async function _checkUpdates() {
  try {
    var r = await fetch('/api/update/check');
    if (!r.ok) return;
    var data = await r.json();
    var bar = document.getElementById('update-bar');
    var parts = [];
    if (data.app && data.app.has_update) {
      parts.push('<span>App update: v' + data.app.latest + ' â€” ' + data.app.changelog +
        ' &nbsp;<a href="' + data.app.download_url + '" target="_blank" style="color:#27ae60;text-decoration:underline">Download</a></span>');
    }
    if (data.models) {
      data.models.forEach(function(m) {
        if (!m.has_update) return;
        var btnId = 'pull-' + m.tag.replace(/[^a-z0-9]/gi, '-');
        if (m.available) {
          parts.push('<span>' + m.name + ' model update (' + m.size_gb + ' GB)&nbsp;' +
            '<button id="' + btnId + '" onclick="pullModel(\'' + m.tag + '\')" ' +
            'style="font-size:9px;padding:1px 6px;cursor:pointer;background:#1a3a1a;color:#2ecc71;border:1px solid #1a4a1a">Pull Model</button></span>');
        } else {
          parts.push('<span style="color:#666">' + m.name + ' model update available (upgrade tier to pull)</span>');
        }
      });
    }
    if (parts.length > 0) {
      bar.innerHTML = parts.join(' &nbsp;&middot;&nbsp; ');
      bar.style.display = 'flex';
    }
  } catch(_) {}
}

async function pullModel(tag) {
  var btnId = 'pull-' + tag.replace(/[^a-z0-9]/gi, '-');
  var btn = document.getElementById(btnId);
  if (btn) { btn.textContent = 'Pullingâ€¦'; btn.disabled = true; }
  try {
    var r = await fetch('/api/update/model/pull', {
      method: 'POST',
      headers: {'Content-Type': 'application/json'},
      body: JSON.stringify({tag: tag}),
    });
    if (r.ok) {
      if (btn) { btn.textContent = 'Done'; btn.style.color = '#27ae60'; }
    } else {
      var err = await r.json().catch(function() { return {}; });
      if (btn) { btn.textContent = err.detail || 'Failed'; btn.style.color = '#e74c3c'; btn.disabled = false; }
    }
  } catch(_) {
    if (btn) { btn.textContent = 'Error'; btn.style.color = '#e74c3c'; btn.disabled = false; }
  }
}
```

- [x] **Step 4: Call `_checkUpdates()` at page load**

Find the bottom script block (lines ~1185â€“1192):

```javascript
_loadConfig();
_seedHistory();
_requestNotifPermission();
_startAlertPoller();
doScan();
setInterval(fetchScan, 5000);
setInterval(fetchResources, 5000);
setInterval(tickUpdated, 1000);
```

Add `_checkUpdates();` immediately after `_loadConfig();`:

```javascript
_loadConfig();
_checkUpdates();
_seedHistory();
_requestNotifPermission();
_startAlertPoller();
doScan();
setInterval(fetchScan, 5000);
setInterval(fetchResources, 5000);
setInterval(tickUpdated, 1000);
```

- [x] **Step 5: Manual smoke test**

Start the server:

```powershell
.\.venv\Scripts\uvicorn termmon.main:app --port 8084
```

Open `http://localhost:8084/dashboard` in a browser. Confirm:
- No JS errors in console
- `#update-bar` is hidden (manifests not live yet, so no update found)
- No regressions to existing tabs/stats

- [x] **Step 6: Commit**

```bash
git add termmon/dashboard.html
git commit -m "feat: add update banner and model pull button to dashboard"
```

---

### Task 5: GitHub Pages manifest files

**Files:**
- Create: `releases.json` (on `gh-pages` branch of `annointedfrom/terminal-monitor`)
- Create: `models-manifest.json` (on `gh-pages` branch)

This task creates the static manifests that the update server fetches. These files live on a separate orphan branch â€” **do not add them to `master`**.

- [x] **Step 1: Create the orphan `gh-pages` branch**

Run from the project root:

```bash
git checkout --orphan gh-pages
git rm -rf .
```

The working directory is now empty. You are on branch `gh-pages` with no commits.

- [x] **Step 2: Create `releases.json`**

```json
{
  "latest": "1.0.0",
  "changelog": "Initial release",
  "download_url": "https://github.com/annointedfrom/terminal-monitor/releases/download/v1.0.0/terminal-monitor-v1.0.0.zip",
  "min_tier": "base"
}
```

Note: `latest` is `"1.0.0"` â€” same as the installed version â€” so `has_update` will be `false` until a real new release is cut. This is intentional: the banner stays hidden until the developer bumps `latest` to `"1.1.0"`.

- [x] **Step 3: Create `models-manifest.json`**

```json
{
  "models": []
}
```

No models listed yet. Add an entry here when the first `ops-brain` model version is ready to ship.

- [x] **Step 4: Commit and push `gh-pages`**

```bash
git add releases.json models-manifest.json
git commit -m "feat: initial GitHub Pages update manifests"
git push origin gh-pages
```

- [x] **Step 5: Enable GitHub Pages**

In the GitHub UI: `annointedfrom/terminal-monitor` â†’ Settings â†’ Pages â†’ Source: `gh-pages` branch, `/ (root)`. Save.

After ~60 seconds, verify:

```bash
curl https://annointedfrom.github.io/terminal-monitor/releases.json
curl https://annointedfrom.github.io/terminal-monitor/models-manifest.json
```

Both should return the JSON created above.

- [x] **Step 6: Return to master**

```bash
git checkout master
```

- [x] **Step 7: Push master to both remotes**

```bash
git push origin master
git push dev master
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task |
|---|---|
| `termmon/version.py` â€” `__version__ = "1.0.0"` | Task 1 âœ… |
| `termmon/updater.py` â€” `check_updates()`, session cache | Task 2 âœ… |
| Manifest fetch timeout 3s, silent failure | Task 2 âœ… |
| `app.state.update_cache` initialized in lifespan | Task 3 âœ… |
| `GET /api/update/check` â€” lazy cache | Task 3 âœ… |
| `POST /api/update/model/pull` â€” MID+ gate, Ollama proxy | Task 3 âœ… |
| `models-manifest.json` `min_tier` filtering, `available` field | Task 2 âœ… |
| 503 when Ollama unavailable | Task 3 âœ… |
| 403 for BASE tier on model pull | Task 3 âœ… |
| Dashboard banner with download link | Task 4 âœ… |
| Model pull button with spinner / Done state | Task 4 âœ… |
| BASE buyer sees greyed-out model (not available) | Task 4 âœ… |
| `releases.json` + `models-manifest.json` on `gh-pages` | Task 5 âœ… |
| `tests/test_updater.py` with respx mocks | Task 2 âœ… |
| Silent on both manifest failures | Task 2 âœ… |

**Placeholder scan:** No TBDs, no "handle edge cases" vagueness, no forward references to undefined types.

**Type consistency:** `LicenseInfo`, `Tier`, `ModelPullRequest` used consistently across all tasks.
