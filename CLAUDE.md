# CLAUDE.md — terminal-monitor (Layer 2)

> Parent: [[../CLAUDE|Sandbox/projects Layer-2]]

## What this is

**Terminal Monitor** — a real-time ops dashboard for AI developers. Monitors ports, processes, MCP servers, CPU/RAM/GPU, and shell history from a browser UI on port 8084. Sold commercially via Gumroad with offline RS256 JWT license keys.

## Commercial setup

| Channel | URL | Purpose |
|---|---|---|
| Public repo | https://github.com/annointedfrom/terminal-monitor | Open-source (Base tier free) |
| Private dev repo | https://github.com/annointedfrom/terminal-monitor-dev | Feature branches before public release |
| Update server | https://annointedfrom.github.io/terminal-monitor/ | releases.json + models-manifest.json |
| Portfolio page | https://portfolio-indol-nine-54.vercel.app/ai | Tier comparison + purchase links |

## Tiers

| Tier | Price | Features |
|---|---|---|
| Base | Free | Port scanner, process monitor, MCP detection, resource graphs, shell history, alerts, Docker |
| Mid | $29 (one-time) | + Memory server (SQLite), MEMORY tab, plugin architecture (RS256 per-plugin keys), update notifications |
| Diamond | $79 (one-time) | + NeuroLinked brain sync every 60s, memory insights, priority support |

## License system

- Offline RS256 JWT — no phone-home, works air-gapped
- Public key hardcoded in `termmon/licensing.py`
- Private key lives on Angel's machine only (never committed, never in repo)
- `termmon-keygen.py` issues buyer JWTs — `python termmon-keygen.py --email <buyer> --tier mid|diamond`
- Buyer adds the JWT to their `config.yaml` under `license_key:`

## Key files

| File | Role |
|---|---|
| `termmon/main.py` | FastAPI app — all routes + lifespan |
| `termmon/licensing.py` | RS256 JWT verify, Tier enum, require_tier() |
| `termmon/memory.py` | SQLite memory store (MID+) |
| `termmon/plugin_loader.py` | Plugin discovery + loading (MID+) |
| `termmon/brain.py` | NeuroLinked sync (Diamond) |
| `termmon/updater.py` | App + model update checks via gh-pages manifests |
| `termmon/config.py` | Pydantic settings from config.yaml |
| `termmon/version.py` | `__version__` — bump here before each release |
| `termmon-keygen.py` | Issues buyer license keys (developer only, not shipped in zip) |
| `scripts/gumroad_setup.py` | Creates/updates Gumroad product listings via API |
| `models/` | Ops-brain fine-tune pipeline (future paid add-on) |

## Run

```powershell
.\.venv\Scripts\uvicorn termmon.main:app --port 8084 --reload
```

## Test

```powershell
.\.venv\Scripts\pytest --tb=short -q
```

Expected: 180 passed (v2.0.0)

## Docker

```powershell
docker-compose up
```

## Release workflow (when shipping a new version)

1. Bump `__version__` in `termmon/version.py`
2. Run full test suite — 0 failures
3. Update `termmon/updater.py` mock version in `tests/test_updater.py` to match new version+1
4. Build zip: zip the project root (exclude .venv, .git, __pycache__, data/, config.yaml)
5. `git tag vX.Y.Z && git push origin vX.Y.Z`
6. `gh release create vX.Y.Z terminal-monitor-vX.Y.Z.zip ...`
7. Update `gh-pages:releases.json` with new version + download URL
8. `git push origin gh-pages`

## New-buyer license issuance

1. Buyer purchases Mid or Diamond on Gumroad
2. Angel runs: `python termmon-keygen.py --email <buyer-email> --tier mid`
3. Angel emails the JWT to the buyer
4. Buyer adds it to their `config.yaml` under `license_key:`

## Git remotes

| Remote | Repo | Use |
|---|---|---|
| `origin` | annointedfrom/terminal-monitor | Public open-source — push after release |
| `dev` | annointedfrom/terminal-monitor-dev | Private dev — push feature branches |
