from types import SimpleNamespace

import pytest

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.maintenance_commands import command_catalog, run_maintenance
from jarvis.diagnostics.health import collect_health
from jarvis.memory.store import MemoryStore
from jarvis.web.server import PanelServer


def _agent():
    return build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))


def test_health_report_contains_measured_components_and_score():
    agent = _agent()
    ready = SimpleNamespace(available=True, name="stub")
    report = collect_health(
        agent, tts=ready, stt=ready, check_dependencies=False,
        gpu_probe=lambda: {"available": True, "name": "Test GPU",
                           "vram_used_mb": 1024, "vram_total_mb": 4096},
    )
    keys = {item["key"] for item in report["checks"]}
    assert {"core", "cpu", "ram", "disk", "ollama", "model", "gpu", "cuda", "vram", "python",
            "venv", "dependencies", "stt", "tts", "microphone",
            "working_memory", "long_memory", "vector_backend", "tools"} <= keys
    assert 0 <= report["score"] <= 100
    assert report["status"] in {"OPERATIONAL", "DEGRADED", "CRITICAL"}
    assert set(report["categories"]) == {
        "Core", "LLM", "GPU", "Voice", "Memory", "Tools", "Dependencies"}


def test_unknown_gpu_and_client_microphone_are_not_invented_as_ready():
    report = collect_health(
        _agent(), check_dependencies=False,
        gpu_probe=lambda: {"available": False, "note": "not detected"},
    )
    checks = {item["key"]: item for item in report["checks"]}
    assert checks["gpu"]["status"] == "unknown"
    assert checks["microphone"]["status"] == "unknown"


def test_required_ollama_failure_makes_overall_health_critical(monkeypatch):
    agent = _agent()
    agent.llm.name = "ollama"
    agent.llm.model = "qwen2.5:14b"
    agent.llm.host = "http://127.0.0.1:1"
    monkeypatch.setattr(
        "urllib.request.urlopen",
        lambda *a, **k: (_ for _ in ()).throw(OSError("offline")),
    )
    report = collect_health(agent, check_dependencies=False,
                            gpu_probe=lambda: {"available": False})
    assert report["status"] == "CRITICAL"
    ollama = next(x for x in report["checks"] if x["key"] == "ollama")
    assert ollama["value"].startswith("OFFLINE")


def test_command_catalog_is_platform_specific_and_marks_risky_commands():
    linux = command_catalog("Linux")
    windows = command_catalog("Windows")
    assert any(x.command == "which python" for x in linux)
    assert not any("systemctl" in x.command for x in windows)
    risky = [x for x in linux if "sudo" in x.command or "tail -f" in x.command]
    assert risky and all(not x.run_allowed and not x.argv for x in risky)


def test_runner_accepts_id_only_and_never_uses_shell(monkeypatch):
    captured = {}

    def fake_run(argv, **kwargs):
        captured.update({"argv": argv, **kwargs})
        return SimpleNamespace(returncode=0, stdout="Python 3.11", stderr="")

    monkeypatch.setattr("subprocess.run", fake_run)
    result = run_maintenance("python_version", system="Linux")
    assert result["ok"] is True and result["stdout"] == "Python 3.11"
    assert captured["shell"] is False
    assert isinstance(captured["argv"], tuple)
    with pytest.raises(ValueError):
        run_maintenance("python_version; rm -rf /tmp/x", system="Linux")
    with pytest.raises(PermissionError):
        run_maintenance("ollama_restart", system="Linux")


def test_panel_health_and_maintenance_views_expose_structured_data(monkeypatch):
    panel = PanelServer(_agent())
    report = {"score": 96, "status": "OPERATIONAL", "checked_at": 1.0,
              "categories": {"Core": {"score": 100, "status": "OPERATIONAL"}},
              "checks": [{"label": "JARVİS CORE", "value": "RUNNING",
                          "status": "ready", "category": "Core"}]}
    monkeypatch.setattr(panel, "health_report", lambda refresh=False: report)
    health = panel.modul_verisi()["saglik"]
    assert health["score"] == 96 and health["status"] == "OPERATIONAL"
    commands = panel.modul_verisi()["komutlar"]["satirlar"]
    maintenance = [row for row in commands if row.get("bakim")]
    assert maintenance and all("run_allowed" in row for row in maintenance)
    panel.shutdown()


def test_panel_html_contains_refresh_copy_run_and_output_views():
    html = __import__("pathlib").Path(
        "docs/mockups/jarvis-panel.html").read_text(encoding="utf-8")
    assert "REFRESH HEALTH" in html
    assert 'fetch("/health/refresh"' in html
    assert 'fetch("/maintenance/run"' in html
    assert 'copy.textContent="COPY"' in html
    assert "STDOUT" in html and "STDERR" in html
