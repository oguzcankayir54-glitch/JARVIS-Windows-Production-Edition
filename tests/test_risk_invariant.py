"""The dynamic-risk safety invariant.

A per-call classifier may raise a tool's risk but must never lower it below the
level the tool declares. If that invariant broke, a manipulated or buggy
classifier could quietly turn a CRITICAL action into an auto-allowed one.
"""
from jarvis.security.permissions import RiskLevel
from jarvis.tools.base import Tool


def _tool(declared, classifier):
    return Tool("t", "test", declared, lambda **k: "ok", params=[], risk_for=classifier)


def test_classifier_can_raise_risk():
    t = _tool(RiskLevel.MEDIUM, lambda args: RiskLevel.CRITICAL)
    assert t.effective_risk({}) is RiskLevel.CRITICAL


def test_classifier_cannot_lower_below_declared_floor():
    t = _tool(RiskLevel.HIGH, lambda args: RiskLevel.LOW)
    assert t.effective_risk({}) is RiskLevel.HIGH


def test_classifier_failure_fails_closed():
    def boom(args):
        raise RuntimeError("sınıflandırıcı çöktü")

    t = _tool(RiskLevel.LOW, boom)
    assert t.effective_risk({}) is RiskLevel.CRITICAL


def test_tool_without_classifier_uses_declared_risk():
    t = Tool("t", "test", RiskLevel.MEDIUM, lambda **k: "ok", params=[])
    assert t.effective_risk({}) is RiskLevel.MEDIUM
