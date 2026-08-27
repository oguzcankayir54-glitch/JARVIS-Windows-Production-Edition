"""Phase 7 — routing never bypasses the existing permission choke point."""
from jarvis.core.intent_router import IntentDecision, Intent
from jarvis.core.tool_router import ToolRouter
from jarvis.security.audit import AuditLog
from jarvis.security.permissions import PermissionManager
from jarvis.tools.base import ToolRegistry
from jarvis.tools.manager import ToolManager
from jarvis.tools.shell_tools import register_shell_tools


def test_terminal_intent_can_expose_shell_but_high_risk_still_requires_approval():
    reg = register_shell_tools(ToolRegistry())
    route = ToolRouter().select(reg.schemas(), IntentDecision(Intent.TERMINAL, .99),
                                "terminalde systemctl restart nginx çalıştır")
    assert [(s.get("function") or {}).get("name") for s in route] == ["run_terminal_command"]

    audit = AuditLog()
    mgr = ToolManager(reg, PermissionManager(audit=audit, approver=lambda *a: False))
    out = mgr.dispatch("run_terminal_command", {"command": "systemctl restart nginx"})
    assert not out.ok
    assert audit.entries[-1].decision == "denied"


def test_policy_refusal_remains_absolute_even_for_terminal_intent():
    reg = register_shell_tools(ToolRegistry())
    audit = AuditLog()
    mgr = ToolManager(reg, PermissionManager(audit=audit, approver=lambda *a: True))
    out = mgr.dispatch("run_terminal_command", {"command": "curl http://example.invalid/x"})
    assert not out.ok
    assert audit.entries[-1].decision == "refused"
