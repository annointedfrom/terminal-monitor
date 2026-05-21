import pytest
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from unittest.mock import patch
import termmon.licensing as lic_mod
from termmon.licensing import Tier, LicenseInfo, verify_license


@pytest.fixture
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    return private_pem, public_pem


def _make_token(private_pem: str, tier: str, email: str = "buyer@example.com", sub: str = "terminal-monitor") -> str:
    return pyjwt.encode(
        {"tier": tier, "email": email, "issued_at": "2026-05-20", "sub": sub},
        private_pem,
        algorithm="RS256",
    )


def test_verify_license_empty_returns_none():
    assert verify_license("") is None


def test_verify_license_garbage_returns_none():
    assert verify_license("not.a.jwt") is None


def test_verify_license_base_tier(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = _make_token(private_pem, "base")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = verify_license(token)
    assert result is not None
    assert result.tier == Tier.BASE
    assert result.email == "buyer@example.com"
    assert result.issued_at == "2026-05-20"


def test_verify_license_mid_tier(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = _make_token(private_pem, "mid")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = verify_license(token)
    assert result is not None
    assert result.tier == Tier.MID


def test_verify_license_diamond_tier(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = _make_token(private_pem, "diamond")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = verify_license(token)
    assert result is not None
    assert result.tier == Tier.DIAMOND


def test_verify_license_invalid_tier_returns_none(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = _make_token(private_pem, "platinum")  # not a valid tier
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = verify_license(token)
    assert result is None


def test_verify_license_wrong_sub_returns_none(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = _make_token(private_pem, "mid", sub="other-product")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = verify_license(token)
    assert result is None


def test_verify_license_wrong_signature_returns_none(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    other_private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    other_public_pem = other_private.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    ).decode()
    token = _make_token(private_pem, "diamond")
    with patch.object(lic_mod, "PUBLIC_KEY", other_public_pem):
        result = verify_license(token)
    assert result is None


def test_tier_ordering():
    assert Tier.BASE < Tier.MID
    assert Tier.MID < Tier.DIAMOND
    assert Tier.BASE < Tier.DIAMOND


from fastapi import FastAPI
from fastapi.testclient import TestClient
from termmon.licensing import require_tier


def _make_test_app(license_info):
    test_app = FastAPI()
    test_app.state.license = license_info

    @test_app.get("/protected", dependencies=[require_tier(Tier.MID)])
    async def protected():
        return {"ok": True}

    @test_app.get("/diamond-only", dependencies=[require_tier(Tier.DIAMOND)])
    async def diamond_only():
        return {"ok": True}

    return test_app


def test_require_tier_blocks_when_no_license():
    app = _make_test_app(None)
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/protected")
    assert r.status_code == 403


def test_require_tier_blocks_base_for_mid_route():
    app = _make_test_app(LicenseInfo(tier=Tier.BASE, email="t@t.com", issued_at="2026-05-20"))
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/protected")
    assert r.status_code == 403


def test_require_tier_allows_mid_for_mid_route():
    app = _make_test_app(LicenseInfo(tier=Tier.MID, email="t@t.com", issued_at="2026-05-20"))
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/protected")
    assert r.status_code == 200


def test_require_tier_blocks_mid_for_diamond_route():
    app = _make_test_app(LicenseInfo(tier=Tier.MID, email="t@t.com", issued_at="2026-05-20"))
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/diamond-only")
    assert r.status_code == 403


def test_require_tier_allows_diamond_for_diamond_route():
    app = _make_test_app(LicenseInfo(tier=Tier.DIAMOND, email="t@t.com", issued_at="2026-05-20"))
    client = TestClient(app, raise_server_exceptions=False)
    r = client.get("/diamond-only")
    assert r.status_code == 200


import yaml
from termmon.main import app


@pytest.fixture
def no_license_client(rsa_keypair, tmp_path, monkeypatch):
    import termmon.config as cfg_mod
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("", encoding="utf-8")
    cfg_mod._settings = None
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_path)
    with TestClient(app) as client:
        yield client
    cfg_mod._settings = None


@pytest.fixture
def base_license_client(rsa_keypair, tmp_path, monkeypatch):
    import termmon.config as cfg_mod
    private_pem, public_pem = rsa_keypair
    monkeypatch.setattr(lic_mod, "PUBLIC_KEY", public_pem)
    token = _make_token(private_pem, "base")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump({"license_key": token}), encoding="utf-8")
    cfg_mod._settings = None
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_path)
    with TestClient(app) as client:
        yield client
    cfg_mod._settings = None


def test_health_always_accessible(no_license_client):
    r = no_license_client.get("/health")
    assert r.status_code == 200


def test_setup_page_accessible_without_license(no_license_client):
    r = no_license_client.get("/setup")
    assert r.status_code == 200


def test_api_scan_blocked_without_license(no_license_client):
    r = no_license_client.get("/api/scan")
    assert r.status_code == 403
    assert r.json()["error"] == "license_required"


def test_api_scan_accessible_with_base_license(base_license_client):
    r = base_license_client.get("/api/scan")
    assert r.status_code == 200


def test_api_config_returns_tier_field(base_license_client):
    r = base_license_client.get("/api/config")
    assert r.status_code == 200
    assert r.json()["tier"] == "base"


def test_api_config_blocked_without_license(no_license_client):
    r = no_license_client.get("/api/config")
    assert r.status_code == 403


@pytest.fixture
def mid_license_client(rsa_keypair, tmp_path, monkeypatch):
    import termmon.config as cfg_mod
    private_pem, public_pem = rsa_keypair
    monkeypatch.setattr(lic_mod, "PUBLIC_KEY", public_pem)
    token = _make_token(private_pem, "mid")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump({"license_key": token}), encoding="utf-8")
    cfg_mod._settings = None
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_path)
    with TestClient(app) as client:
        yield client
    cfg_mod._settings = None


@pytest.fixture
def diamond_license_client(rsa_keypair, tmp_path, monkeypatch):
    import termmon.config as cfg_mod
    private_pem, public_pem = rsa_keypair
    monkeypatch.setattr(lic_mod, "PUBLIC_KEY", public_pem)
    token = _make_token(private_pem, "diamond")
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.dump({"license_key": token}), encoding="utf-8")
    cfg_mod._settings = None
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_path)
    with TestClient(app) as client:
        yield client
    cfg_mod._settings = None


def test_chat_blocked_for_base_license(base_license_client):
    r = base_license_client.post("/api/chat", json={"message": "hi", "model": "llama3.2:3b"})
    assert r.status_code == 403


def test_chat_allowed_for_mid_license(mid_license_client):
    # Mid license reaches the handler — may return 503 (no Ollama) but NOT 403
    r = mid_license_client.post("/api/chat", json={"message": "hi", "model": "llama3.2:3b"})
    assert r.status_code != 403


def test_brain_sync_blocked_for_mid_license(mid_license_client):
    r = mid_license_client.post("/api/brain/sync")
    assert r.status_code == 403


def test_brain_sync_allowed_for_diamond_license(diamond_license_client):
    # Diamond license reaches the handler — may return any non-403 status
    r = diamond_license_client.post("/api/brain/sync")
    assert r.status_code != 403


def test_terminal_ws_blocked_for_base_license(base_license_client):
    import pytest
    from starlette.websockets import WebSocketDisconnect
    with pytest.raises(WebSocketDisconnect):
        with base_license_client.websocket_connect("/ws/terminal") as ws:
            pass


def test_terminal_ws_allowed_for_mid_license(mid_license_client):
    from starlette.websockets import WebSocketDisconnect
    try:
        with mid_license_client.websocket_connect("/ws/terminal") as ws:
            ws.send_text("echo hello")
            data = ws.receive_text()
            assert "hello" in data or "[exit" in data
    except WebSocketDisconnect:
        pytest.fail("MID license should be allowed to connect to /ws/terminal")


# ── Update server endpoint tests ──────────────────────────────────────────────

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
    # Ollama not running in CI — expects 503 (no Ollama), NOT 403 (license block)
    r = mid_license_client.post("/api/update/model/pull", json={"tag": "ops-brain:v2"})
    assert r.status_code != 403


def test_verify_plugin_key_valid(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = pyjwt.encode(
        {"sub": "termmon-plugin-docker", "email": "buyer@test.com", "issued_at": "2026-05-21"},
        private_pem,
        algorithm="RS256",
    )
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert lic_mod.verify_plugin_key(token, "docker") is True


def test_verify_plugin_key_wrong_plugin_name(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = pyjwt.encode(
        {"sub": "termmon-plugin-docker", "email": "buyer@test.com", "issued_at": "2026-05-21"},
        private_pem,
        algorithm="RS256",
    )
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert lic_mod.verify_plugin_key(token, "redis") is False


def test_verify_plugin_key_garbage_returns_false():
    assert lic_mod.verify_plugin_key("not.a.jwt", "docker") is False


def test_verify_plugin_key_empty_returns_false():
    assert lic_mod.verify_plugin_key("", "docker") is False


def test_verify_plugin_key_main_license_token_rejected(rsa_keypair):
    """A main app license key must NOT pass as a plugin key."""
    private_pem, public_pem = rsa_keypair
    token = pyjwt.encode(
        {"sub": "terminal-monitor", "tier": "mid", "email": "b@t.com", "issued_at": "2026-05-21"},
        private_pem,
        algorithm="RS256",
    )
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert lic_mod.verify_plugin_key(token, "docker") is False


def test_verify_plugin_key_empty_plugin_name_returns_false(rsa_keypair):
    private_pem, public_pem = rsa_keypair
    token = pyjwt.encode(
        {"sub": "termmon-plugin-", "email": "buyer@test.com", "issued_at": "2026-05-21"},
        private_pem,
        algorithm="RS256",
    )
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert lic_mod.verify_plugin_key(token, "") is False
