from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pathlib

import psutil
from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel

from termmon import brain
from termmon.scanner import ollama
from termmon.scanner.health import check_health
from termmon.scanner.mcp import scan_mcp
from termmon.scanner.ports import scan_ports
from termmon.scanner.resources import get_resources

logger = logging.getLogger(__name__)


async def _full_scan() -> dict:
    ports = scan_ports()
    ports = await check_health(ports)
    mcps = scan_mcp()
    mcp_count = sum(1 for m in mcps if m["running"])
    process_names = {p["process"] for p in ports if p["process"] != "unknown"}
    return {
        "scanned_at": datetime.now(timezone.utc).isoformat(),
        "ports": ports,
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


class ChatRequest(BaseModel):
    message: str
    model: str = "llama3.2:3b"


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
    if not result["available"]:
        return JSONResponse(
            status_code=503,
            content={
                "reply": "Ollama is not running. Install Ollama and pull a model:\n\n  ollama pull llama3.2:3b",
                "provider": "none",
                "available": False,
            },
        )
    return {"reply": result["reply"], "provider": "ollama", "available": True, "model": req.model}


@app.get("/api/ollama/models")
async def ollama_models():
    models = await ollama.list_models()
    return {"models": models, "available": len(models) > 0}


@app.post("/api/restart/{agent_id}")
async def restart_agent(agent_id: str):
    return JSONResponse(status_code=501, content={"detail": "restart not implemented (v2)"})


_DASHBOARD = pathlib.Path(__file__).parent / "dashboard.html"


@app.get("/dashboard")
async def dashboard():
    return FileResponse(_DASHBOARD, media_type="text/html")
