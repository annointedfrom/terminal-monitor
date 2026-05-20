import json
from unittest.mock import patch

import termmon.scanner.history as hist_mod


def _patched(tmp_path):
    return [
        patch.object(hist_mod, "_DATA_DIR", tmp_path),
        patch.object(hist_mod, "_SCAN_PATH", tmp_path / "scan_history.jsonl"),
        patch.object(hist_mod, "_RESOURCE_PATH", tmp_path / "resource_history.jsonl"),
    ]


def test_append_scan_creates_file(tmp_path):
    with _patched(tmp_path)[0], _patched(tmp_path)[1], _patched(tmp_path)[2]:
        hist_mod.append_scan({"scanned_at": "t1", "summary": {}})
        lines = (tmp_path / "scan_history.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    assert json.loads(lines[0])["scanned_at"] == "t1"


def test_load_returns_last_n(tmp_path):
    patches = _patched(tmp_path)
    with patches[0], patches[1], patches[2]:
        for i in range(10):
            hist_mod.append_scan({"scanned_at": f"t{i}"})
        result = hist_mod.load_scan_history(n=3)
    assert len(result) == 3
    assert result[0]["scanned_at"] == "t7"
    assert result[-1]["scanned_at"] == "t9"


def test_rolling_cap_drops_oldest(tmp_path):
    patches = _patched(tmp_path)
    with patches[0], patches[1], patches[2]:
        for i in range(510):
            hist_mod.append_scan({"scanned_at": f"t{i}"})
        lines = (tmp_path / "scan_history.jsonl").read_text().strip().splitlines()
    assert len(lines) == 500
    assert json.loads(lines[0])["scanned_at"] == "t10"


def test_append_resource_and_load(tmp_path):
    patches = _patched(tmp_path)
    with patches[0], patches[1], patches[2]:
        hist_mod.append_resource({"cpu_percent": 42.0})
        result = hist_mod.load_resource_history(n=5)
    assert len(result) == 1
    assert result[0]["cpu_percent"] == 42.0


def test_empty_returns_empty_list(tmp_path):
    patches = _patched(tmp_path)
    with patches[0], patches[1], patches[2]:
        result = hist_mod.load_scan_history()
    assert result == []
