import json
import pytest
import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from pathlib import Path
from unittest.mock import patch

import termmon.licensing as lic_mod


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


def _make_plugin_token(private_pem: str, plugin_name: str) -> str:
    return pyjwt.encode(
        {"sub": f"termmon-plugin-{plugin_name}", "email": "buyer@test.com", "issued_at": "2026-05-21"},
        private_pem,
        algorithm="RS256",
    )


def _write_plugin(
    plugin_dir: Path,
    *,
    private_pem: str,
    name: str,
    has_manifest: bool = True,
    has_init: bool = True,
    has_key: bool = True,
    scan_body: str = "def scan():\n    return {'ok': True}\n",
    has_tab: bool = False,
    key_sub_name: str | None = None,
) -> None:
    """Write a minimal plugin folder. key_sub_name overrides the sub claim for mismatch tests."""
    plugin_dir.mkdir(parents=True, exist_ok=True)
    if has_manifest:
        (plugin_dir / "manifest.json").write_text(json.dumps({
            "name": name, "label": name.title(), "version": "1.0.0",
            "description": "Test plugin", "min_tier": "base",
            "has_tab": has_tab, "author": "test",
        }))
    if has_init:
        (plugin_dir / "__init__.py").write_text(scan_body)
    if has_key:
        sub_name = key_sub_name if key_sub_name is not None else name
        token = _make_plugin_token(private_pem, sub_name)
        (plugin_dir / "plugin.key").write_text(token)
    if has_tab:
        (plugin_dir / "tab.html").write_text("<div>Hello from plugin</div>")


# ─── Loader discovery tests ────────────────────────────────────────────────────

def test_load_plugins_returns_empty_when_dir_missing(tmp_path):
    from termmon.plugin_loader import load_plugins
    result = load_plugins(tmp_path / "no-such-dir")
    assert result == []


def test_load_plugins_skips_missing_manifest(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    d.mkdir()
    (d / "__init__.py").write_text("def scan(): return {}")
    (d / "plugin.key").write_text(_make_plugin_token(private_pem, "myplugin"))
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_skips_missing_key(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin", has_key=False)
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_skips_invalid_jwt(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin")
    (d / "plugin.key").write_text("not.a.valid.jwt")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_skips_wrong_sub(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin", key_sub_name="otherplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_skips_missing_scan(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin", scan_body="x = 1\n")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_skips_bad_import(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin",
                  scan_body="def scan(\n    return {}\n")  # syntax error
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        assert load_plugins(tmp_path) == []


def test_load_plugins_loads_valid_plugin(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        result = load_plugins(tmp_path)
    assert len(result) == 1
    assert result[0].meta.name == "myplugin"


# ─── LoadedPlugin method tests ────────────────────────────────────────────────

def test_loaded_plugin_scan_returns_data(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    assert plugins[0].scan() == {"ok": True}


def test_loaded_plugin_tab_html_returns_content(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin", has_tab=True)
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    assert plugins[0].tab_html() == "<div>Hello from plugin</div>"


def test_loaded_plugin_tab_html_none_when_file_missing(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    assert plugins[0].tab_html() is None


def test_loaded_plugin_has_router_false_without_router(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(d, private_pem=private_pem, name="myplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    assert plugins[0].has_router() is False


def test_loaded_plugin_has_router_true_with_router(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "myplugin"
    _write_plugin(
        d, private_pem=private_pem, name="myplugin",
        scan_body=(
            "def scan():\n    return {}\n"
            "def router():\n    from fastapi import APIRouter\n    return APIRouter()\n"
        ),
    )
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    assert plugins[0].has_router() is True


# ─── _resolve_plugins_dir tests ───────────────────────────────────────────────

def test_resolve_plugins_dir_default():
    from termmon.plugin_loader import _resolve_plugins_dir
    import termmon.plugin_loader as _pl
    expected = Path(_pl.__file__).parent.parent / "plugins"
    assert _resolve_plugins_dir(None) == expected


def test_resolve_plugins_dir_custom(tmp_path):
    from termmon.plugin_loader import _resolve_plugins_dir
    assert _resolve_plugins_dir(str(tmp_path)) == tmp_path


# ─── API endpoint tests ────────────────────────────────────────────────────────
# These tests use a minimal FastAPI app (not termmon.main.app) to avoid
# polluting the main app's route table across test runs.

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _endpoint_client(plugin) -> TestClient:
    """Minimal app with plugin routes registered via _register_plugin_endpoints."""
    from termmon.main import _register_plugin_endpoints
    from termmon.licensing import LicenseInfo, Tier

    mini = FastAPI()
    mini.state.license = LicenseInfo(tier=Tier.BASE, email="t@test.com", issued_at="2026-05-21")
    mini.state.plugins = [plugin]
    _register_plugin_endpoints(mini, plugin)

    @mini.get("/api/plugins")
    async def _list():
        return [
            {
                "name": p.meta.name,
                "label": p.meta.label,
                "version": p.meta.version,
                "description": p.meta.description,
                "has_tab": p.meta.has_tab,
            }
            for p in mini.state.plugins
        ]

    return TestClient(mini)


def test_get_plugins_returns_metadata(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "endplugin"
    _write_plugin(d, private_pem=private_pem, name="endplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    client = _endpoint_client(plugins[0])
    r = client.get("/api/plugins")
    assert r.status_code == 200
    body = r.json()
    assert body[0]["name"] == "endplugin"
    assert "label" in body[0]
    assert "has_tab" in body[0]


def test_plugin_data_returns_scan_result(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "dataplugin"
    _write_plugin(d, private_pem=private_pem, name="dataplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    client = _endpoint_client(plugins[0])
    r = client.get("/api/plugins/dataplugin/data")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_plugin_data_returns_500_when_scan_raises(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "errplugin"
    _write_plugin(d, private_pem=private_pem, name="errplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    plugin = plugins[0]
    with patch.object(plugin.module, "scan", side_effect=RuntimeError("boom")):
        client = _endpoint_client(plugin)
        r = client.get("/api/plugins/errplugin/data")
    assert r.status_code == 500


def test_plugin_tab_returns_html(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "tabplugin"
    _write_plugin(d, private_pem=private_pem, name="tabplugin", has_tab=True)
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    client = _endpoint_client(plugins[0])
    r = client.get("/api/plugins/tabplugin/tab")
    assert r.status_code == 200
    assert "<div>" in r.text


def test_plugin_tab_returns_404_when_has_tab_false(tmp_path, rsa_keypair):
    from termmon.plugin_loader import load_plugins
    private_pem, public_pem = rsa_keypair
    d = tmp_path / "notabplugin"
    _write_plugin(d, private_pem=private_pem, name="notabplugin")
    with patch.object(lic_mod, "PUBLIC_KEY", public_pem):
        plugins = load_plugins(tmp_path)
    client = _endpoint_client(plugins[0])
    # No /tab route registered when has_tab=False → FastAPI returns 404
    r = client.get("/api/plugins/notabplugin/tab")
    assert r.status_code == 404
