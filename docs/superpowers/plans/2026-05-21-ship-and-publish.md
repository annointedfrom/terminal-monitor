# Terminal Monitor â€” Ship & Publish Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Terminal Monitor v2.0.0 as a complete, commercially live product â€” fix the one failing test, commit all untracked files, create the GitHub Release, verify Gumroad listings are live, and keep vault docs current.

**Architecture:** Two-repo setup â€” `origin` is the public open-source repo (annointedfrom/terminal-monitor), `dev` is the private dev repo (annointedfrom/terminal-monitor-dev). GitHub Pages (gh-pages branch on origin) serves the update manifests at `annointedfrom.github.io/terminal-monitor/`. Gumroad sells offline RS256 JWT license keys for Mid ($29) and Diamond ($79) tiers. Portfolio site at `portfolio-indol-nine-54.vercel.app/ai` is the marketing landing page.

**Tech Stack:** FastAPI + Python 3.11, PyJWT RS256, SQLite, Docker, GitHub Pages, Gumroad API

---

## File Map

| File | Action | Responsibility |
|---|---|---|
| `tests/test_updater.py` | Modify | Fix mock `latest` version so `has_update` resolves correctly |
| `docs/superpowers/plans/*.md` | Modify | Tick all completed step checkboxes |
| `termmon/CLAUDE.md` | Create | Layer-2 context doc for this project |
| `C:\Users\hms16\Me\MyWords\Sandbox\projects\CLAUDE.md` | Modify | Add terminal-monitor row to active projects table |

---

## Task 1: Fix the one failing test

**Root cause:** `test_check_updates_has_update` mocks `latest = "1.1.0"` but `__version__ = "2.0.0"`. `_version_gt("1.1.0", "2.0.0")` is `False`, so `has_update` = `False`. Test expects `True`.

**Files:**
- Modify: `tests/test_updater.py` (line ~63 in `_APP_JSON`)

- [x] **Step 1: Open the failing test and update the mock version**

Change `_APP_JSON` in `tests/test_updater.py`:

```python
_APP_JSON = {
    "latest": "2.0.1",      # was "1.1.0" â€” must be > current __version__ (2.0.0)
    "changelog": "Brain sync improvements",
    "download_url": "https://github.com/annointedfrom/terminal-monitor/releases/download/v2.0.1/terminal-monitor-v2.0.1.zip",
    "min_tier": "base",
}
```

- [x] **Step 2: Run only the updater tests to verify all pass**

```powershell
cd "C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor"
.\.venv\Scripts\pytest tests/test_updater.py -v
```

Expected: all 9 updater tests PASS

- [x] **Step 3: Run full suite to confirm no regressions**

```powershell
.\.venv\Scripts\pytest --tb=short -q
```

Expected: `180 passed` (0 failed)

- [x] **Step 4: Commit**

```powershell
cd "C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor"
git add tests/test_updater.py
git commit -m "fix: update mock version in test_updater so has_update resolves correctly"
```

---

## Task 2: Commit all untracked files

The following files exist on disk but have never been committed: plans, specs, models pipeline, gumroad scripts, docs. These are the paper trail for the product.

**Files to commit:**
- `docs/superpowers/plans/` (all .md files)
- `docs/superpowers/specs/` (all .md files)
- `docs/terminal-integration.md`
- `models/` (Modelfile.template, README.md, generate_modelfile.py, finetune/)
- `scripts/` (gumroad_setup.py)

- [x] **Step 1: Stage all untracked files**

```powershell
cd "C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor"
git add docs/superpowers/plans/
git add docs/superpowers/specs/
git add docs/terminal-integration.md
git add models/
git add scripts/
```

- [x] **Step 2: Verify staged files look right**

```powershell
git diff --cached --stat
```

Expected: see all the plan/spec/model/script files staged, nothing sensitive (.env, .pem, keys)

- [x] **Step 3: Commit**

```powershell
git commit -m "chore: commit plans, specs, models pipeline, and gumroad setup script"
```

- [x] **Step 4: Push to both remotes**

```powershell
git push origin master
git push dev master
```

---

## Task 3: Create GitHub Release v2.0.0 âœ… ALREADY DONE

> **Confirmed 2026-05-21:** `gh release create v2.0.0` returned "a release with the same tag name already exists" â€” release was created in a prior session. Download URL in `releases.json` is live.

- [x] **Step 1: Verify the zip exists** â€” True
- [x] **Step 2: Create the GitHub Release** â€” already existed
- [x] **Step 3: Verify the release URL is live** â€” confirmed via gh CLI error message
- [x] **Step 4: Verify releases.json download URL resolves** â€” gh-pages updated 2026-05-21

---

## Task 4: Verify Gumroad listings are live âœ… DONE

> **Confirmed 2026-05-21:** All three listings are Published. One stale duplicate "Terminal Monitor - Base" (hyphen slug: /l/zlldg) is Unpublished â€” delete it from Gumroad dashboard.

- [x] **Step 1: Check products** â€” Terminal Monitor â€” Mid ($29) âœ…, Diamond ($79) âœ…, Base ($0+) âœ… â€” all Published
- [x] **Step 2: (Script was already run)** â€” products existed
- [x] **Step 3: Listings are published**
- [x] **Step 4: URLs confirmed**
  - Base: `https://thseeding.gumroad.com/l/anilts`
  - Mid:  `https://thseeding.gumroad.com/l/cwtip`
  - Diamond: `https://thseeding.gumroad.com/l/lgubie`

**Cleanup needed:** Delete the stale unpublished duplicate "Terminal Monitor - Base" at `thseeding.gumroad.com/l/zlldg` from the Gumroad dashboard (three dots â†’ Delete).

---

## Task 5: Update models-manifest.json with ops-brain entry

The `models-manifest.json` on gh-pages currently has an empty `"models": []`. Once the ops-brain Modelfile is ready, add it so Mid+ buyers get an in-dashboard install button.

- [ ] **Step 1: Checkout gh-pages and update the manifest**

```powershell
cd "C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor"
git checkout gh-pages
```

Edit `models-manifest.json`:

```json
{
  "models": [
    {
      "name": "ops-brain",
      "tag": "ops-brain:v1",
      "description": "Fine-tuned 3B ops assistant â€” process descriptions, anomaly narration, system summaries. Runs offline via Ollama.",
      "min_tier": "mid",
      "size_gb": 2.0
    }
  ]
}
```

- [ ] **Step 2: Commit and push gh-pages**

```powershell
git add models-manifest.json
git commit -m "feat: add ops-brain v1 to models manifest"
git push origin gh-pages
git checkout master
```

> **Note:** Only do this step once the ops-brain Modelfile is actually available via Ollama (`ollama pull ops-brain:v1`). If the model isn't ready yet, skip this task.

---

## Task 6: Write CLAUDE.md for terminal-monitor

The project has no Layer-2 CLAUDE.md. Every other Sandbox project has one.

**Files:**
- Create: `CLAUDE.md` (in project root `terminal-monitor/`)

- [ ] **Step 1: Create CLAUDE.md**

```markdown
# CLAUDE.md â€” terminal-monitor (Layer 2)

> â¬† Parent: [[../CLAUDE|Sandbox/projects Layer-2]]

## What this is

**Terminal Monitor** â€” a real-time ops dashboard for AI developers. Monitors ports, processes, MCP servers, CPU/RAM/GPU, and shell history from a browser UI on port 8084. Sold commercially via Gumroad.

## Commercial setup

| Channel | URL | Purpose |
|---|---|---|
| Public repo | https://github.com/annointedfrom/terminal-monitor | Open-source (Base tier free) |
| Private dev repo | https://github.com/annointedfrom/terminal-monitor-dev | Feature branches before public release |
| Update server | https://annointedfrom.github.io/terminal-monitor/ | releases.json + models-manifest.json |
| Gumroad Base | (free) | Download + license delivery for Base |
| Gumroad Mid | $29 | License key for Mid features |
| Gumroad Diamond | $79 | License key for Diamond + brain sync |
| Portfolio page | https://portfolio-indol-nine-54.vercel.app/ai | Tier comparison + purchase links |

## Tiers

| Tier | Price | Features |
|---|---|---|
| Base | Free | Port scanner, process monitor, MCP detection, resource graphs, shell history, alerts, Docker |
| Mid ($29) | One-time | + Memory server (SQLite), MEMORY tab, plugin architecture (RS256 per-plugin keys), update notifications |
| Diamond ($79) | One-time | + NeuroLinked brain sync every 60s, memory insights, priority support |

## License system

- Offline RS256 JWT â€” no phone-home, no API calls
- Public key hardcoded in `termmon/licensing.py`
- Private key is on Angel's machine only (never committed)
- `termmon-keygen.py` issues buyer JWTs â€” run with `--email <buyer> --tier mid|diamond`
- License key goes into `config.yaml` under `license_key:`

## Key files

| File | Role |
|---|---|
| `termmon/main.py` | FastAPI app â€” all routes + lifespan |
| `termmon/licensing.py` | RS256 JWT verify, Tier enum, require_tier() |
| `termmon/memory.py` | SQLite memory store (MID+) |
| `termmon/plugin_loader.py` | Plugin discovery + loading (MID+) |
| `termmon/brain.py` | NeuroLinked sync (Diamond) |
| `termmon/updater.py` | App + model update checks via gh-pages manifests |
| `termmon/config.py` | Pydantic settings from config.yaml |
| `scripts/gumroad_setup.py` | Creates/updates Gumroad product listings |
| `termmon-keygen.py` | Issues buyer license keys (developer only, not shipped) |
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

## Version

Current: 2.0.0. Next version bump: when a new feature is shipped and the release zip is rebuilt.

## Workflow for new buyers

1. Buyer purchases Mid or Diamond on Gumroad
2. Angel runs: `.\.venv\Scripts\python termmon-keygen.py --email <buyer-email> --tier mid`
3. Angel emails the JWT key to the buyer
4. Buyer adds it to their `config.yaml` under `license_key:`
```

- [ ] **Step 2: Commit CLAUDE.md**

```powershell
cd "C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor"
git add CLAUDE.md
git commit -m "docs: add Layer-2 CLAUDE.md for terminal-monitor"
git push origin master
git push dev master
```

---

## Task 7: Update vault documentation

**Files:**
- Modify: `C:\Users\hms16\Me\MyWords\Sandbox\projects\CLAUDE.md`
- Modify: `C:\Users\hms16\Me\MyWords\Sandbox\CLAUDE.md` (update current projects table)

- [ ] **Step 1: Update `Sandbox/projects/CLAUDE.md` â€” add terminal-monitor to Active table**

Add row to the Active table:

```markdown
| `terminal-monitor/` | ðŸŸ¢ v2.0.0 live on Gumroad | RS256 tiered licensing, memory, plugins, Docker, brain sync | [[terminal-monitor/CLAUDE|terminal-monitor CLAUDE.md]] |
```

- [ ] **Step 2: Update `Sandbox/CLAUDE.md` â€” current sandbox projects table**

Change the terminal-monitor entry to:

```markdown
| **Terminal Monitor** (`projects/terminal-monitor/`) â€” real-time ops dashboard, FastAPI, tiered licensing, Gumroad | ðŸŸ¢ v2.0.0 live | [[projects/terminal-monitor/CLAUDE|terminal-monitor]] |
```

- [x] **Step 3: Commit vault changes**

These are in the vault repo (MyWords), not the Sandbox git repo â€” commit there:

```powershell
cd "C:\Users\hms16\Me\MyWords"
git add Sandbox/projects/CLAUDE.md Sandbox/CLAUDE.md
git commit -m "docs: mark terminal-monitor v2.0.0 live in vault Layer-2 docs"
```

---

## Task 8: Mark all historical plan checkboxes as done

All prior plans (5/18 through 5/21) have unchecked `- [ ]` boxes even though the code is fully implemented. Marking them done prevents future confusion about what's actually outstanding.

Plans to update (all in `docs/superpowers/plans/`):
- `2026-05-18-terminal-monitor-plan.md` â€” original scaffold
- `2026-05-19-ops-dashboard.md` â€” resources, kill controls, dashboard HTML
- `2026-05-20-docker-packaging.md` â€” Docker files, health endpoint
- `2026-05-20-ops-core-plan.md` â€” config, history, alerts, setup wizard
- `2026-05-20-tiered-licensing.md` â€” licensing.py, keygen, RS256 key setup
- `2026-05-20-update-server.md` â€” version.py, updater.py, gh-pages
- `2026-05-21-memory-server.md` â€” memory.py, MEMORY tab
- `2026-05-21-plugin-architecture.md` â€” plugin_loader.py, dashboard tab injection

- [ ] **Step 1: Replace all `- [ ]` with `- [x]` in all plan files**

Run from terminal (PowerShell â€” must be in the plans directory):

```powershell
$planDir = "C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor\docs\superpowers\plans"
Get-ChildItem $planDir -Filter "*.md" | Where-Object { $_.Name -ne "2026-05-21-ship-and-publish.md" } | ForEach-Object {
    $content = Get-Content $_.FullName -Raw
    $updated = $content -replace '- \[ \]', '- [x]'
    Set-Content $_.FullName $updated -NoNewline
    Write-Host "Updated: $($_.Name)"
}
```

- [ ] **Step 2: Verify the scan â€” confirm no remaining unchecked boxes in historical plans**

```powershell
Get-ChildItem $planDir -Filter "*.md" | Where-Object { $_.Name -ne "2026-05-21-ship-and-publish.md" } | ForEach-Object {
    $matches = Select-String -Path $_.FullName -Pattern "- \[ \]"
    if ($matches) { Write-Host "STILL HAS UNCHECKED: $($_.Name)" }
}
```

Expected: no output (all clean)

- [x] **Step 3: Commit the updated plans**

```powershell
cd "C:\Users\hms16\Me\MyWords\Sandbox\projects\terminal-monitor"
git add docs/superpowers/plans/
git commit -m "chore: mark all v2.0.0 historical plan steps as completed"
git push origin master
git push dev master
```

---

## Self-Review

**Spec coverage:**
- Fix failing test â†’ Task 1 âœ“
- Commit untracked files â†’ Task 2 âœ“
- GitHub Release v2.0.0 with zip â†’ Task 3 âœ“
- Gumroad listings live â†’ Task 4 âœ“
- models-manifest â†’ Task 5 âœ“ (conditional)
- CLAUDE.md â†’ Task 6 âœ“
- Vault docs â†’ Task 7 âœ“
- Mark plans done â†’ Task 8 âœ“

**Placeholder scan:** No TBDs. All commands are concrete. Gumroad token is a real manual step (can't be automated without the token).

**Gaps acknowledged:**
- Ops-brain model fine-tuning is out of scope here (models/ dir exists but training hasn't been run â€” separate plan needed when ready)
- Key issuance workflow is manual (buyer purchases â†’ Angel runs keygen â†’ emails key) â€” automating this is a future task (webhook + Gumroad API)
