from __future__ import annotations

import os

import httpx

DEFAULT_MODEL = "llama3.2:3b"


def _ollama_url() -> str:
    return os.environ.get("OLLAMA_URL", "http://localhost:11434")


async def generate(message: str, system: str, model: str = DEFAULT_MODEL) -> dict:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{_ollama_url()}/api/generate",
                json={"model": model, "system": system, "prompt": message, "stream": False},
                timeout=30.0,
            )
            r.raise_for_status()
            return {"reply": r.json()["response"], "available": True}
    except Exception:
        return {"reply": None, "available": False}


async def list_models() -> list[str]:
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{_ollama_url()}/api/tags", timeout=5.0)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []
