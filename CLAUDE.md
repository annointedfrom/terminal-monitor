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
| Mid | $29 (one-time) | + Memory server (SQLite), MEMORY tab, plugin architecture, multi-shell terminal (PS/CMD/Bash), MCP start/kill, AI chat, update notifications |
| Diamond | $79 (one-time) | + NeuroLinked brain sync, AI filesystem awareness, training data export, PHANTOM character, memory insights, priority support |

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

Expected: 180 passed (v2.1.0 — new features tested via integration, not unit tests)

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

## New-buyer license issuance (automated)

License delivery is **fully automated** via the Gumroad webhook pipeline (live 2026-05-23):

1. Buyer purchases on Gumroad
2. Gumroad POSTs to `https://landing-eight-rho-26.vercel.app/api/gumroad-webhook?secret=<GUMROAD_WEBHOOK_SECRET>`
3. Webhook generates an RS256 JWT (Mid/Diamond) or sends a welcome email (Base)
4. Buyer receives the license key email from `noreply@angelvaquerajr.dev` within seconds

### Email pipeline components

| Component | Location | Purpose |
|---|---|---|
| Webhook handler | `landing/api/gumroad-webhook.ts` | Vercel serverless — validates secret, generates JWT, sends email |
| Email domain | `angelvaquerajr.dev` (Cloudflare DNS) | Verified in Resend — DKIM, SPF, MX all green |
| Email sender | Resend API | Transactional delivery |
| Vercel env vars | `GUMROAD_WEBHOOK_SECRET`, `RESEND_API_KEY`, `RESEND_FROM_EMAIL`, `TERMMON_PRIVATE_KEY` | All set in Vercel dashboard |

### Manual fallback (if webhook fails)

1. `python termmon-keygen.py --email <buyer-email> --tier mid`
2. Email the JWT manually

## Security (audit 2026-05-22, updated 2026-05-26)

- **✅ JWT expiry** — `licensing.py` verifies `exp` by default. Both `termmon-keygen.py` and the Gumroad webhook set `exp: 2099`.
- **✅ `/api/setup` license downgrade** — fixed in `main.py`: existing valid license is never downgraded to `None`.
- **✅ WebSocket terminal RCE** — `terminal_enabled` defaults to `False`. Per-shell blocked patterns: `_TERMINAL_BLOCKED` (PowerShell), `_TERMINAL_BLOCKED_CMD` (cmd), `_TERMINAL_BLOCKED_BASH` (bash).
- **✅ MCP start/kill** — `POST /api/mcp/{name}/start` and `/kill` look up commands from the local config file by name only. The HTTP client sends only the server name, never a command string.
- **✅ AI filesystem context** — `_fs_context()` injects a scoped home-dir listing (top level only) and drive stats. No recursive traversal, no file content read.

## New in v2.1.0 (2026-05-26)

- Multi-shell terminal: PowerShell, CMD, Git Bash via `?shell=` WebSocket query param
- AI chat now knows your file system (home dir entries + drive usage injected into system prompt)
- MCP start/kill from dashboard — API-gated, config-bound
- PHANTOM character — Diamond-only, triple-click unlock, cybersecurity-themed abilities
- Training data export (`GET /api/training/export`, Diamond)

## Git remotes

| Remote | Repo | Use |
|---|---|---|
| `origin` | annointedfrom/terminal-monitor | Public open-source — push after release |
| `dev` | annointedfrom/terminal-monitor-dev | Private dev — push feature branches |
