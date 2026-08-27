"""Service log tools — how a case gets opened, followed and closed.

Risk follows the same rule as memory: reading is LOW, writing durable state
is MEDIUM. Nothing here touches the operating system, but a case record is
work history — it should never appear as a silent side effect of chatting,
so the model has to ask for each write explicitly and every one is audited.

The wording of the descriptions matters more than usual: these are the only
hint the model gets about *when* to open a case rather than just answer. They
say it plainly, because a model that opens a case for every question is worse
than one that never does.
"""
from __future__ import annotations

from typing import Any

from ..memory.cases import CaseError, CaseStore
from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry


def _hata(exc: CaseError) -> dict[str, Any]:
    """A refusal the model can read and act on, not a stack trace."""
    return {"hata": str(exc)}


def register_case_tools(registry: ToolRegistry, store: CaseStore) -> ToolRegistry:

    def vaka_ac(musteri: str, cihaz: str, belirti: str) -> dict[str, Any]:
        try:
            vaka = store.open_case(musteri, cihaz, belirti)
        except CaseError as exc:
            return _hata(exc)
        return {"acildi": True, "vaka_no": vaka.id, "musteri": vaka.customer,
                "cihaz": vaka.device, "belirti": vaka.symptom}

    def vaka_notu_ekle(vaka_no: int, not_metni: str, tur: str = "gozlem") -> dict[str, Any]:
        try:
            kayit = store.add_note(int(vaka_no), not_metni, tur)
        except CaseError as exc:
            return _hata(exc)
        return {"eklendi": True, "vaka_no": kayit.case_id, "not_no": kayit.id, "tur": kayit.kind}

    def vaka_kapat(vaka_no: int, sonuc: str) -> dict[str, Any]:
        try:
            vaka = store.close_case(int(vaka_no), sonuc)
        except CaseError as exc:
            return _hata(exc)
        return {"kapatildi": True, "vaka_no": vaka.id, "sonuc": vaka.resolution}

    def acik_vakalar() -> dict[str, Any]:
        vakalar = store.open_cases()
        return {
            "adet": len(vakalar),
            "vakalar": [
                {"vaka_no": v.id, "musteri": v.customer, "cihaz": v.device,
                 "belirti": v.symptom, "durum": v.status, "ozet": v.as_line()}
                for v in vakalar
            ],
        }

    def vaka_detay(vaka_no: int) -> dict[str, Any]:
        vaka = store.get_case(int(vaka_no), with_notes=True)
        if vaka is None:
            return {"hata": f"#{vaka_no} numaralı vaka yok."}
        return {
            "vaka_no": vaka.id, "musteri": vaka.customer, "cihaz": vaka.device,
            "belirti": vaka.symptom, "durum": vaka.status, "sonuc": vaka.resolution,
            "notlar": [{"tur": n.kind, "metin": n.text} for n in vaka.notes],
        }

    registry.register(Tool(
        name="vaka_ac",
        description=(
            "Servise yeni gelen bir cihaz için vaka kaydı aç. YALNIZCA kullanıcı "
            "gerçekten bir cihazın servise geldiğini söylediğinde kullan — genel "
            "teknik sorular için vaka açma."
        ),
        risk=RiskLevel.MEDIUM, func=vaka_ac,
        params=[
            Param("musteri", "string", "Müşteri adı", required=True),
            Param("cihaz", "string", "Cihaz, ör. 'Lenovo V15 laptop'", required=True),
            Param("belirti", "string", "Şikâyet, müşterinin anlattığı hâliyle", required=True),
        ]))

    registry.register(Tool(
        name="vaka_notu_ekle",
        description=(
            "Açık bir vakaya not ekle: gözlem, denenen işlem veya ara sonuç. "
            "Teşhis ilerledikçe eklenmeli — sonradan 'ne denemiştik' sorusunun cevabı budur."
        ),
        risk=RiskLevel.MEDIUM, func=vaka_notu_ekle,
        params=[
            Param("vaka_no", "integer", "Vaka numarası", required=True),
            Param("not_metni", "string", "Notun kendisi", required=True),
            Param("tur", "string", "'gozlem' | 'deneme' | 'sonuc'"),
        ]))

    registry.register(Tool(
        name="vaka_kapat",
        description=(
            "Vakayı kapat. Sonuç alanına arızanın NE ÇIKTIĞINI yaz — 'düzeldi' gibi "
            "bir cevap aynı belirti bir yıl sonra geldiğinde hiçbir işe yaramaz."
        ),
        risk=RiskLevel.MEDIUM, func=vaka_kapat,
        params=[
            Param("vaka_no", "integer", "Vaka numarası", required=True),
            Param("sonuc", "string", "Arıza neydi, ne yapıldı", required=True),
        ]))

    def vaka_ara(belirti: str) -> dict[str, Any]:
        sonuclar = store.search(belirti)
        return {
            "adet": len(sonuclar),
            "sorgu": belirti,
            "sonuclar": [
                {"vaka_no": v.id, "cihaz": v.device, "belirti": v.symptom,
                 "durum": v.status, "cikan": v.resolution or "(henüz belli değil)",
                 "eslesen_kelime": puan}
                for v, puan in sonuclar
            ],
            "not": "Kelime eşleşmesi — anlam araması değil. Sonuçları teyit et.",
        }

    registry.register(Tool(
        name="vaka_ara",
        description=(
            "Geçmiş vakalarda benzer belirtiyi ara ve NE ÇIKTIĞINI getir. "
            "Bir arıza teşhis ederken önce buna bak: aynı belirti daha önce "
            "görüldüyse sonucu en kıymetli ipucudur."
        ),
        risk=RiskLevel.LOW, func=vaka_ara,
        params=[Param("belirti", "string", "Aranacak belirti/ifade", required=True)]))

    registry.register(Tool(
        name="acik_vakalar",
        description="Serviste bekleyen açık vakaları listele (en eskisi başta).",
        risk=RiskLevel.LOW, func=acik_vakalar, params=[]))

    registry.register(Tool(
        name="vaka_detay",
        description="Bir vakanın tüm notlarıyla birlikte ayrıntısını getir.",
        risk=RiskLevel.LOW, func=vaka_detay,
        params=[Param("vaka_no", "integer", "Vaka numarası", required=True)]))

    return registry
