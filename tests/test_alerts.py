# tests/test_alerts.py
from termmon.config import Settings, AlertsConfig, ServiceConfig
from termmon.scanner.alerts import evaluate_alerts


def _settings(**kw) -> Settings:
    return Settings(alerts=AlertsConfig(**kw))


def _scan(ports=None) -> dict:
    return {"ports": ports or [], "mcp_servers": [], "summary": {}}


def _res(cpu=0.0, ram=0.0, gpu_temp=None) -> dict:
    r: dict = {"cpu_percent": cpu, "memory": {"percent": ram}, "disk": {"percent": 5.0}}
    if gpu_temp is not None:
        r["gpu_temp_c"] = gpu_temp
    return r


def test_no_alerts_below_thresholds():
    alerts = evaluate_alerts(_scan(), _res(cpu=50.0, ram=60.0), _settings())
    assert alerts == []


def test_cpu_triggers_alert():
    alerts = evaluate_alerts(_scan(), _res(cpu=85.0), _settings(cpu_threshold=80))
    assert any("cpu" in a["id"] for a in alerts)


def test_ram_triggers_alert_with_value_in_message():
    alerts = evaluate_alerts(_scan(), _res(ram=87.0), _settings(ram_threshold=80))
    msg = next(a["message"] for a in alerts if "ram" in a["id"])
    assert "87" in msg


def test_service_offline_when_notify_enabled():
    svc = ServiceConfig(name="my-agent", port=8090)
    s = Settings(alerts=AlertsConfig(offline_notify=True), services=[svc])
    alerts = evaluate_alerts(_scan(ports=[]), _res(), s)
    assert any(a["id"] == "service_offline_my-agent" for a in alerts)


def test_offline_notify_false_skips_service_alerts():
    svc = ServiceConfig(name="my-agent", port=8090)
    s = Settings(alerts=AlertsConfig(offline_notify=False), services=[svc])
    alerts = evaluate_alerts(_scan(ports=[]), _res(), s)
    assert not any("service_offline" in a["id"] for a in alerts)


def test_gpu_temp_triggers_alert():
    alerts = evaluate_alerts(_scan(), _res(gpu_temp=85.0), _settings(gpu_temp_threshold=80))
    assert any("gpu_temp" in a["id"] for a in alerts)


def test_alert_ids_deterministic():
    s = _settings(cpu_threshold=80)
    r = _res(cpu=85.0)
    assert [a["id"] for a in evaluate_alerts(_scan(), r, s)] == \
           [a["id"] for a in evaluate_alerts(_scan(), r, s)]


def test_service_healthy_port_no_alert():
    svc = ServiceConfig(name="my-agent", port=8090)
    s = Settings(alerts=AlertsConfig(offline_notify=True), services=[svc])
    port_entry = {"port": 8090, "process": "python.exe", "healthy": True,
                  "pid": 1, "label": "my-agent", "memory_mb": 50.0}
    alerts = evaluate_alerts(_scan(ports=[port_entry]), _res(), s)
    assert not any("service_offline" in a["id"] for a in alerts)
