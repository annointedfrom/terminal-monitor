#!/usr/bin/env python3
"""Developer tool for issuing Terminal Monitor license keys. Never ships to buyers."""
from __future__ import annotations

import argparse
import pathlib
import sys
from datetime import date, datetime, timezone

import jwt


def generate_keypair(key_dir: pathlib.Path) -> str:
    """Generate a 2048-bit RSA keypair in key_dir. Returns public key PEM. No-ops if key exists."""
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives import serialization

    private_path = key_dir / "private_key.pem"
    public_path = key_dir / "public_key.pem"

    if private_path.exists():
        print(f"[skip] {private_path} already exists — not overwriting.", file=sys.stderr)
        return public_path.read_text()

    key_dir.mkdir(parents=True, exist_ok=True)
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    public_pem = private_key.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    private_path.write_bytes(private_pem)
    public_path.write_bytes(public_pem)
    print(f"[ok] Keypair written to {key_dir}", file=sys.stderr)
    return public_pem.decode()


def issue_key(tier: str, email: str, private_key_path: pathlib.Path) -> str:
    """Sign a JWT license key for the given tier and email."""
    private_pem = private_key_path.read_text()
    return jwt.encode(
        {
            "tier": tier,
            "email": email,
            "issued_at": date.today().isoformat(),
            "sub": "terminal-monitor",
            "exp": datetime(2099, 1, 1, tzinfo=timezone.utc),
        },
        private_pem,
        algorithm="RS256",
    )


def issue_plugin_key(plugin_name: str, email: str, private_key_path: pathlib.Path) -> str:
    """Sign a JWT plugin key for the given plugin name and email. No tier field."""
    private_pem = private_key_path.read_text()
    return jwt.encode(
        {
            "sub": f"termmon-plugin-{plugin_name}",
            "email": email,
            "issued_at": date.today().isoformat(),
            "exp": datetime(2099, 1, 1, tzinfo=timezone.utc),
        },
        private_pem,
        algorithm="RS256",
    )


def _default_key_dir() -> pathlib.Path:
    return pathlib.Path.home() / ".termmon"


def main() -> None:
    parser = argparse.ArgumentParser(description="Terminal Monitor license key tool")
    parser.add_argument("--generate-keypair", action="store_true", help="Generate RSA keypair")
    parser.add_argument("--tier", choices=["base", "mid", "diamond"], help="License tier")
    parser.add_argument("--email", help="Buyer email to encode in the key")
    parser.add_argument("--plugin", help="Plugin name to issue a plugin key for (ignores --tier)")
    parser.add_argument("--key-dir", type=pathlib.Path, default=_default_key_dir(),
                        help="Directory for keypair files (default: ~/.termmon)")
    args = parser.parse_args()

    if args.generate_keypair:
        public_pem = generate_keypair(args.key_dir)
        print("\nEmbed this PUBLIC_KEY in termmon/licensing.py:\n")
        print(public_pem)
        return

    if args.plugin and args.email:
        private_key_path = args.key_dir / "private_key.pem"
        if not private_key_path.exists():
            print(f"[error] Private key not found at {private_key_path}", file=sys.stderr)
            print("Run: python termmon-keygen.py --generate-keypair", file=sys.stderr)
            sys.exit(1)
        token = issue_plugin_key(args.plugin, args.email, private_key_path)
        print(token)
        return

    if args.tier and args.email:
        private_key_path = args.key_dir / "private_key.pem"
        if not private_key_path.exists():
            print(f"[error] Private key not found at {private_key_path}", file=sys.stderr)
            print("Run: python termmon-keygen.py --generate-keypair", file=sys.stderr)
            sys.exit(1)
        token = issue_key(args.tier, args.email, private_key_path)
        print(token)
        return

    parser.print_help()


if __name__ == "__main__":
    main()
