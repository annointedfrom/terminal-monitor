from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import jwt

try:
    from fastapi import Depends, HTTPException, Request as _FastAPIRequest
except ImportError:  # FastAPI not installed in all environments
    Depends = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    _FastAPIRequest = None  # type: ignore[assignment]

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
        raw_tier = payload.get("tier")
        if not raw_tier:
            return None
        try:
            tier = Tier[raw_tier.upper()]
        except KeyError:
            return None
        return LicenseInfo(
            tier=tier,
            email=payload.get("email", ""),
            issued_at=payload.get("issued_at", ""),
        )
    except Exception:
        return None


def require_tier(minimum: Tier):
    async def _check(request: _FastAPIRequest) -> LicenseInfo:  # type: ignore[valid-type]
        info: LicenseInfo | None = getattr(request.app.state, "license", None)
        if info is None or info.tier < minimum:
            raise HTTPException(
                status_code=403,
                detail={"error": "insufficient_tier", "required": minimum.name.lower()},
            )
        return info

    return Depends(_check)
