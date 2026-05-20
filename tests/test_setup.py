# tests/test_setup.py
import pathlib
import yaml
from unittest.mock import patch


def test_build_config_structure():
    import setup as setup_mod
    cfg = setup_mod._build_config(
        title="Test Ops", default_model="llama3.2:3b", training_threshold=50,
        brain_enabled=False, brain_url="http://localhost:8000",
        services=[{"name": "my-agent", "port": 8090}],
        cpu_threshold=70, ram_threshold=75, gpu_temp_threshold=85, offline_notify=True,
    )
    assert cfg["dashboard"]["title"] == "Test Ops"
    assert cfg["brain"]["enabled"] is False
    assert cfg["services"][0]["port"] == 8090
    assert cfg["alerts"]["cpu_threshold"] == 70


def test_write_config_writes_yaml(tmp_path):
    import setup as setup_mod
    out = tmp_path / "config.yaml"
    cfg = setup_mod._build_config(
        title="X", default_model="m", training_threshold=100,
        brain_enabled=False, brain_url="http://localhost:8000",
        services=[], cpu_threshold=80, ram_threshold=80, gpu_temp_threshold=80, offline_notify=True,
    )
    setup_mod._write_config(cfg, out)
    loaded = yaml.safe_load(out.read_text())
    assert loaded["dashboard"]["title"] == "X"


def test_write_config_overwrites_existing(tmp_path):
    import setup as setup_mod
    out = tmp_path / "config.yaml"
    out.write_text("old: data\n")
    cfg = setup_mod._build_config(
        title="New", default_model="m", training_threshold=100,
        brain_enabled=False, brain_url="http://localhost:8000",
        services=[], cpu_threshold=80, ram_threshold=80, gpu_temp_threshold=80, offline_notify=True,
    )
    setup_mod._write_config(cfg, out)
    loaded = yaml.safe_load(out.read_text())
    assert "old" not in loaded
    assert loaded["dashboard"]["title"] == "New"
