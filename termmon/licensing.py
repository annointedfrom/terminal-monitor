from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum

import jwt

try:
    from fastapi import Depends, HTTPException, Request
except ImportError:  # FastAPI not installed in all environments
    Depends = None  # type: ignore[assignment]
    HTTPException = None  # type: ignore[assignment]
    Request = None  # type: ignore[assignment]

PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAzxyJfSH4uAzS3cD9BflH
J5frjtkIAUtlXCdqiySVPEXQFwq6nlMLVE4I5eLdXF6249p9EpkMmq6ME2bS5mKD
V6+JHAAtBBZLmH7Q2w35s/Jwb/vVqroumQ7hLnzy7fNh84iyyXl7Asf6GpfO/AFo
ALt2VsefunbIfVALlpBdShiWg0t3YEnefQ/CJkxj6l02XZlmj70Vo4ehWuWO+cer
AHh08pg0dowbS97/fJ70g5sLRae20ezUesiVH6FF/X8pLv73RXUt0MmOdPGvaEer
VMs/l4SyGbIuuQHiPKkuuL8rZ7SXk5VkARrn0b2u+i5GSuhuKLjvy3HYCFpo+V+N
VwIDAQAB
-----END PUBLIC KEY-----
"""


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


def verify_plugin_key(token: str, plugin_name: str) -> bool:
    if not token or not plugin_name or not PUBLIC_KEY:
        return False
    try:
        payload = jwt.decode(
            token,
            PUBLIC_KEY,
            algorithms=["RS256"],
        )
        return payload.get("sub") == f"termmon-plugin-{plugin_name}"
    except Exception:
        return False


def require_tier(minimum: Tier):
    if Depends is None or HTTPException is None:
        raise RuntimeError("require_tier() requires FastAPI; install fastapi to use it")

    async def _check(request: Request) -> LicenseInfo:  # type: ignore[valid-type] — Request is None only without FastAPI; this path is never reached in that context
        info: LicenseInfo | None = getattr(request.app.state, "license", None)
        if info is None or info.tier < minimum:
            raise HTTPException(
                status_code=403,
                detail={"error": "insufficient_tier", "required": minimum.name.lower()},
            )
        return info

    return Depends(_check)
