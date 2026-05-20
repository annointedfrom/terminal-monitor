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

    mock_freq = MagicMock()
    mock_freq.current = 3200.0
    mock_freq.max = 4800.0

    with patch("termmon.scanner.resources.psutil.cpu_percent", return_value=[22.5, 18.0, 30.0, 20.0]), \
         patch("termmon.scanner.resources.psutil.cpu_freq", return_value=mock_freq), \
         patch("termmon.scanner.resources.psutil.virtual_memory", return_value=mock_mem), \
         patch("termmon.scanner.resources.psutil.disk_usage", return_value=mock_disk):
        r = client.get("/api/resources")

    assert r.status_code == 200
    data = r.json()
    assert data["cpu_percent"] == 22.6  # round(avg([22.5,18.0,30.0,20.0]), 1)
    assert data["memory"]["total"] == 17179869184
    assert data["memory"]["percent"] == 47.6
    assert data["disk"]["percent"] == 39.1
    assert data["cpu_cores"] == 4
    assert len(data["cpu_per_core"]) == 4


def test_get_resources_live_schema():
    data = get_resources()
    assert isinstance(data["cpu_percent"], float)
    assert {"total", "available", "percent", "used"} <= data["memory"].keys()
    assert {"total", "used", "free", "percent"} <= data["disk"].keys()


def test_dashboard_returns_html():
    import pathlib
    with patch("termmon.main._CONFIG_PATH", pathlib.Path(__file__).parent / "test_config_stub.yaml"):
        r = client.get("/dashboard")
    assert r.status_code == 200
    assert "text/html" in r.headers["content-type"]


def test_process_detail_existing():
    import psutil as _psutil
    mock_proc = MagicMock()
    mock_proc.__enter__ = MagicMock(return_value=None)
    mock_proc.__exit__ = MagicMock(return_value=False)
    mock_proc.oneshot.return_value = mock_proc
    mock_proc.name.return_value = "python.exe"
    mock_proc.exe.return_value = r"C:\Python\python.exe"
    mock_proc.cmdline.return_value = ["python.exe", "app.py"]
    mock_proc.username.return_value = "DESKTOP\\user"
    mock_proc.cpu_percent.return_value = 2.5
    mock_proc.status.return_value = "running"
    mock_proc.create_time.return_value = 1700000000.0
    with patch("termmon.main.psutil.Process", return_value=mock_proc):
        r = client.get("/api/process/1234")
    assert r.status_code == 200
    data = r.json()
    assert data["pid"] == 1234
    assert data["name"] == "python.exe"
    assert "exe" in data
    assert "cmdline" in data
    assert "username" in data
    assert "status" in data


def test_process_detail_not_found():
    import psutil as _psutil
    with patch("termmon.main.psutil.Process", side_effect=_psutil.NoSuchProcess(pid=99999)):
        r = client.get("/api/process/99999")
    assert r.status_code == 404
    assert "not found" in r.json()["detail"].lower()


def test_chat_ollama_unavailable_claude_fallback():
    ollama_unavail = {"reply": None, "available": False}
    claude_result = {"reply": "You have 1 active port.", "available": True}
    with patch("termmon.main._full_scan", new=AsyncMock(return_value=_mock_scan())), \
         patch("termmon.main.ollama.generate", new=AsyncMock(return_value=ollama_unavail)), \
         patch("termmon.main.claude_ai.generate", new=AsyncMock(return_value=claude_result)):
        r = client.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is True
    assert data["provider"] == "claude"
    assert data["reply"] == "You have 1 active port."


def test_chat_both_unavailable():
    unavail = {"reply": None, "available": False}
    with patch("termmon.main._full_scan", new=AsyncMock(return_value=_mock_scan())), \
         patch("termmon.main.ollama.generate", new=AsyncMock(return_value=unavail)), \
         patch("termmon.main.claude_ai.generate", new=AsyncMock(return_value=unavail)):
        r = client.post("/api/chat", json={"message": "hello"})
    assert r.status_code == 503
    data = r.json()
    assert data["available"] is False


def test_chat_ollama_available():
    mock_result = {"reply": "You have 1 port active.", "available": True}
    with patch("termmon.main._full_scan", new=AsyncMock(return_value=_mock_scan())), \
         patch("termmon.main.ollama.generate", new=AsyncMock(return_value=mock_result)):
        r = client.post("/api/chat", json={"message": "how many ports?", "model": "ops-brain"})
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is True
    assert data["provider"] == "ollama"
    assert data["reply"] == "You have 1 port active."
    assert data["model"] == "ops-brain"


def test_ollama_models_available():
    with patch("termmon.main.ollama.list_models", new=AsyncMock(return_value=["llama3.2:3b", "phi3:mini"])):
        r = client.get("/api/ollama/models")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is True
    assert "llama3.2:3b" in data["models"]


def test_ollama_models_unavailable():
    with patch("termmon.main.ollama.list_models", new=AsyncMock(return_value=[])):
        r = client.get("/api/ollama/models")
    assert r.status_code == 200
    data = r.json()
    assert data["available"] is False
    assert data["models"] == []


def test_process_descriptions_returns_dict():
    r = client.get("/api/process/descriptions")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, dict)
    assert "lsass.exe" in data
    assert "Dolphin.exe" in data
    assert "steam.exe" not in data  # case-sensitive


def test_process_describe_local_hit():
    r = client.get("/api/process/describe/lsass.exe")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "local"
    assert "security" in data["description"].lower()


def test_process_describe_ai_fallback():
    unavail = {"reply": None, "available": False}
    ai_result = {"reply": "SomeObscureApp is a background helper process.", "available": True}
    with patch("termmon.main.ollama.generate", new=AsyncMock(return_value=unavail)), \
         patch("termmon.main.claude_ai.generate", new=AsyncMock(return_value=ai_result)):
        r = client.get("/api/process/describe/SomeObscureApp_notindict.exe")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "ai"
    assert "obscure" in data["description"].lower()


def test_process_describe_unknown_no_ai():
    unavail = {"reply": None, "available": False}
    with patch("termmon.main.ollama.generate", new=AsyncMock(return_value=unavail)), \
         patch("termmon.main.claude_ai.generate", new=AsyncMock(return_value=unavail)):
        r = client.get("/api/process/describe/totally_unknown_xyz.exe")
    assert r.status_code == 200
    data = r.json()
    assert data["source"] == "unknown"
    assert data["description"] is None


def test_api_config_safe_fields():
    r = client.get("/api/config")
    assert r.status_code == 200
    data = r.json()
    assert "title" in data
    assert "default_model" in data
    assert "services" in data
    assert "alerts" in data
    assert "brain_enabled" in data
    # brain URL must NOT be exposed to frontend
    assert "url" not in data
    assert "brain_url" not in data


def test_api_history_structure():
    r = client.get("/api/history")
    assert r.status_code == 200
    data = r.json()
    assert "scan" in data
    assert "resources" in data
    assert isinstance(data["scan"], list)
    assert isinstance(data["resources"], list)
