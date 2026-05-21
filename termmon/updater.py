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
    from termmon.scanner.ollama import _ollama_url  # deferred to avoid circular import
    async with httpx.AsyncClient() as client:
        r = await client.post(
            f"{_ollama_url()}/api/pull",
            json={"name": tag, "stream": False},
            timeout=120.0,
        )
        r.raise_for_status()
