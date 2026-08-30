"""Tool base, registry, manager dispatch, and system tools."""
from jarvis.security.audit import AuditLog
from jarvis.security.permissions import PermissionManager, RiskLevel
from jarvis.tools.base import Param, Tool, ToolRegistry
from jarvis.tools.manager import ToolManager
from jarvis.tools.system_tools import register_system_tools


def _manager(approver=None):
    registry = ToolRegistry()
    register_system_tools(registry)
    pm = PermissionManager(audit=AuditLog(), approver=approver, non_interactive=approver is None)
    return ToolManager(registry, pm), registry


def test_system_tools_registered():
    _, registry = _manager()
    names = {t.name for t in registry.all()}
    assert {"get_system_info", "get_cpu_temperature", "get_gpu_temperature",
            "get_ram_usage", "get_disk_health"} <= names


def test_low_risk_tool_runs():
    mgr, _ = _manager()
    res = mgr.dispatch("get_system_info")
    assert res.ok and "cpu_percent" in res.data


def test_gpu_tool_degrades_gracefully():
    # No NVIDIA GPU in CI/container: tool must succeed with available=False,
    # never raise.
    mgr, _ = _manager()
    res = mgr.dispatch("get_gpu_temperature")
    assert res.ok and res.data["available"] in (True, False)


def test_unknown_tool_is_rejected():
    mgr, _ = _manager()
    res = mgr.dispatch("rm_rf_everything")
    assert not res.ok and "bilinmeyen" in res.error
    assert res.error_type == "UNKNOWN_TOOL"


def test_tool_result_carries_duration_and_verification():
    registry = ToolRegistry()
    registry.register(Tool(
        name="verified", description="test", risk=RiskLevel.LOW,
        func=lambda: {"exists": False}, params=[],
        verifier=lambda data: bool(data.get("exists")),
    ))
    res = ToolManager(registry, PermissionManager(non_interactive=True)).dispatch("verified")
    assert not res.ok
    assert res.verified is False
    assert res.duration_ms >= 0
    assert res.error_type == "VERIFICATION_FAILED"


def test_unknown_param_rejected():
    reg = ToolRegistry()
    reg.register(Tool("noop", "test", RiskLevel.LOW, lambda: "ok", params=[]))
    pm = PermissionManager(audit=AuditLog())
    res = ToolManager(reg, pm).dispatch("noop", {"surprise": 1})
    assert not res.ok


def test_high_risk_tool_blocked_without_approval():
    reg = ToolRegistry()
    reg.register(Tool("set_cfg", "değiştir", RiskLevel.HIGH, lambda **k: "done",
                      params=[Param("key", required=True)]))
    pm = PermissionManager(audit=AuditLog(), approver=lambda *a: False)
    res = ToolManager(reg, pm).dispatch("set_cfg", {"key": "x"})
    assert not res.ok and "İzin reddedildi" in res.error


def test_tool_schema_shape():
    reg = ToolRegistry()
    reg.register(Tool("t", "desc", RiskLevel.LOW, lambda: 1, params=[Param("a", "integer", "n", True)]))
    schema = reg.schemas()[0]
    assert schema["function"]["name"] == "t"
    assert schema["function"]["parameters"]["required"] == ["a"]


def test_windows_adapters_are_registered_and_honest_on_linux():
    from jarvis.tools.windows_tools import register_windows_tools
    reg = ToolRegistry()
    register_windows_tools(reg)
    names = {tool.name for tool in reg.all()}
    assert {"windows_system", "windows_process", "windows_network",
            "windows_service", "windows_window", "windows_audio",
            "windows_power", "windows_input"} <= names
    result = ToolManager(reg, PermissionManager(non_interactive=True)).dispatch("windows_service", {"name": "ollama"})
    assert result.ok and result.data["available"] is False


def test_windows_service_tolerates_legacy_console_bytes(monkeypatch):
    from types import SimpleNamespace

    from jarvis.tools import windows_tools

    options = {}

    def fake_run(*args, **kwargs):
        options.update(kwargs)
        return SimpleNamespace(returncode=1, stdout="", stderr="bozuk \ufffd çıktı")

    monkeypatch.setattr(windows_tools.platform, "system", lambda: "Windows")
    monkeypatch.setattr(windows_tools.subprocess, "run", fake_run)

    result = windows_tools.windows_service("ollama")

    assert options["errors"] == "replace"
    assert result["available"] is False
