from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pathlib

import psutil
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from termmon import brain
from termmon.scanner import ollama
from termmon.scanner import claude_ai
from termmon.scanner.health import check_health
from termmon.scanner.mcp import scan_mcp
from termmon.scanner.ports import scan_ports
from termmon.scanner.processes import scan_background_processes
from termmon.scanner.resources import get_resources

logger = logging.getLogger(__name__)

_PROC_DESC_PATH = pathlib.Path(__file__).parent / "proc_desc.json"

def _load_proc_desc() -> dict[str, str]:
    raw = json.loads(_PROC_DESC_PATH.read_text(encoding="utf-8"))
    flat: dict[str, str] = {}
    for entries in raw.values():
        flat.update(entries)
    return flat

_PROC_DESC: dict[str, str] = _load_proc_desc()
_desc_cache: dict[str, str] = {}


async def _full_scan() -> dict:
    ports = scan_ports()
    ports = await check_health(ports)
    mcps = scan_mcp()
    mcp_count = sum(1 for m in mcps if m["running"])
    process_names = {p["process"] for p in ports if p["process"] != "unknown"}
    port_pids = {p["pid"] for p in ports if p["pid"]}
    background = scan_background_processes(exclude_pids=port_pids)
    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "ports": ports,
        "background_processes": background,
        "mcp_servers": mcps,
        "summary": {
            "port_count": len(ports),
            "mcp_count": mcp_count,
            "process_count": len(process_names),
        },
    }


async def _brain_loop() -> None:
    while True:
        await asyncio.sleep(60)
        try:
            result = await _full_scan()
            await brain.sync(result)
        except Exception as exc:
            logger.warning("Brain loop error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_brain_loop())
    yield
    task.cancel()


app = FastAPI(title="Terminal Monitor", lifespan=lifespan)


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/api/scan")
async def get_scan():
    return await _full_scan()


@app.get("/api/mcp")
async def get_mcp():
    return scan_mcp()


@app.get("/api/stats/port_count")
async def stats_port_count():
    return len(scan_ports())


@app.get("/api/stats/mcp_count")
async def stats_mcp_count():
    return sum(1 for m in scan_mcp() if m["running"])


@app.get("/api/stats/process_count")
async def stats_process_count():
    ports = scan_ports()
    return len({p["process"] for p in ports if p["process"] != "unknown"})


@app.get("/api/resources")
async def get_resources_endpoint():
    return get_resources()


@app.post("/api/brain/sync")
async def brain_sync():
    result = await _full_scan()
    await brain.sync(result)
    return {"synced": True, "summary": result["summary"]}


@app.post("/api/kill/{pid}")
async def kill_process(pid: int):
    try:
        proc = psutil.Process(pid)
        proc.terminate()
        await asyncio.sleep(0.5)
        if proc.is_running():
            proc.kill()
        return {"killed": True, "pid": pid}
    except psutil.NoSuchProcess:
        return JSONResponse(status_code=404, content={"detail": "Process not found"})
    except psutil.AccessDenied:
        return JSONResponse(status_code=403, content={"detail": "Access denied"})


@app.get("/api/process/descriptions")
async def process_descriptions():
    return _PROC_DESC


@app.get("/api/process/describe/{name}")
async def process_describe(name: str):
    if name in _PROC_DESC:
        return {"name": name, "description": _PROC_DESC[name], "source": "local"}
    if name in _desc_cache:
        return {"name": name, "description": _desc_cache[name], "source": "cache"}

    system = (
        "You are a Windows system expert. Describe the given process in 1-2 sentences: "
        "what software it belongs to, what it does, and whether it is safe. Be concise and factual."
    )
    prompt = f"What is the Windows process named '{name}'?"

    result = await ollama.generate(prompt, system)
    if not result["available"]:
        result = await claude_ai.generate(prompt, system)

    if result["available"] and result["reply"]:
        _desc_cache[name] = result["reply"]
        return {"name": name, "description": result["reply"], "source": "ai"}

    return {"name": name, "description": None, "source": "unknown"}


@app.get("/api/process/{pid}")
async def process_detail(pid: int):
    try:
        proc = psutil.Process(pid)
        with proc.oneshot():
            try:
                exe = proc.exe()
            except (psutil.AccessDenied, OSError):
                exe = None
            try:
                cmd = proc.cmdline()
            except (psutil.AccessDenied, OSError):
                cmd = []
            return {
                "pid": pid,
                "name": proc.name(),
                "exe": exe,
                "cmdline": cmd[:8],
                "username": proc.username(),
                "cpu_percent": proc.cpu_percent(interval=None),
                "status": proc.status(),
                "create_time": proc.create_time(),
            }
    except psutil.NoSuchProcess:
        return JSONResponse(status_code=404, content={"detail": "Process not found"})
    except psutil.AccessDenied:
        return JSONResponse(status_code=403, content={"detail": "Access denied"})


_TRAINING_PATH = pathlib.Path(__file__).parent.parent / "models" / "training_seed.jsonl"

_SANITIZE_PATTERNS = [
    (re.compile(r"C:\\Users\\[^\\]+", re.IGNORECASE), r"C:\\Users\\<user>"),
    (re.compile(r"/home/[^/\s]+"), "/home/<user>"),
    (re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"), "<email>"),
    (re.compile(r"\bsk-ant-[A-Za-z0-9\-]+"), "<api-key>"),
]


def _sanitize(text: str) -> str:
    for pattern, replacement in _SANITIZE_PATTERNS:
        text = pattern.sub(replacement, text)
    return text.strip()


class TrainingPair(BaseModel):
    question: str
    answer: str


class ChatRequest(BaseModel):
    message: str
    model: str = "ops-brain"


@app.post("/api/chat")
async def chat_with_ai(req: ChatRequest):
    scan = await _full_scan()
    ports_summary = [
        {"process": p["process"], "port": p["port"], "memory_mb": round(p.get("memory_mb", 0))}
        for p in scan["ports"][:20]
    ]
    system = (
        "You are an ops assistant monitoring the user's local machine. "
        "Answer questions about running processes, system health, and what actions to take. "
        "Be concise — 1-3 sentences unless more detail is explicitly requested. "
        f"Current system snapshot: active ports={scan['summary']['port_count']}, "
        f"unique processes={scan['summary']['process_count']}, "
        f"MCP servers running={scan['summary']['mcp_count']}. "
        f"Top processes: {json.dumps(ports_summary)}"
    )
    result = await ollama.generate(req.message, system, req.model)
    if result["available"]:
        return {"reply": result["reply"], "provider": "ollama", "available": True, "model": req.model}

    claude_result = await claude_ai.generate(req.message, system)
    if claude_result["available"]:
        return {"reply": claude_result["reply"], "provider": "claude", "available": True, "model": "claude-haiku-4-5-20251001"}

    return JSONResponse(
        status_code=503,
        content={
            "reply": (
                "No AI backend available.\n\n"
                "Option 1 — Local (free): install Ollama then run:\n  ollama pull llama3.2:3b\n\n"
                "Option 2 — Claude: set ANTHROPIC_API_KEY in your environment."
            ),
            "provider": "none",
            "available": False,
        },
    )


@app.get("/api/ollama/models")
async def ollama_models():
    models = await ollama.list_models()
    return {"models": models, "available": len(models) > 0}


@app.post("/api/training/save")
async def save_training_pair(req: TrainingPair):
    question = _sanitize(req.question)
    answer = _sanitize(req.answer)
    if not question or not answer:
        return JSONResponse(status_code=400, content={"detail": "Empty question or answer"})
    entry = json.dumps({"instruction": question, "output": answer}, ensure_ascii=False)
    with open(_TRAINING_PATH, "a", encoding="utf-8") as f:
        f.write(entry + "\n")
    return {"saved": True, "instruction": question}


@app.get("/api/process/descriptions")
async def process_descriptions():
    return _PROC_DESC


@app.get("/api/process/describe/{name}")
async def process_describe(name: str):
    if name in _PROC_DESC:
        return {"name": name, "description": _PROC_DESC[name], "source": "local"}
    if name in _desc_cache:
        return {"name": name, "description": _desc_cache[name], "source": "cache"}

    system = (
        "You are a Windows system expert. Describe the given process in 1-2 sentences: "
        "what software it belongs to, what it does, and whether it is safe. Be concise and factual."
    )
    prompt = f"What is the Windows process named '{name}'?"

    result = await ollama.generate(prompt, system)
    if not result["available"]:
        result = await claude_ai.generate(prompt, system)

    if result["available"] and result["reply"]:
        _desc_cache[name] = result["reply"]
        return {"name": name, "description": result["reply"], "source": "ai"}

    return {"name": name, "description": None, "source": "unknown"}


@app.post("/api/restart/{agent_id}")
async def restart_agent(agent_id: str):
    return JSONResponse(status_code=501, content={"detail": "restart not implemented (v2)"})


_DASHBOARD = pathlib.Path(__file__).parent / "dashboard.html"


@app.get("/dashboard")
async def dashboard():
    return FileResponse(_DASHBOARD, media_type="text/html")
