from __future__ import annotations

import asyncio

import httpx


async def _ping(client: httpx.AsyncClient, port: int) -> bool:
    try:
        r = await client.get(f"http://localhost:{port}/health", timeout=1.5)
        if r.status_code != 404:
            return r.status_code < 500
        r2 = await client.get(f"http://localhost:{port}/", timeout=1.5)
        return r2.status_code < 500
    except Exception:
        return False


async def check_health(ports: list[dict]) -> list[dict]:
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*[_ping(client, p["port"]) for p in ports])
    return [{**p, "healthy": healthy} for p, healthy in zip(ports, results)]
