import json
import pathlib
import tempfile
from unittest.mock import MagicMock, patch

from termmon.scanner.mcp import _read_mcp_config, scan_mcp


def _make_settings(servers: dict) -> pathlib.Path:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        json.dump({"mcpServers": servers}, f)
        return pathlib.Path(f.name)


def test_read_mcp_config_parses_servers():
    path = _make_settings({"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}})
    result = _read_mcp_config(path)
    assert "playwright" in result


def test_read_mcp_config_missing_file():
    result = _read_mcp_config(pathlib.Path("/nonexistent.json"))
    assert result == {}


def test_scan_mcp_running():
    path = _make_settings({"playwright": {"command": "npx", "args": ["@playwright/mcp@latest"]}})
    mock_proc = MagicMock()
    mock_proc.info = {
        "pid": 9999,
        "name": "node.exe",
        "cmdline": ["node", "@playwright/mcp@latest"],
    }
    with patch("psutil.process_iter", return_value=[mock_proc]):
        result = scan_mcp(settings_path=path)
    assert result[0]["name"] == "playwright"
    assert result[0]["running"] is True
    assert result[0]["pid"] == 9999


def test_scan_mcp_not_running():
    path = _make_settings(
        {"chrome-devtools-mcp": {"command": "npx", "args": ["chrome-devtools-mcp"]}}
    )
    with patch("psutil.process_iter", return_value=[]):
        result = scan_mcp(settings_path=path)
    assert result[0]["running"] is False
    assert result[0]["pid"] is None
