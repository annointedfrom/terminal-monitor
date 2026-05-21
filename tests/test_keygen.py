import importlib.util
import pathlib
import jwt as pyjwt


def _load_keygen():
    spec = importlib.util.spec_from_file_location(
        "termmon_keygen",
        pathlib.Path(__file__).parent.parent / "termmon-keygen.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_generate_keypair_creates_pem_files(tmp_path):
    kg = _load_keygen()
    public_pem = kg.generate_keypair(tmp_path)
    assert (tmp_path / "private_key.pem").exists()
    assert (tmp_path / "public_key.pem").exists()
    assert "BEGIN PUBLIC KEY" in public_pem


def test_issue_key_produces_valid_jwt(tmp_path):
    kg = _load_keygen()
    public_pem = kg.generate_keypair(tmp_path)
    token = kg.issue_key("mid", "buyer@example.com", tmp_path / "private_key.pem")
    payload = pyjwt.decode(token, public_pem, algorithms=["RS256"], options={"verify_exp": False})
    assert payload["tier"] == "mid"
    assert payload["email"] == "buyer@example.com"
    assert payload["sub"] == "terminal-monitor"
    assert "issued_at" in payload


def test_issue_key_all_tiers(tmp_path):
    kg = _load_keygen()
    public_pem = kg.generate_keypair(tmp_path)
    for tier in ("base", "mid", "diamond"):
        token = kg.issue_key(tier, f"{tier}@test.com", tmp_path / "private_key.pem")
        payload = pyjwt.decode(token, public_pem, algorithms=["RS256"], options={"verify_exp": False})
        assert payload["tier"] == tier


def test_generate_keypair_does_not_overwrite_existing(tmp_path):
    kg = _load_keygen()
    kg.generate_keypair(tmp_path)
    original_mtime = (tmp_path / "private_key.pem").stat().st_mtime
    kg.generate_keypair(tmp_path)  # second call should not overwrite
    assert (tmp_path / "private_key.pem").stat().st_mtime == original_mtime
