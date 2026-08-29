from jarvis.core.events import EventBus
from jarvis.diagnostics.monitor import MonitorConfig, ProactiveMonitor


class Clock:
    now = 0.0

    def __call__(self):
        return self.now


def _telemetry(*, ram=10, disk=10, gpu_available=False, temp=None,
               vram_used=None, vram_total=None):
    return {
        "ram": {"percent": ram},
        "disk": {"used_percent": disk},
        "gpu": {"available": gpu_available, "temp_c": temp,
                "vram_used_mb": vram_used, "vram_total_mb": vram_total},
    }


def test_warning_is_not_repeated_until_cooldown():
    bus, clock, seen = EventBus(), Clock(), []
    bus.subscribe("system.*", seen.append)
    monitor = ProactiveMonitor(bus, MonitorConfig(enabled=True, cooldown=30), clock=clock)
    monitor.evaluate_telemetry(_telemetry(ram=90))
    monitor.evaluate_telemetry(_telemetry(ram=91))
    assert [e.name for e in seen] == ["system.warning"]
    clock.now = 31
    monitor.evaluate_telemetry(_telemetry(ram=92))
    assert [e.name for e in seen] == ["system.warning", "system.warning"]


def test_severity_escalation_is_immediate_and_payload_is_measured():
    bus, clock, seen = EventBus(), Clock(), []
    bus.subscribe("system.*", seen.append)
    monitor = ProactiveMonitor(bus, MonitorConfig(enabled=True, cooldown=300), clock=clock)
    monitor.evaluate_telemetry(_telemetry(disk=91))
    monitor.evaluate_telemetry(_telemetry(disk=99))
    assert [e.name for e in seen] == ["system.warning", "system.alert"]
    assert seen[-1].payload["value"] == 99
    assert seen[-1].payload["threshold"] == 97


def test_recovery_requires_consecutive_clear_samples_and_emits_once():
    bus, seen = EventBus(), []
    bus.subscribe("system.*", seen.append)
    monitor = ProactiveMonitor(bus, MonitorConfig(enabled=True, recovery_samples=2))
    monitor.evaluate_telemetry(_telemetry(ram=99))
    monitor.evaluate_telemetry(_telemetry(ram=20))
    assert [e.name for e in seen] == ["system.alert"]
    monitor.evaluate_telemetry(_telemetry(ram=20))
    monitor.evaluate_telemetry(_telemetry(ram=20))
    assert [e.name for e in seen] == ["system.alert", "system.recovered"]


def test_unknown_gpu_values_never_generate_notifications():
    bus, seen = EventBus(), []
    bus.subscribe("system.*", seen.append)
    monitor = ProactiveMonitor(bus, MonitorConfig(enabled=True))
    monitor.evaluate_telemetry(_telemetry(gpu_available=False))
    assert seen == []


def test_service_error_and_success_use_event_bus_with_recovery():
    bus, seen = EventBus(), []
    bus.subscribe("system.*", seen.append)
    monitor = ProactiveMonitor(bus, MonitorConfig(enabled=True, recovery_samples=1))
    bus.publish("voice.error", {"stage": "tts", "error_type": "TTSError"})
    bus.publish("voice.finished", {"stage": "tts"})
    assert [e.name for e in seen] == ["system.warning", "system.recovered"]
    monitor.close()
    bus.publish("voice.error", {"stage": "tts", "error_type": "TTSError"})
    assert len(seen) == 2


def test_disabled_or_intentionally_disabled_voice_does_not_alert():
    bus, seen = EventBus(), []
    bus.subscribe("system.*", seen.append)
    disabled = ProactiveMonitor(bus, MonitorConfig(enabled=False))
    disabled.evaluate_telemetry(_telemetry(ram=100))
    expected_off = ProactiveMonitor(bus, MonitorConfig(enabled=True, expect_tts=False))
    expected_off.evaluate_health({"checks": [
        {"key": "tts", "status": "warning", "value": "DISABLED"}]})
    assert seen == []


def test_expected_tts_failure_alerts_and_thresholds_are_normalized():
    cfg = MonitorConfig(enabled=True, expect_tts=True,
                        ram_warning=110, ram_critical=20)
    assert cfg.ram_warning == cfg.ram_critical == 100
    bus, seen = EventBus(), []
    bus.subscribe("system.warning", seen.append)
    monitor = ProactiveMonitor(bus, cfg)
    monitor.evaluate_health({"checks": [
        {"key": "tts", "status": "warning", "value": "DISABLED"}]})
    assert seen and seen[0].payload["key"] == "health.tts"


def test_panel_subscribes_to_warning_alert_and_recovery_events():
    html = __import__("pathlib").Path(
        "docs/mockups/jarvis-panel.html").read_text(encoding="utf-8")
    for name in ("system.warning", "system.alert", "system.recovered"):
        assert f'es.addEventListener("{name}"' in html


def test_panel_background_threads_stop_cleanly():
    import threading
    import time

    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore
    from jarvis.web.server import PanelServer

    agent = build_agent(Config(llm_provider="mock", non_interactive=True),
                        memory=MemoryStore(":memory:"))
    panel = PanelServer(
        agent, host="127.0.0.1", port=0,
        monitor_config=MonitorConfig(enabled=True, health_interval=15),
    )
    server_thread = threading.Thread(target=panel.serve_forever, daemon=True)
    server_thread.start()
    deadline = time.time() + 5
    while panel._httpd is None and time.time() < deadline:
        time.sleep(0.01)
    assert panel._httpd is not None
    panel.shutdown()
    server_thread.join(timeout=3)
    assert not server_thread.is_alive()
    assert panel._background_threads == []
