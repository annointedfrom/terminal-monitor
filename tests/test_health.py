import httpx
import pytest
import respx

from termmon.scanner.health import check_health

_PORT_ENTRY = {
    "port": 8082,
    "pid": 1,
    "process": "python.exe",
    "memory_mb": 50.0,
    "uptime_s": 100,
    "healthy": False,
    "label": "Job Agent",
}


@pytest.mark.asyncio
async def test_healthy_port():
    with respx.mock:
        respx.get("http://localhost:8082/health").mock(return_value=httpx.Response(200))
        result = await check_health([_PORT_ENTRY])
    assert result[0]["healthy"] is True


@pytest.mark.asyncio
async def test_unhealthy_port_connection_error():
    entry = {**_PORT_ENTRY, "port": 9999, "label": ""}
    with respx.mock:
        respx.get("http://localhost:9999/health").mock(
            side_effect=httpx.ConnectError("refused")
        )
        result = await check_health([entry])
    assert result[0]["healthy"] is False


@pytest.mark.asyncio
async def test_falls_back_to_root_on_404():
    entry = {**_PORT_ENTRY, "port": 34872, "label": "Roblox"}
    with respx.mock:
        respx.get("http://localhost:34872/health").mock(return_value=httpx.Response(404))
        respx.get("http://localhost:34872/").mock(return_value=httpx.Response(200))
        result = await check_health([entry])
    assert result[0]["healthy"] is True
