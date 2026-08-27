from __future__ import annotations

from ..agenda.store import AgendaError, AgendaStore
from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry


def register_agenda_tools(registry: ToolRegistry, store: AgendaStore) -> ToolRegistry:
    def ekle(baslik: str, tur: str, son_tarih: str, hatirlatma: str = "",
             notlar: str = "", vaka_no: int | None = None):
        try:
            item = store.create(baslik, tur, son_tarih, hatirlatma, notlar, vaka_no)
            return {"eklendi": True, "kayit": item.as_dict()}
        except (AgendaError, ValueError) as exc:
            return {"hata": str(exc)}

    def listele(durum: str = "acik"):
        try:
            items = store.list(durum)
            return {"adet": len(items), "kayitlar": [x.as_dict() for x in items]}
        except AgendaError as exc:
            return {"hata": str(exc)}

    def durum(kayit_no: int, yeni_durum: str):
        try:
            return {"guncellendi": True,
                    "kayit": store.set_status(int(kayit_no), yeni_durum).as_dict()}
        except (AgendaError, ValueError) as exc:
            return {"hata": str(exc)}

    registry.register(Tool("ajanda_ekle", "Görev, randevu veya teslim tarihi ekle.",
        RiskLevel.MEDIUM, ekle, [Param("baslik", "string", "Başlık", True),
        Param("tur", "string", "gorev | randevu | teslim", True),
        Param("son_tarih", "string", "ISO yerel tarih-saat", True),
        Param("hatirlatma", "string", "ISO hatırlatma zamanı"),
        Param("notlar", "string", "Notlar"), Param("vaka_no", "integer", "Bağlı vaka")]))
    registry.register(Tool("ajanda_listele", "Ajandadaki kayıtları listele.", RiskLevel.LOW,
        listele, [Param("durum", "string", "acik | tamamlandi | iptal | hepsi")]))
    registry.register(Tool("ajanda_durum", "Ajanda kaydını tamamla veya iptal et.",
        RiskLevel.MEDIUM, durum, [Param("kayit_no", "integer", "Kayıt numarası", True),
        Param("yeni_durum", "string", "tamamlandi | iptal", True)]))
    return registry
