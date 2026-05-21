from termmon.version import __version__


def test_version_is_string():
    assert isinstance(__version__, str)
    parts = __version__.split(".")
    assert len(parts) == 3
    assert all(p.isdigit() for p in parts)


import httpx
import respx
from termmon.updater import _version_gt, _tier_available, check_updates
from termmon.licensing import LicenseInfo, Tier

# ── Version comparison ────────────────────────────────────────────────────────

def test_version_gt_newer():
    assert _version_gt("1.1.0", "1.0.0") is True


def test_version_gt_equal():
    assert _version_gt("1.0.0", "1.0.0") is False


def test_version_gt_older():
    assert _version_gt("1.0.0", "1.1.0") is False


def test_version_gt_malformed():
    assert _version_gt("bad", "1.0.0") is False


# ── Tier filter ───────────────────────────────────────────────────────────────

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


# ── Manifest fetching (respx mocks) ──────────────────────────────────────────

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
    assert result["app"]["current"] == __version__
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


# ── ollama_pull tests ─────────────────────────────────────────────────────────

async def test_ollama_pull_success():
    import os
    pull_url = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/pull"
    with respx.mock:
        respx.post(pull_url).mock(return_value=httpx.Response(200, json={"status": "success"}))
        from termmon.updater import ollama_pull
        await ollama_pull("ops-brain:v2")  # should not raise


async def test_ollama_pull_failure_raises():
    import os
    pull_url = os.environ.get("OLLAMA_URL", "http://localhost:11434") + "/api/pull"
    with respx.mock:
        respx.post(pull_url).mock(return_value=httpx.Response(503, json={"error": "unavailable"}))
        from termmon.updater import ollama_pull
        import pytest
        with pytest.raises(Exception):
            await ollama_pull("ops-brain:v2")
