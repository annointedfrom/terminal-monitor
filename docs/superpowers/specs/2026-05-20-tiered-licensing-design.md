# Tiered Licensing — Design Spec

**Date:** 2026-05-20
**Project:** Terminal Monitor (ops-platform feature 2 of 5)
**Status:** Approved — ready for implementation planning

---

## Goal

Gate Terminal Monitor features behind three purchasable tiers using offline RS256-signed JWT license keys. Every install requires a key; no anonymous or free-trial usage. Keys are issued manually by the developer and verified locally by the app — no internet required after delivery.

---

## Business Model

- **One-time purchase per tier.** Buyers pay once and own that tier permanently.
- **Paid upgrade path.** Mid = Base price + delta. Diamond = Mid price + delta.
- **Major version upgrades** (v2, v3) are optional paid upgrades delivered via the update server (ops-platform feature 3).
- **Key issuance is manual.** Developer runs `termmon-keygen.py` on their local machine after each purchase and delivers the key string to the buyer (email, Gumroad, etc.).

---

## Tiers

| Feature | Base | Mid | Diamond |
|---|---|---|---|
| Dashboard (ports, services, health checks) | ✅ | ✅ | ✅ |
| Resource monitoring + scan history | ✅ | ✅ | ✅ |
| Alerts (CPU, memory, GPU, offline services) | ✅ | ✅ | ✅ |
| AI chat tab (Ollama integration) | ❌ | ✅ | ✅ |
| Terminal tab (PowerShell WebSocket) | ❌ | ✅ | ✅ |
| Brain sync (NeuroLinked integration) | ❌ | ❌ | ✅ |
| Plugin architecture | ❌ | ❌ | ✅ |
| Custom model training | ❌ | ❌ | ✅ |
| Priority support + updates | ❌ | ❌ | ✅ |

---

## License Key Format

Keys are RS256-signed JWTs with the following payload:

```json
{
  "tier": "base" | "mid" | "diamond",
  "email": "buyer@example.com",
  "issued_at": "2026-05-20",
  "sub": "terminal-monitor"
}
```

- No expiry field — keys are perpetual for the issued major version.
- The `sub` claim scopes keys to this product (prevents key reuse across future products).
- The RSA private key (2048-bit minimum) lives only on the developer's machine and is never committed to any repository.
- The RSA public key is embedded as a constant in `termmon/licensing.py` and ships with the app.

---

## Architecture

### Components

**`termmon-keygen.py`** (developer tool, not shipped to buyers)
- Loads RSA private key from a local file (`~/.termmon/private_key.pem` or path arg)
- Accepts: `--tier`, `--email`
- Accepts: `--generate-keypair` to create a new RSA keypair (explicit, never automatic)
- Outputs: signed JWT string to stdout

**`termmon/licensing.py`** (ships with app)
- Embeds the RSA public key as a module-level constant
- `verify_license(key_string: str) -> LicenseInfo | None` — returns parsed tier or None if invalid/missing
- `LicenseInfo` dataclass: `tier: Tier`, `email: str`, `issued_at: str`
- `Tier` enum: `BASE`, `MID`, `DIAMOND` with ordering (`BASE < MID < DIAMOND`)
- `requires_tier(minimum: Tier)` — FastAPI dependency for route guards

**`termmon/config.py`** (existing, modified)
- `Settings` gets a `license_key: str` field (empty string = no license)
- `get_settings()` continues to work as before

**`termmon/main.py`** (existing, modified)
- App startup calls `verify_license(settings.license_key)` and stores result in app state
- If license is None → all routes except `/health` and `/setup` return 403 with `{"error": "license_required"}`
- `/api/config` response includes `tier: "base" | "mid" | "diamond" | "none"`

### Route Guards

| Route | Minimum tier |
|---|---|
| `/api/chat` | MID |
| `/ws/terminal` | MID |
| `/api/brain/*` | DIAMOND |
| `/api/plugins` | DIAMOND |
| `/api/model/train` | DIAMOND |
| All other `/api/*` routes | BASE (any valid license) |

Guards are implemented as FastAPI dependencies using `requires_tier(Tier.MID)` etc., not as middleware, so they're explicit per route.

### No-License Flow

When `settings.license_key` is empty or the signature is invalid:

1. App starts normally (health endpoint stays up for Docker healthcheck)
2. All API routes return `403 {"error": "license_required", "detail": "A valid license key is required"}`
3. Frontend detects 403 on `/api/config` and redirects to `/setup` with a license entry banner
4. Setup wizard shows a "License Key" field prominently (always visible, not optional)
5. On save, if the key is invalid, the wizard shows an inline error: "Invalid license key"

### Frontend Gating

The frontend reads `tier` from `/api/config` and conditionally renders tabs:
- Base: Dashboard tab only
- Mid: + AI Chat tab, Terminal tab
- Diamond: + Brain tab, Plugins tab, Model tab

Backend guards are the real enforcement; frontend hiding is UX polish only.

---

## Setup Wizard Integration

The `license_key` field is added to the setup wizard form. It is:
- Always visible (not collapsed or optional)
- Labeled: **License Key** with a placeholder: `eyJ...`
- Validated on the backend when the form is submitted (`/api/setup`)
- On invalid key: wizard returns a field-level error, not a full page error

The wizard displays the resolved tier name ("Base", "Mid", "Diamond") in green after a successful save, so the buyer gets confirmation on the redirected dashboard page.

---

## Key Generation Workflow (Developer)

```bash
# One-time setup: generate keypair
python termmon-keygen.py --generate-keypair
# → writes ~/.termmon/private_key.pem and public_key.pem
# → prints public key to embed in termmon/licensing.py

# Issue a license key
python termmon-keygen.py --tier mid --email buyer@example.com
# → prints JWT string to stdout, copy-paste to buyer
```

The public key printed by `--generate-keypair` is pasted as the `PUBLIC_KEY` constant in `termmon/licensing.py` before the first release.

---

## Files Created / Modified

| File | Action | Purpose |
|---|---|---|
| `termmon-keygen.py` | Create | Developer key issuance tool |
| `termmon/licensing.py` | Create | JWT verification, Tier enum, route dependency |
| `termmon/config.py` | Modify | Add `license_key: str = ""` to Settings |
| `termmon/main.py` | Modify | Startup license check, 403 flow, pass tier to `/api/config` |
| `termmon/setup.html` | Modify | Add license key field + tier confirmation display |
| `tests/test_licensing.py` | Create | Unit tests for verify_license, tier ordering, route guards |

---

## Security Notes

- Private key is never committed to any repository (add `*.pem` and `~/.termmon/` to `.gitignore`)
- `termmon-keygen.py` is added to `.dockerignore` — it must never ship inside a buyer's Docker image
- Public key is embedded in source — this is intentional and safe (can verify, not forge)
- A compromised or leaked key can only be invalidated by rotating the keypair and shipping an app update with the new public key embedded
- Keys contain email for traceability; buyers are informed their email is encoded in their key
- `sub: "terminal-monitor"` claim prevents accidental key reuse if future products use the same keygen tool

---

## Out of Scope (this spec)

- Automated purchase → key delivery pipeline (manual for now)
- Key revocation without a public key rotation
- Multi-seat / team licenses
- License expiry / subscription mode
- Pricing amounts (business decision, not implementation)
