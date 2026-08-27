"""Tools that expose guided diagnostic playbooks to the agent."""
from __future__ import annotations

from ..diagnostics import DiagnosticEngine, DiagnosticError
from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry


def register_diagnostic_tools(registry: ToolRegistry,
                              engine: DiagnosticEngine) -> ToolRegistry:
    def teshis_playbooklari() -> dict:
        items = engine.list_playbooks()
        return {"adet": len(items), "playbooklar": items}

    def teshis_baslat(vaka_no: int, playbook: str) -> dict:
        try:
            return engine.start(int(vaka_no), playbook)
        except (DiagnosticError, ValueError) as exc:
            return {"hata": str(exc)}

    def teshis_yanitla(oturum_no: int, secenek: str) -> dict:
        try:
            return engine.answer(int(oturum_no), secenek)
        except (DiagnosticError, ValueError) as exc:
            return {"hata": str(exc)}

    registry.register(Tool(
        name="teshis_playbooklari",
        description="Kullanılabilen yönlendirmeli teknik teşhis playbook'larını listele.",
        risk=RiskLevel.LOW, func=teshis_playbooklari, params=[]))
    registry.register(Tool(
        name="teshis_baslat",
        description=("Mevcut bir servis vakasında yönlendirmeli teşhis başlat. "
                     "Genel teknik soruda değil, kullanıcı vaka numarası verdiğinde kullan."),
        risk=RiskLevel.MEDIUM, func=teshis_baslat,
        params=[Param("vaka_no", "integer", "Açık servis vakası", required=True),
                Param("playbook", "string", "Playbook kimliği", required=True)]))
    registry.register(Tool(
        name="teshis_yanitla",
        description=("Aktif teşhis oturumunda teknisyenin doğruladığı seçeneği kaydet "
                     "ve güvenli sıradaki adıma ilerle."),
        risk=RiskLevel.MEDIUM, func=teshis_yanitla,
        params=[Param("oturum_no", "integer", "Teşhis oturum numarası", required=True),
                Param("secenek", "string", "Sunulan seçenek kimliği", required=True)]))
    return registry
