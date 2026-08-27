"""Tool abstraction: a typed, schema-described unit of capability.

Tools are the *only* way the agent touches the system. Each tool carries a
fixed :class:`RiskLevel` and a JSON-schema-ish parameter description used both
for validation and for advertising the tool to an LLM.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable
import time

from ..security.permissions import RiskLevel


@dataclass
class ToolResult:
    ok: bool
    data: Any = None
    error: str = ""
    duration_ms: float = 0.0
    error_type: str = ""
    verified: bool | None = None

    def as_text(self) -> str:
        if self.ok:
            return str(self.data)
        return f"HATA: {self.error}"


@dataclass
class Param:
    name: str
    type: str = "string"        # string | number | integer | boolean
    description: str = ""
    required: bool = False


@dataclass
class Tool:
    name: str
    description: str
    risk: RiskLevel
    func: Callable[..., Any]
    params: list[Param] = field(default_factory=list)
    #: Optional argument-aware risk classifier. Some tools (a shell runner) are
    #: only as dangerous as what they are asked to do, so the effective risk is
    #: computed per call. See :meth:`effective_risk` for the safety invariant.
    risk_for: Callable[[dict[str, Any]], RiskLevel] | None = None
    #: Optional policy gate returning a refusal reason, or None to proceed.
    #: A refusal here is absolute: the call is rejected *before* the permission
    #: layer, so it is never offered to the user for approval. Approval must
    #: never be able to unlock something policy forbids outright.
    precheck: Callable[[dict[str, Any]], str | None] | None = None
    verifier: Callable[[Any], bool] | None = None

    def refusal(self, args: dict[str, Any]) -> str | None:
        """Policy reason this call must not run at all, if any."""
        if self.precheck is None:
            return None
        try:
            return self.precheck(args)
        except Exception as exc:
            return f"Ön kontrol başarısız: {exc}"

    def effective_risk(self, args: dict[str, Any]) -> RiskLevel:
        """Risk for one specific call.

        A classifier may only *raise* the risk above the declared level, never
        lower it: ``risk`` stays the floor. That way a buggy or manipulated
        classifier can never downgrade a dangerous tool below its declaration.
        """
        if self.risk_for is None:
            return self.risk
        try:
            computed = self.risk_for(args)
        except Exception:
            # A classifier that cannot decide must fail closed, not open.
            return RiskLevel.CRITICAL
        return max(self.risk, computed)

    def run(self, **kwargs: Any) -> ToolResult:
        started = time.perf_counter()
        try:
            self._validate(kwargs)
            data = self.func(**kwargs)
            result = ToolResult(ok=True, data=data, verified=True)
            if self.verifier is not None:
                try:
                    result.verified = bool(self.verifier(data))
                except Exception as exc:
                    result.ok = False
                    result.verified = False
                    result.error_type = "VERIFICATION_FAILED"
                    result.error = f"Doğrulama başarısız: {exc}"
                if not result.verified and result.ok:
                    result.ok = False
                    result.error_type = "VERIFICATION_FAILED"
                    result.error = "Araç sonucu beklenen durumu doğrulamadı."
            result.duration_ms = round((time.perf_counter() - started) * 1000, 3)
            return result
        except Exception as exc:  # surfaced to the agent, never crashes it
            return ToolResult(ok=False, verified=False,
                              error_type=type(exc).__name__.upper(),
                              error=f"{type(exc).__name__}: {exc}",
                              duration_ms=round((time.perf_counter() - started) * 1000, 3))

    def _validate(self, kwargs: dict[str, Any]) -> None:
        allowed = {p.name for p in self.params}
        for key in kwargs:
            if key not in allowed:
                raise ValueError(f"bilinmeyen parametre: {key}")
        for p in self.params:
            if p.required and kwargs.get(p.name) in (None, ""):
                raise ValueError(f"zorunlu parametre eksik: {p.name}")

    def to_schema(self) -> dict[str, Any]:
        """OpenAI/Ollama-style function schema for tool advertising."""
        properties: dict[str, Any] = {}
        required: list[str] = []
        for p in self.params:
            properties[p.name] = {"type": p.type, "description": p.description}
            if p.required:
                required.append(p.name)
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": f"[{self.risk.label}] {self.description}",
                "parameters": {"type": "object", "properties": properties, "required": required},
            },
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> Tool:
        if tool.name in self._tools:
            raise ValueError(f"tool zaten kayıtlı: {tool.name}")
        self._tools[tool.name] = tool
        return tool

    def get(self, name: str) -> Tool | None:
        return self._tools.get(name)

    def all(self) -> list[Tool]:
        return list(self._tools.values())

    def schemas(self) -> list[dict[str, Any]]:
        return [t.to_schema() for t in self._tools.values()]
