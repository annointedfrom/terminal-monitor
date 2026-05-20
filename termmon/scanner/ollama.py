from __future__ import annotations

import httpx

OLLAMA_URL = "http://localhost:11434"
DEFAULT_MODEL = "llama3.2:3b"


async def generate(message: str, system: str, model: str = DEFAULT_MODEL) -> dict:
    """Call Ollama /api/generate (non-streaming).

    Returns {"reply": str, "available": True} on success or
    {"reply": None, "available": False} if Ollama is unreachable or the
    model is missing.
    """
    try:
        async with httpx.AsyncClient() as client:
            r = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={"model": model, "system": system, "prompt": message, "stream": False},
                timeout=30.0,
            )
            r.raise_for_status()
            return {"reply": r.json()["response"], "available": True}
    except Exception:
        return {"reply": None, "available": False}


async def list_models() -> list[str]:
    """Return names of models available locally in Ollama."""
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(f"{OLLAMA_URL}/api/tags", timeout=5.0)
            r.raise_for_status()
            return [m["name"] for m in r.json().get("models", [])]
    except Exception:
        return []
