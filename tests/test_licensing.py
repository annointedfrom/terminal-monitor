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
