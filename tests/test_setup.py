# tests/test_setup.py
import pathlib
import yaml
from unittest.mock import patch


def test_build_config_structure():
    import setup as setup_mod
    cfg = setup_mod._build_config(
        title="Test Ops", default_model="llama3.2:3b", training_threshold=50,
        brain_enabled=False, brain_url="http://localhost:8000",
        services=[{"name": "my-agent", "port": 8090}],
        cpu_threshold=70, ram_threshold=75, gpu_temp_threshold=85, offline_notify=True,
    )
    assert cfg["dashboard"]["title"] == "Test Ops"
    assert cfg["brain"]["enabled"] is False
    assert cfg["services"][0]["port"] == 8090
    assert cfg["alerts"]["cpu_threshold"] == 70


def test_write_config_writes_yaml(tmp_path):
    import setup as setup_mod
    out = tmp_path / "config.yaml"
    cfg = setup_mod._build_config(
        title="X", default_model="m", training_threshold=100,
        brain_enabled=False, brain_url="http://localhost:8000",
        services=[], cpu_threshold=80, ram_threshold=80, gpu_temp_threshold=80, offline_notify=True,
    )
    setup_mod._write_config(cfg, out)
    loaded = yaml.safe_load(out.read_text())
    assert loaded["dashboard"]["title"] == "X"


def test_write_config_overwrites_existing(tmp_path):
    import setup as setup_mod
    out = tmp_path / "config.yaml"
    out.write_text("old: data\n")
    cfg = setup_mod._build_config(
        title="New", default_model="m", training_threshold=100,
        brain_enabled=False, brain_url="http://localhost:8000",
        services=[], cpu_threshold=80, ram_threshold=80, gpu_temp_threshold=80, offline_notify=True,
    )
    setup_mod._write_config(cfg, out)
    loaded = yaml.safe_load(out.read_text())
    assert "old" not in loaded
    assert loaded["dashboard"]["title"] == "New"


def test_setup_post_updates_app_state_license(tmp_path, monkeypatch):
    import yaml
    import termmon.config as cfg_mod
    import termmon.licensing as lic_mod
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization
    import jwt as pyjwt
    from fastapi.testclient import TestClient
    from termmon.main import app

    # Generate test keypair
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = private_key.public_key().public_bytes(
        serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo
    ).decode()
    monkeypatch.setattr(lic_mod, "PUBLIC_KEY", public_pem)

    token = pyjwt.encode(
        {"tier": "mid", "email": "t@t.com", "issued_at": "2026-05-20", "sub": "terminal-monitor"},
        private_pem, algorithm="RS256"
    )

    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text("", encoding="utf-8")
    cfg_mod._settings = None
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_path)

    with TestClient(app) as client:
        r = client.post("/api/setup", json={"license_key": token})
        assert r.status_code == 200
        assert r.json()["saved"] is True
        assert app.state.license is not None
        assert app.state.license.tier.name == "MID"

    cfg_mod._settings = None
