from __future__ import annotations

import os

import anthropic

CLAUDE_MODEL = "claude-haiku-4-5-20251001"


async def generate(message: str, system: str) -> dict:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return {"reply": None, "available": False}
    try:
        client = anthropic.AsyncAnthropic(api_key=api_key)
        msg = await client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=300,
            system=system,
            messages=[{"role": "user", "content": message}],
        )
        return {"reply": msg.content[0].text, "available": True}
    except Exception:
        return {"reply": None, "available": False}
