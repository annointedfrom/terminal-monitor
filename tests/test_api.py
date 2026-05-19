from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from termmon.main import app
from termmon.scanner.resources import get_resources

client = TestClient(app)


def _mock_scan():
    return {
        "scanned_at": "2026-05-18T00:00:00+00:00",
        "ports": [
            {
                "port": 8082,
                "pid": 1,
                "process": "python.exe",
                "memory_mb": 50.0,
                "uptime_s": 100,
                "healthy": True,
                "label": "Job Agent",
            }
        ],
        "mcp_servers": [
            {"name": "playwright", "command": "npx @playwright/mcp@latest", "running": True, "pid": 9999}
        ],
        "summary": {"port_count": 1, "mcp_count": 1, "process_count": 1},
    }


def test_health():
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_scan_returns_required_keys():
    with patch("termmon.main._full_scan", new=AsyncMock(return_value=_mock_scan())):
        r = client.get("/api/scan")
    assert r.status_code == 200
    data = r.json()
    assert "ports" in data
    assert "mcp_servers" in data
    assert "summary" in data


def test_stats_port_count():
    with patch("termmon.main.scan_ports", return_value=[{"port": 8082}, {"port": 8084}]):
        r = client.get("/api/stats/port_count")
    assert r.status_code == 200
    assert r.json() == 2


def test_stats_mcp_count():
    with patch(
        "termmon.main.scan_mcp",
        return_value=[
            {"running": True, "pid": 1},
            {"running": False, "pid": None},
        ],
    ):
        r = client.get("/api/stats/mcp_count")
    assert r.status_code == 200
    assert r.json() == 1


def test_brain_sync_endpoint():
    mock_sync = AsyncMock()
    with patch("termmon.main._full_scan", new=AsyncMock(return_value=_mock_scan())), \
         patch("termmon.main.brain.sync", new=mock_sync):
        r = client.post("/api/brain/sync")
    assert r.status_code == 200
    assert r.json()["synced"] is True
    mock_sync.assert_called_once()


def test_kill_process_success():
    mock_proc = MagicMock()
    mock_proc.is_running.return_value = False
    with patch("termmon.main.psutil.Process", return_value=mock_proc):
        r = client.post("/api/kill/12345")
    assert r.status_code == 200
    assert r.json() == {"killed": True, "pid": 12345}
    mock_proc.terminate.assert_called_once()


def test_kill_process_not_found():
    import psutil as _psutil
    with patch("termmon.main.psutil.Process", side_effect=_psutil.NoSuchProcess(pid=99999)):
        r = client.post("/api/kill/99999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_kill_process_access_denied():
    import psutil as _psutil
    with patch("termmon.main.psutil.Process", side_effect=_psutil.AccessDenied(pid=1)):
        r = client.post("/api/kill/1")
    assert r.status_code == 403
    assert "denied" in r.json()["detail"].lower()


def test_restart_stub_returns_501():
    r = client.post("/api/restart/job-agent")
    assert r.status_code == 501


def test_get_resources_structure():
    mock_mem = MagicMock()
    mock_mem.total = 17179869184
    mock_mem.available = 9000000000
    mock_mem.percent = 47.6
    mock_mem.used = 8179869184

    mock_disk = MagicMock()
    mock_disk.total = 512000000000
    mock_disk.used = 200000000000
    mock_disk.free = 312000000000
    mock_disk.percent = 39.1

    with patch("termmon.scanner.resources.psutil.cpu_percent", return_value=22.5), \
         patch("termmon.scanner.resources.psutil.virtual_memory", return_value=mock_mem), \
         patch("termmon.scanner.resources.psutil.disk_usage", return_value=mock_disk):
        r = client.get("/api/resources")

    assert r.status_code == 200
    data = r.json()
    assert data["cpu_percent"] == 22.5
    assert data["memory"]["total"] == 17179869184
    assert data["memory"]["percent"] == 47.6
    assert data["disk"]["percent"] == 39.1


def test_get_resources_live_schema():
    data = get_resources()
    assert isinstance(data["cpu_percent"], float)
    assert {"total", "available", "percent", "used"} <= data["memory"].keys()
    assert {"total", "used", "free", "percent"} <= data["disk"].keys()


def test_dashboard_returns_html():
    r = client.get("/dashboard")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]
