from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from termmon import brain
from termmon.scanner.health import check_health
from termmon.scanner.mcp import scan_mcp
from termmon.scanner.ports import scan_ports

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


@app.post("/api/brain/sync")
async def brain_sync():
    result = await _full_scan()
    await brain.sync(result)
    return {"synced": True, "summary": result["summary"]}


@app.post("/api/kill/{pid}")
async def kill_process(pid: int):
    return JSONResponse(status_code=501, content={"detail": "kill not implemented (v2)"})


@app.post("/api/restart/{agent_id}")
async def restart_agent(agent_id: str):
    return JSONResponse(status_code=501, content={"detail": "restart not implemented (v2)"})
