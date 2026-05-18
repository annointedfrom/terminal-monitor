import pathlib
import tempfile
import time
from unittest.mock import MagicMock, patch

import yaml

from termmon.scanner.ports import _load_labels, scan_ports


def test_load_labels_from_yaml():
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"agents": [{"port": 8082, "name": "Job Agent"}]}, f)
        path = pathlib.Path(f.name)
    labels = _load_labels(path)
    assert labels == {8082: "Job Agent"}


def test_load_labels_missing_file():
    labels = _load_labels(pathlib.Path("/nonexistent/path.yaml"))
    assert labels == {}


def _make_conn(port, pid, status="LISTEN"):
    conn = MagicMock()
    conn.status = status
    conn.laddr = MagicMock(port=port)
    conn.pid = pid
    return conn


def test_scan_ports_filters_listen_only():
    conn_listen = _make_conn(8082, 100, "LISTEN")
    conn_established = _make_conn(9000, 200, "ESTABLISHED")

    mock_proc = MagicMock()
    mock_proc.name.return_value = "python.exe"
    mock_proc.memory_info.return_value = MagicMock(rss=50 * 1024 * 1024)
    mock_proc.create_time.return_value = 0.0

    with patch("psutil.net_connections", return_value=[conn_listen, conn_established]), \
         patch("psutil.Process", return_value=mock_proc), \
         patch("time.time", return_value=3600.0):
        result = scan_ports(hub_config_path=pathlib.Path("/nonexistent.yaml"))

    assert len(result) == 1
    assert result[0]["port"] == 8082


def test_scan_ports_attaches_label():
    conn = _make_conn(8082, 100)

    mock_proc = MagicMock()
    mock_proc.name.return_value = "python.exe"
    mock_proc.memory_info.return_value = MagicMock(rss=10 * 1024 * 1024)
    mock_proc.create_time.return_value = 0.0

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump({"agents": [{"port": 8082, "name": "Job Agent"}]}, f)
        cfg_path = pathlib.Path(f.name)

    with patch("psutil.net_connections", return_value=[conn]), \
         patch("psutil.Process", return_value=mock_proc), \
         patch("time.time", return_value=3600.0):
        result = scan_ports(hub_config_path=cfg_path)

    assert result[0]["label"] == "Job Agent"
