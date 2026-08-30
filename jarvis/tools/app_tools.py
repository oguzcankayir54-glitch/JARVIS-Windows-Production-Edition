"""The "aç" tool — one verb that covers everything the owner opens.

The design goal was stated plainly: *"komutları bu kadar zor öğrenmesin."*
So there is one tool, it takes a name in ordinary Turkish, and the matching is
forgiving. "YouTube aç", "hesap makinesi aç", "ayarları aç" all land here.

Risk is MEDIUM, the same as opening a browser: it starts a program on the
owner's desktop. Visible, reversible, and gated — but still J.A.R.V.I.S.
launching something, so it goes through the permission layer.

What it will not do is take a path. The catalogue is an allowlist (see
:mod:`jarvis.apps.katalog` for why), so a request to open something unknown
comes back as "bilmiyorum" with suggestions, never as a guess at an
executable.
"""
from __future__ import annotations

from typing import Any

from ..apps.ac import uygulamayi_ac
from ..apps.katalog import benzerler, bul, katalog, kullanici_katalogu
from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry


def register_app_tools(registry: ToolRegistry, data_dir: str = "~/.jarvis") -> ToolRegistry:

    def uygulama_ac(ad: str) -> dict[str, Any]:
        istek = (ad or "").strip()
        if not istek:
            return {"hata": "Hangi uygulamayı açacağımı söylemediniz."}

        uygulama = bul(istek, data_dir)
        if uygulama is None:
            oneriler = benzerler(istek, data_dir=data_dir)
            return {
                "hata": f"'{istek}' listemde yok.",
                "oneriler": oneriler,
                "not": ("Uydurma bir program adı deneme. Kullanıcı listede "
                        "olmayan bir uygulama istiyorsa "
                        f"{kullanici_katalogu(data_dir)} dosyasına "
                        "ekleyebileceğini söyle."),
            }

        # Launch failures must escape to Tool.run so they become an actual
        # failed ToolResult.  Otherwise the model sees a successful tool call
        # containing an error-shaped payload and may still claim it opened.
        acilan = uygulamayi_ac(uygulama)
        return {"acildi": True, "uygulama": uygulama.ad,
                "tur": uygulama.tur, "hedef": acilan,
                "user_message": f"{uygulama.ad} açıldı."}

    def uygulama_listesi(filtre: str = "") -> dict[str, Any]:
        liste = katalog(data_dir)
        if filtre.strip():
            eslesenler = benzerler(filtre, adet=20, data_dir=data_dir)
            liste = [u for u in liste if u.ad in eslesenler]
        return {
            "adet": len(liste),
            "uygulamalar": [{"ad": u.ad, "tur": u.tur} for u in liste],
            "ekleme_dosyasi": str(kullanici_katalogu(data_dir)),
        }

    registry.register(Tool(
        name="uygulama_ac",
        description=(
            "Kullanıcının bilgisayarında bir uygulama veya siteyi AÇ. "
            "'YouTube aç', 'hesap makinesi aç', 'ayarları aç', 'not defterini "
            "aç', 'görev yöneticisini aç' gibi her isteğe bu araçla cevap ver. "
            "Adı kullanıcının söylediği gibi ver — eşleştirmeyi araç yapar. "
            "Listede olmayan bir ad için tahmin yürütme; araç öneri döndürür."
        ),
        risk=RiskLevel.MEDIUM, func=uygulama_ac,
        params=[Param("ad", "string", "Açılacak uygulama/site adı", required=True)]))

    registry.register(Tool(
        name="uygulama_listesi",
        description=(
            "Açabildiğin uygulama ve siteleri listele. Kullanıcı 'neleri "
            "açabilirsin', 'hangi uygulamaları biliyorsun' diye sorduğunda "
            "kullan."
        ),
        risk=RiskLevel.LOW, func=uygulama_listesi,
        params=[Param("filtre", "string", "İsteğe bağlı arama sözcüğü")]))

    return registry
