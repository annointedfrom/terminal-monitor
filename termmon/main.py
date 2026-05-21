from __future__ import annotations

import asyncio
import json
import logging
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import pathlib

import psutil
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from termmon.licensing import verify_license, LicenseInfo, Tier, require_tier
from pydantic import BaseModel

from termmon import brain
from termmon.config import get_settings, write_settings
from termmon.scanner import ollama
from termmon.scanner import claude_ai
from termmon.scanner.alerts import evaluate_alerts
from termmon.scanner.health import check_health
from termmon.scanner.mcp import scan_mcp
from termmon.scanner.ports import scan_ports
from termmon.scanner.processes import scan_background_processes
from termmon.scanner.resources import get_resources
from termmon.scanner.history import (
    append_scan, append_resource,
    load_scan_history, load_resource_history,
)

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
_last_scan: dict | None = None
_last_resources: dict | None = None


async def _full_scan() -> dict:
    global _last_scan
    ports = scan_ports()
    ports = await check_health(ports)
    mcps = scan_mcp()
    mcp_count = sum(1 for m in mcps if m["running"])
    process_names = {p["process"] for p in ports if p["process"] != "unknown"}
    port_pids = {p["pid"] for p in ports if p["pid"]}
    background = scan_background_processes(exclude_pids=port_pids)
    result = {
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
    _last_scan = result
    append_scan(result)
    return result


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
    settings = get_settings()
    app.state.license = verify_license(settings.license_key)
    tasks = []
    if settings.brain.enabled:
        tasks.append(asyncio.create_task(_brain_loop()))
    yield
    for t in tasks:
        t.cancel()


app = FastAPI(title="Terminal Monitor", lifespan=lifespan)

_LICENSE_EXEMPT = {"/health", "/setup", "/api/setup", "/dashboard"}


@app.middleware("http")
async def license_gate(request: Request, call_next):
    if request.url.path.rstrip("/") in _LICENSE_EXEMPT:
        return await call_next(request)
    if getattr(request.app.state, "license", None) is None:
        return JSONResponse(
            status_code=403,
            content={"error": "license_required", "detail": "A valid license key is required"},
        )
    return await call_next(request)


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
    global _last_resources
    result = get_resources()
    _last_resources = result
    append_resource(result)
    return result


@app.get("/api/history")
async def get_history():
    return {
        "scan": load_scan_history(n=30),
        "resources": load_resource_history(n=30),
    }


@app.get("/api/alerts/current")
async def get_current_alerts():
    if _last_scan is None or _last_resources is None:
        return {"alerts": []}
    settings = get_settings()
    return {"alerts": evaluate_alerts(_last_scan, _last_resources, settings)}


@app.get("/api/config")
async def get_config(request: Request):
    settings = get_settings()
    license_info: LicenseInfo | None = getattr(request.app.state, "license", None)
    return {
        "title": settings.dashboard.title,
        "default_model": settings.dashboard.default_model,
        "training_threshold": settings.dashboard.training_threshold,
        "services": [s.model_dump() for s in settings.services],
        "alerts": settings.alerts.model_dump(),
        "brain_enabled": settings.brain.enabled,
        "tier": license_info.tier.name.lower() if license_info else "none",
    }


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


class SetupRequest(BaseModel):
    title: str = "Ops Dashboard"
    default_model: str = "ops-brain"
    training_threshold: int = 100
    brain_enabled: bool = False
    brain_url: str = "http://localhost:8000"
    services: list[dict] = []
    cpu_threshold: int = 80
    ram_threshold: int = 80
    gpu_temp_threshold: int = 80
    offline_notify: bool = True


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


@app.post("/api/restart/{agent_id}")
async def restart_agent(agent_id: str):
    return JSONResponse(status_code=501, content={"detail": "restart not implemented (v2)"})


@app.get("/api/training/status")
async def training_status():
    settings = get_settings()
    threshold = settings.dashboard.training_threshold
    count = 0
    if _TRAINING_PATH.exists():
        count = sum(
            1
            for line in _TRAINING_PATH.read_text(encoding="utf-8").splitlines()
            if line.strip()
        )
    return {"count": count, "threshold": threshold, "ready": count >= threshold}


@app.websocket("/ws/terminal")
async def terminal_ws(websocket: WebSocket):
    """Local-only PowerShell command runner — one process per command."""
    await websocket.accept()
    try:
        while True:
            cmd = await websocket.receive_text()
            cmd = cmd.strip()
            if not cmd:
                continue
            try:
                proc = await asyncio.create_subprocess_exec(
                    "powershell.exe",
                    "-NoProfile", "-NonInteractive", "-Command", cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=str(pathlib.Path.home()),
                )
                while True:
                    chunk = await proc.stdout.read(1024)
                    if not chunk:
                        break
                    await websocket.send_text(chunk.decode("utf-8", errors="replace"))
                await proc.wait()
                await websocket.send_text(f"\r\n[exit {proc.returncode}]\r\n")
            except Exception as exc:
                await websocket.send_text(f"[error] {exc}\r\n")
    except Exception:
        pass


_CONFIG_PATH = pathlib.Path(__file__).parent.parent / "config.yaml"
_DASHBOARD = pathlib.Path(__file__).parent / "dashboard.html"
_SETUP = pathlib.Path(__file__).parent / "setup.html"


@app.get("/setup")
async def setup_page():
    return FileResponse(_SETUP, media_type="text/html")


@app.post("/api/setup")
async def setup_post(req: SetupRequest):
    from termmon.config import (
        Settings, DashboardConfig, BrainConfig, ServiceConfig, AlertsConfig,
    )
    settings = Settings(
        dashboard=DashboardConfig(
            title=req.title,
            default_model=req.default_model,
            training_threshold=req.training_threshold,
        ),
        brain=BrainConfig(enabled=req.brain_enabled, url=req.brain_url),
        services=[
            ServiceConfig(name=s["name"], port=s["port"], start_command=s.get("start_command"))
            for s in req.services
            if s.get("name") and s.get("port")
        ],
        alerts=AlertsConfig(
            cpu_threshold=req.cpu_threshold,
            ram_threshold=req.ram_threshold,
            gpu_temp_threshold=req.gpu_temp_threshold,
            offline_notify=req.offline_notify,
        ),
    )
    write_settings(settings)
    return {"saved": True}


@app.get("/dashboard")
async def dashboard():
    if not _CONFIG_PATH.exists():
        return RedirectResponse("/setup", status_code=303)
    return FileResponse(_DASHBOARD, media_type="text/html")
