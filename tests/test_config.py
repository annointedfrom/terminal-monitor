import textwrap
from unittest.mock import patch


def test_defaults_when_no_config_file(tmp_path):
    config_path = tmp_path / "config.yaml"
    import termmon.config as cfg_mod
    cfg_mod._settings = None
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        s = cfg_mod._load()
    assert s.dashboard.title == "Ops Dashboard"
    assert s.brain.enabled is False
    assert s.alerts.cpu_threshold == 80
    assert s.services == []


def test_loads_custom_values(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text(textwrap.dedent("""\
        dashboard:
          title: "My Ops"
          default_model: "llama3.2:3b"
          training_threshold: 50
        brain:
          enabled: true
          url: "http://localhost:9000"
        services:
          - name: "my-agent"
            port: 8090
        alerts:
          cpu_threshold: 70
          ram_threshold: 75
          offline_notify: false
    """), encoding="utf-8")
    import termmon.config as cfg_mod
    cfg_mod._settings = None
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        s = cfg_mod._load()
    assert s.dashboard.title == "My Ops"
    assert s.brain.enabled is True
    assert s.brain.url == "http://localhost:9000"
    assert s.services[0].name == "my-agent"
    assert s.services[0].port == 8090
    assert s.alerts.cpu_threshold == 70
    assert s.alerts.offline_notify is False


def test_write_and_reload(tmp_path):
    import yaml
    import termmon.config as cfg_mod
    from termmon.config import Settings, DashboardConfig
    cfg_mod._settings = None
    config_path = tmp_path / "config.yaml"
    s = Settings(dashboard=DashboardConfig(title="Written"))
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        cfg_mod.write_settings(s)
        loaded = yaml.safe_load(config_path.read_text())
    assert loaded["dashboard"]["title"] == "Written"


def test_missing_sections_get_defaults(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("dashboard:\n  title: Partial\n", encoding="utf-8")
    import termmon.config as cfg_mod
    cfg_mod._settings = None
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        s = cfg_mod._load()
    assert s.alerts.cpu_threshold == 80
    assert s.brain.enabled is False
    assert s.services == []


def test_license_key_defaults_to_empty(tmp_path):
    config_path = tmp_path / "config.yaml"
    import termmon.config as cfg_mod
    cfg_mod._settings = None
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        s = cfg_mod._load()
    assert s.license_key == ""


def test_license_key_loads_from_yaml(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("license_key: 'eyJtest'\n", encoding="utf-8")
    import termmon.config as cfg_mod
    cfg_mod._settings = None
    with patch.object(cfg_mod, "_CONFIG_PATH", config_path):
        s = cfg_mod._load()
    assert s.license_key == "eyJtest"


def test_memory_config_defaults():
    from termmon.config import Settings
    s = Settings()
    assert s.memory.enabled is True
    assert s.memory.max_entries == 10000
    assert s.memory.shell_history_import is True


def test_memory_config_from_yaml(tmp_path, monkeypatch):
    import yaml
    import termmon.config as cfg_mod
    cfg_file = tmp_path / "config.yaml"
    cfg_file.write_text(
        yaml.dump({"memory": {"enabled": False, "max_entries": 500, "shell_history_import": False}}),
        encoding="utf-8",
    )
    monkeypatch.setattr(cfg_mod, "_CONFIG_PATH", cfg_file)
    monkeypatch.setattr(cfg_mod, "_settings", None)
    s = cfg_mod.get_settings()
    assert s.memory.enabled is False
    assert s.memory.max_entries == 500
    assert s.memory.shell_history_import is False
