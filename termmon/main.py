from __future__ import annotations

import asyncio
import json
import logging
import pathlib
import re
from contextlib import asynccontextmanager
from datetime import datetime, timezone

import httpx
import psutil
from fastapi import FastAPI, Request, WebSocket
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field
from termmon.licensing import verify_license, LicenseInfo, Tier, require_tier
from termmon.updater import check_updates, ollama_pull
from termmon.plugin_loader import load_plugins, _resolve_plugins_dir, LoadedPlugin

from termmon import brain
from termmon.config import get_settings, write_settings
from termmon.memory import (
    init_db as _init_db,
    add_entry as _add_entry,
    get_recent as _get_recent,
    search as _memory_search,
    delete_entry as _delete_entry,
    import_shell_history as _import_shell_history,
)
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

# Sentinel used to detect test-pre-seeded app.state.memory_conn in lifespan
_SENTINEL = object()

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


def _register_plugin_endpoints(app: FastAPI, plugin: LoadedPlugin) -> None:
    name = plugin.meta.name
    _scan = plugin.scan
    _tab_html = plugin.tab_html

    async def _data():
        try:
            return _scan()
        except Exception as exc:
            logger.warning("Plugin %s scan() raised: %s", name, exc)
            return JSONResponse(status_code=500, content={"detail": "Plugin error"})

    app.add_api_route(f"/api/plugins/{name}/data", _data, methods=["GET"])

    if plugin.meta.has_tab:
        async def _tab():
            html = _tab_html()
            if html is None:
                return JSONResponse(status_code=404, content={"detail": "tab.html not found"})
            return HTMLResponse(html)

        app.add_api_route(f"/api/plugins/{name}/tab", _tab, methods=["GET"])

    if plugin.has_router():
        try:
            app.include_router(plugin.get_router(), prefix=f"/api/plugins/{name}")
        except Exception as exc:
            logger.warning("Plugin %s: router() failed: %s — action routes not registered", name, exc)


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
            license_info = getattr(app.state, "license", None)
            conn = getattr(app.state, "memory_conn", None)
            since_ts = getattr(app.state, "last_memory_sync_ts", None)
            is_diamond = license_info is not None and license_info.tier == Tier.DIAMOND
            new_ts = await brain.sync(
                result,
                conn=conn if is_diamond else None,
                since_ts=since_ts if is_diamond else None,
            )
            if new_ts:
                app.state.last_memory_sync_ts = new_ts
        except Exception as exc:
            logger.warning("Brain loop error: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    app.state.license = verify_license(settings.license_key)
    app.state.update_cache = None
    plugins_dir = _resolve_plugins_dir(settings.plugins_dir)
    app.state.plugins = load_plugins(plugins_dir)
    for plugin in app.state.plugins:
        _register_plugin_endpoints(app, plugin)
    _pre_seeded_conn = getattr(app.state, "memory_conn", _SENTINEL)
    if _pre_seeded_conn is not _SENTINEL:
        # Test pre-seeded the connection — skip production DB init entirely
        pass
    elif settings.memory.enabled:
        try:
            app.state.memory_conn = _init_db(
                pathlib.Path("data/memory.db"), settings.memory.max_entries
            )
        except Exception as exc:
            logger.warning("Memory DB init failed: %s", exc)
            app.state.memory_conn = None
        if app.state.memory_conn is not None:
            try:
                if settings.memory.shell_history_import:
                    _import_shell_history(app.state.memory_conn, settings.memory.max_entries)
                scan = await _full_scan()
                res = get_resources()
                _add_entry(
                    app.state.memory_conn,
                    "snapshot",
                    (
                        f"ports={scan['summary']['port_count']}, "
                        f"processes={scan['summary']['process_count']}, "
                        f"MCP={scan['summary']['mcp_count']}, "
                        f"CPU={res.get('cpu_percent', 0):.0f}%, "
                        f"RAM={res.get('memory', {}).get('percent', 0):.0f}%"
                    ),
                    {
                        "port_count": scan["summary"]["port_count"],
                        "process_count": scan["summary"]["process_count"],
                        "mcp_count": scan["summary"]["mcp_count"],
                    },
                    "auto",
                    settings.memory.max_entries,
                )
                app.state.last_memory_sync_ts = datetime.now(timezone.utc).isoformat()
            except Exception as exc:
                logger.warning("Memory startup snapshot failed (non-fatal): %s", exc)
    else:
        app.state.memory_conn = None
    tasks = []
    if settings.brain.enabled:
        tasks.append(asyncio.create_task(_brain_loop()))
    yield
    for t in tasks:
        t.cancel()


class MemoryAddRequest(BaseModel):
    type: str = "note"
    content: str
    metadata: dict = Field(default_factory=dict)


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


@app.get("/api/plugins")
async def list_plugins(request: Request):
    plugins = getattr(request.app.state, "plugins", [])
    return [
        {
            "name": p.meta.name,
            "label": p.meta.label,
            "version": p.meta.version,
            "description": p.meta.description,
            "has_tab": p.meta.has_tab,
        }
        for p in plugins
    ]


@app.get("/api/memory", dependencies=[require_tier(Tier.MID)])
async def list_memory(
    request: Request,
    type: str | None = None,
    limit: int = 50,
    search: str | None = None,
):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    if search:
        return _memory_search(conn, search, limit)
    return _get_recent(conn, type, limit)


@app.post("/api/memory", dependencies=[require_tier(Tier.MID)])
async def add_memory(body: MemoryAddRequest, request: Request):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    settings = get_settings()
    entry_id = _add_entry(
        conn, body.type, body.content, body.metadata, "user", settings.memory.max_entries
    )
    return {"id": entry_id}


@app.post("/api/memory/import-shell", dependencies=[require_tier(Tier.MID)])
async def reimport_shell(request: Request):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    settings = get_settings()
    added = _import_shell_history(conn, settings.memory.max_entries)
    return {"added": added}


@app.get("/api/memory/export", dependencies=[require_tier(Tier.MID)])
async def export_memory(request: Request):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    return _get_recent(conn, None, 100_000)


@app.get("/api/memory/insights", dependencies=[require_tier(Tier.DIAMOND)])
async def memory_insights(request: Request):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    settings = get_settings()
    try:
        async with httpx.AsyncClient() as client:
            r = await client.get(
                f"{settings.brain.url}/api/claude/search",
                params={"q": "terminal monitor commands patterns", "limit": 5},
                timeout=5.0,
            )
            if r.status_code == 200:
                return {"source": "brain", "suggestions": r.json()}
    except Exception:
        pass
    cmds = _get_recent(conn, "command", 5)
    return {"source": "local", "suggestions": [{"text": e["content"]} for e in cmds]}


@app.delete("/api/memory/{entry_id}", dependencies=[require_tier(Tier.MID)])
async def delete_memory(entry_id: int, request: Request):
    conn = getattr(request.app.state, "memory_conn", None)
    if conn is None:
        return JSONResponse(status_code=503, content={"detail": "Memory not available"})
    deleted = _delete_entry(conn, entry_id)
    if not deleted:
        return JSONResponse(status_code=404, content={"detail": "Entry not found"})
    return {"deleted": True, "id": entry_id}


@app.get("/api/update/check")
async def update_check(request: Request):
    if request.app.state.update_cache is None:
        request.app.state.update_cache = await check_updates(
            getattr(request.app.state, "license", None)
        )
    return request.app.state.update_cache


@app.post("/api/update/model/pull", dependencies=[require_tier(Tier.MID)])
async def model_pull(req: ModelPullRequest, request: Request):
    try:
        await ollama_pull(req.tag)
        conn = getattr(request.app.state, "memory_conn", None)
        if conn is not None:
            settings = get_settings()
            try:
                _add_entry(conn, "command", f"ollama pull {req.tag}",
                           {"action": "model_pull", "target": req.tag, "result": "ok"},
                           "termmon", settings.memory.max_entries)
            except Exception as exc:
                logger.warning("Memory log for model_pull failed: %s", exc)
        return {"pulled": True, "tag": req.tag}
    except Exception as exc:
        logger.warning("Model pull failed for tag=%s: %s", req.tag, exc)
        return JSONResponse(status_code=503, content={"detail": "Ollama unavailable"})


@app.post("/api/brain/sync")
async def brain_sync(_: LicenseInfo = require_tier(Tier.DIAMOND)):
    result = await _full_scan()
    await brain.sync(result)
    return {"synced": True, "summary": result["summary"]}


@app.post("/api/kill/{pid}", dependencies=[require_tier(Tier.MID)])
async def kill_process(pid: int, request: Request):
    try:
        proc = psutil.Process(pid)
        proc_name = proc.name()
        proc.terminate()
        await asyncio.sleep(0.5)
        if proc.is_running():
            proc.kill()
        conn = getattr(request.app.state, "memory_conn", None)
        if conn is not None:
            settings = get_settings()
            try:
                _add_entry(conn, "command", f"kill {proc_name} (pid={pid})",
                           {"action": "kill", "target": proc_name, "pid": pid, "result": "ok"},
                           "termmon", settings.memory.max_entries)
            except Exception as exc:
                logger.warning("Memory log for kill failed: %s", exc)
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


class ModelPullRequest(BaseModel):
    tag: str


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
    license_key: str = ""


@app.post("/api/chat")
async def chat_with_ai(req: ChatRequest, request: Request, _: LicenseInfo = require_tier(Tier.MID)):
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
    conn = getattr(request.app.state, "memory_conn", None)
    settings = get_settings()
    if conn is not None:
        mem_parts = []
        recent_chats = _get_recent(conn, "chat", 10)
        if recent_chats:
            def _chat_role(meta_str: str) -> str:
                try:
                    return json.loads(meta_str or "{}").get("role", "?")
                except Exception:
                    return "?"
            chat_lines = "\n".join(
                f"  [{_chat_role(e['metadata'])}] {e['content'][:200]}"
                for e in reversed(recent_chats)
            )
            mem_parts.append(f"Recent conversation:\n{chat_lines}")
        recent_cmds = _get_recent(conn, "command", 20)
        if recent_cmds:
            cmd_lines = "\n".join(f"  {e['content'][:200]}" for e in recent_cmds)
            mem_parts.append(f"Recent commands:\n{cmd_lines}")
        snapshots = _get_recent(conn, "snapshot", 1)
        if snapshots:
            mem_parts.append(f"Last snapshot: {snapshots[0]['content']}")
        if mem_parts:
            system += "\n\n" + "\n\n".join(mem_parts)

    result = await ollama.generate(req.message, system, req.model)
    if result["available"]:
        reply = result["reply"]
        provider = "ollama"
        model_name = req.model
    else:
        claude_result = await claude_ai.generate(req.message, system)
        if claude_result["available"]:
            reply = claude_result["reply"]
            provider = "claude"
            model_name = "claude-haiku-4-5-20251001"
        else:
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

    if conn is not None:
        try:
            _add_entry(conn, "chat", req.message,
                       {"role": "you", "model": model_name}, "auto",
                       settings.memory.max_entries)
            _add_entry(conn, "chat", reply,
                       {"role": "ai", "model": model_name}, "auto",
                       settings.memory.max_entries)
        except Exception as exc:
            logger.warning("Memory save for chat failed: %s", exc)

    return {"reply": reply, "provider": provider, "available": True, "model": model_name}


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
    info: LicenseInfo | None = getattr(websocket.app.state, "license", None)
    if info is None or info.tier < Tier.MID:
        await websocket.close(code=1008, reason="license_required")
        return
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
async def setup_post(req: SetupRequest, request: Request):
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
        license_key=req.license_key,
    )
    write_settings(settings)
    request.app.state.license = verify_license(req.license_key)
    return {"saved": True}


@app.get("/dashboard")
async def dashboard():
    if not _CONFIG_PATH.exists():
        return RedirectResponse("/setup", status_code=303)
    return FileResponse(_DASHBOARD, media_type="text/html")
