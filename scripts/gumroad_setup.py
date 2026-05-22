"""
Create Terminal Monitor Gumroad listings via API.
Usage: set GUMROAD_ACCESS_TOKEN env var, then run this script.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from urllib.parse import quote

import httpx as requests

API_BASE = "https://api.gumroad.com/v2"
ZIP_PATH = Path(__file__).parent.parent.parent / "terminal-monitor-v2.0.0.zip"

PRODUCTS = [
    {
        "name": "Terminal Monitor — Base",
        "price": 0,
        "description": (
            "A real-time ops dashboard for AI developers. Monitor ports, processes, "
            "MCP servers, CPU/RAM/GPU, and shell history from a single terminal-resident UI.\n\n"
            "Base tier includes:\n"
            "• Port scanner with health checks\n"
            "• Process monitor with kill controls\n"
            "• MCP server detection\n"
            "• Resource graphs (CPU, RAM, GPU)\n"
            "• Shell history viewer\n"
            "• Auto-refresh every 10s\n"
            "• Docker-ready\n\n"
            "Runs locally on port 8084. No cloud, no telemetry.\n\n"
            "See all tiers at https://portfolio-indol-nine-54.vercel.app/ai"
        ),
    },
    {
        "name": "Terminal Monitor — Mid",
        "price": 2900,
        "description": (
            "Everything in Base, plus:\n"
            "• Custom memory server — store notes, commands, and snapshots in SQLite\n"
            "• MEMORY tab — browse, search, and delete entries from the dashboard\n"
            "• Plugin architecture — load custom scan/router plugins with RS256 keys\n"
            "• Shell history auto-import into memory on startup\n"
            "• In-dashboard update notifications\n\n"
            "A license key will be delivered via email within 24 hours of purchase.\n\n"
            "See all tiers at https://portfolio-indol-nine-54.vercel.app/ai"
        ),
    },
    {
        "name": "Terminal Monitor — Diamond",
        "price": 7900,
        "description": (
            "Everything in Mid, plus:\n"
            "• NeuroLinked brain sync — memory entries auto-pushed to your local AI brain every 60s\n"
            "• Memory insights endpoint\n"
            "• Priority support\n\n"
            "A Diamond license key will be delivered via email within 24 hours of purchase.\n\n"
            "See all tiers at https://portfolio-indol-nine-54.vercel.app/ai"
        ),
    },
]


def headers() -> dict:
    token = os.environ.get("GUMROAD_ACCESS_TOKEN", "")
    if not token:
        print("ERROR: set GUMROAD_ACCESS_TOKEN environment variable")
        sys.exit(1)
    return {"Authorization": f"Bearer {token}"}


def create_product(product: dict) -> str:
    r = requests.post(
        f"{API_BASE}/products",
        headers=headers(),
        data={
            "name": product["name"],
            "price": product["price"],
            "description": product["description"],
            "published": False,
        },
    )
    r.raise_for_status()
    data = r.json()
    product_id = data["product"]["id"]
    print(f"  Created: {product['name']} (id={product_id})")
    return product_id


def upload_file(product_id: str) -> None:
    if not ZIP_PATH.exists():
        print(f"  WARNING: zip not found at {ZIP_PATH}, skipping file upload")
        return
    encoded_id = quote(product_id, safe="")
    with ZIP_PATH.open("rb") as f:
        r = requests.post(
            f"{API_BASE}/products/{encoded_id}/product_files",
            headers=headers(),
            files={"file": (ZIP_PATH.name, f, "application/zip")},
        )
    r.raise_for_status()
    print(f"  Uploaded: {ZIP_PATH.name}")


def list_existing() -> dict[str, str]:
    r = requests.get(f"{API_BASE}/products", headers=headers())
    r.raise_for_status()
    return {p["name"]: p["id"] for p in r.json().get("products", [])}


def main() -> None:
    print(f"Using zip: {ZIP_PATH}")
    print(f"Zip exists: {ZIP_PATH.exists()}\n")

    existing = list_existing()
    print(f"Existing products: {list(existing.keys()) or 'none'}\n")

    for product in PRODUCTS:
        if product["name"] in existing:
            product_id = existing[product["name"]]
            print(f"Already exists: {product['name']} (id={product_id}) — uploading file only")
        else:
            print(f"Creating: {product['name']} (${product['price'] // 100})")
            product_id = create_product(product)
        print()

    print("Done. Go to gumroad.com/products to review and publish each listing.")


if __name__ == "__main__":
    main()
