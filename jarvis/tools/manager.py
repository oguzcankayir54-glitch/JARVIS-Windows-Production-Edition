"""Tool Manager — the single choke point between the agent and the system.

    LLM → Agent → ToolManager → PermissionLayer → OS

The manager looks a tool up by name, runs it through the
:class:`PermissionManager`, executes it only if allowed, and records the
outcome in the audit log. The LLM never calls a tool directly.
"""
from __future__ import annotations

from typing import Any

from ..security.audit import AuditEntry
from ..security.permissions import PermissionManager
from .base import ToolRegistry, ToolResult


class ToolManager:
    def __init__(self, registry: ToolRegistry, permissions: PermissionManager) -> None:
        self.registry = registry
        self.permissions = permissions

    def dispatch(self, name: str, args: dict[str, Any] | None = None) -> ToolResult:
        args = args or {}
        tool = self.registry.get(name)
        if tool is None:
            return ToolResult(ok=False, verified=False, error_type="UNKNOWN_TOOL",
                              error=f"bilinmeyen tool: {name}")

        # Risk is resolved per call: a shell tool is only as dangerous as the
        # command it was handed.
        risk = tool.effective_risk(args)

        # Policy refusals come first and are absolute: a call the tool forbids
        # outright is never offered for approval, so no amount of user consent
        # can unlock it.
        refusal = tool.refusal(args)
        if refusal is not None:
            self.permissions.audit.record(
                AuditEntry(tool=name, risk=risk.label, decision="refused", args=args, detail=refusal)
            )
            return ToolResult(ok=False, verified=False, error_type="POLICY_REFUSED",
                              error=f"Reddedildi (politika): {refusal}")

        # check() writes its own audit entry for the decision it makes.
        decision = self.permissions.check(tool.name, risk, args, tool.description)
        if not decision.allowed:
            return ToolResult(ok=False, verified=False, error_type="PERMISSION_DENIED",
                              error=f"İzin reddedildi: {decision.reason}")

        result = tool.run(**args)
        if not result.ok:
            self.permissions.audit.record(
                AuditEntry(tool=name, risk=risk.label, decision="error", args=args, detail=result.error)
            )
        return result
