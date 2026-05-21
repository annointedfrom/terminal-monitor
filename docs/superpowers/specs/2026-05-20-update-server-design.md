# Update Server — Design Spec

**Date:** 2026-05-20
**Project:** Terminal Monitor (ops-platform feature 3 of 5)
**Status:** Approved — ready for implementation planning

---

## Goal

Give buyers a way to discover and apply app updates and model updates from inside the Terminal Monitor dashboard. App updates are download-link only (buyer controls the install). Model updates are one-click pulls via the local Ollama API, gated by license tier.

---

## Business Model

- **App updates** available to all licensed tiers (BASE+). Major version upgrades (v2, v3) are optional paid upgrades — buyers on v1 see the banner but the download link leads to a purchase page, not a free zip.
- **Model updates** available to MID+ tiers only (since AI chat is a MID feature). New model versions are pushed by the developer; buyers pull on demand.
- **No forced updates** — the check is passive (startup + manual trigger), the apply step requires explicit buyer action.

---

## Architecture

### Overview

```
Terminal Monitor startup
  → termmon/updater.py fetches releases.json from GitHub Pages (3s timeout)
  → termmon/updater.py fetches models-manifest.json from GitHub Pages (3s timeout)
  → results cached in app.state.update_cache for session lifetime
  → GET /api/update/check returns cached result to frontend
  → dashboard renders banner if has_update is true

Buyer clicks "Pull Model"
  → POST /api/update/model/pull (requires MID tier)
  → calls POST http://localhost:11434/api/pull (Ollama local API)
  → returns pulled: true / 503 if Ollama unavailable
```

### Components

**`termmon/version.py`** (new)
- Single constant: `__version__ = "1.0.0"`
- Source of truth for the current installed version
- Imported by `updater.py` for comparison and by `main.py` for startup logging

**`termmon/updater.py`** (new)
- `check_updates(license_info: LicenseInfo | None) -> dict` — fetches both manifests, compares versions, filters models by tier, returns structured result
- Manifest fetch timeout: 3s; on any failure returns `{"app": None, "models": []}` silently
- Results cached in `app.state.update_cache`; refreshed only on restart

**`termmon/main.py`** (modified)
- Lifespan: calls `check_updates` and stores result in `app.state.update_cache`
- `GET /api/update/check` — returns cached update status
- `POST /api/update/model/pull` — requires `Tier.MID`; accepts `{"tag": "ops-brain:v2"}`; calls Ollama pull API; returns `{"pulled": True, "tag": "..."}` or 503

**`termmon/dashboard.html`** (modified)
- Update banner rendered if `app.has_update` or any `model.has_update` is true
- App update: green banner with changelog text + "Download v1.1.0" link
- Model update: banner with model name + "Pull Model" button; button shows spinner during pull, "Done" on success

**Manifest hosting — GitHub Pages**
- Branch: `gh-pages` on `annointedfrom/terminal-monitor`
- `releases.json` — updated manually when cutting a new app release
- `models-manifest.json` — updated when publishing a new Ollama model version
- URLs:
  - `https://annointedfrom.github.io/terminal-monitor/releases.json`
  - `https://annointedfrom.github.io/terminal-monitor/models-manifest.json`

---

## Data Shapes

### `releases.json`

```json
{
  "latest": "1.1.0",
  "changelog": "Brain sync improvements, faster port scanning",
  "download_url": "https://github.com/annointedfrom/terminal-monitor/releases/download/v1.1.0/terminal-monitor-v1.1.0.zip",
  "min_tier": "base"
}
```

### `models-manifest.json`

```json
{
  "models": [
    {
      "name": "ops-brain",
      "tag": "ops-brain:v2",
      "description": "Terminal Monitor ops model v2 — faster, better at port analysis",
      "min_tier": "mid",
      "size_gb": 2.0
    }
  ]
}
```

### `GET /api/update/check` response

```json
{
  "app": {
    "current": "1.0.0",
    "latest": "1.1.0",
    "has_update": true,
    "changelog": "Brain sync improvements, faster port scanning",
    "download_url": "https://github.com/annointedfrom/terminal-monitor/releases/download/v1.1.0/terminal-monitor-v1.1.0.zip"
  },
  "models": [
    {
      "name": "ops-brain",
      "tag": "ops-brain:v2",
      "has_update": true,
      "size_gb": 2.0,
      "available": true
    }
  ]
}
```

`available` on each model is `true` only if the buyer's license tier meets `min_tier`. BASE buyers see `available: false` on MID-only models; the frontend greys out the pull button.

If either manifest fetch fails, the corresponding key is `null` (app) or `[]` (models) — no banner shown.

### `POST /api/update/model/pull` request/response

Request: `{"tag": "ops-brain:v2"}`

Success: `{"pulled": true, "tag": "ops-brain:v2"}`

Failure (Ollama down): `503 {"detail": "Ollama unavailable"}`

---

## Files Created / Modified

| File | Action | Purpose |
|---|---|---|
| `termmon/version.py` | Create | `__version__` constant |
| `termmon/updater.py` | Create | Manifest fetch, version comparison, cache |
| `termmon/main.py` | Modify | `/api/update/check`, `/api/update/model/pull`, lifespan update cache |
| `termmon/dashboard.html` | Modify | Update banner, model pull button + progress |
| `tests/test_updater.py` | Create | Version comparison, manifest parsing (respx mocks) |
| `gh-pages/releases.json` | Create | App version manifest (GitHub Pages branch) |
| `gh-pages/models-manifest.json` | Create | Model version manifest (GitHub Pages branch) |

---

## Security Notes

- Manifest URLs are public — no secrets in the manifest files
- Model pull calls the **local** Ollama API only (`localhost:11434`) — no external model server needed
- `/api/update/model/pull` is tier-gated at MID; a BASE licensee cannot trigger pulls
- The download URL for app updates points to GitHub Releases — buyer downloads and installs manually; Terminal Monitor never writes to its own installation directory
- No license re-validation against a remote server — offline operation preserved

---

## Error Handling

| Scenario | Behavior |
|---|---|
| GitHub Pages unreachable | Silent — no banner, no error shown to buyer |
| Manifest JSON malformed | Silent — treat as no update available |
| Ollama unavailable during model pull | 503 returned; frontend shows "Ollama not running" message |
| Buyer already has latest version | `has_update: false`; no banner rendered |
| BASE tier buyer on model pull endpoint | 403 from `require_tier(Tier.MID)` |

---

## Out of Scope (this spec)

- Automatic background update application (buyer always clicks to apply)
- Delta/patch updates (full zip download only for app updates)
- Update rollback
- Paid upgrade gate on download URL (manual for now — link goes to Gumroad/GitHub)
- Multi-model support beyond `ops-brain` (manifest supports it, dashboard only shows one for v1)
