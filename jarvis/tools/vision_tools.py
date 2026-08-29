"""Explicit screenshot analysis tool backed by the common vision pipeline."""
from __future__ import annotations

from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry


def register_vision_tools(registry: ToolRegistry, pipeline) -> ToolRegistry:
    if registry.get("masaustu_analiz") is not None:
        return registry

    def masaustu_analiz(gorev: str = "ocr") -> dict:
        tasks = [x.strip() for x in (gorev or "ocr").split(",") if x.strip()]
        return pipeline.capture_and_submit(tasks).result(timeout=120).as_dict()

    registry.register(Tool(
        name="masaustu_analiz",
        description=("Kullanıcının açık onayıyla mevcut masaüstünün ekran görüntüsünü "
                     "yerel olarak analiz et; görüntüyü diske kaydetmez."),
        risk=RiskLevel.HIGH,
        func=masaustu_analiz,
        params=[Param("gorev", "string", "ocr | objects | faces; virgülle ayrılabilir")],
    ))
    return registry
