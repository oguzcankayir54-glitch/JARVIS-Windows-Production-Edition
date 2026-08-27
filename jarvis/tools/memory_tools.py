"""Memory tools — the controlled way facts enter and leave long-term storage.

Reading memory is harmless (LOW). Writing and deleting change durable state,
so they are MEDIUM: allowed without a prompt but always audited, and never a
silent side effect of conversation — the model has to ask for them explicitly.
"""
from __future__ import annotations

from typing import Any

from ..memory.onem import Kaynak
from ..memory.store import MemoryStore
from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry


def register_memory_tools(registry: ToolRegistry, store: MemoryStore) -> ToolRegistry:
    def remember_fact(key: str, value: str, category: str = "genel",
                      onemli: bool = False,
                      cikarim: bool = False) -> dict[str, Any]:
        kaynak = Kaynak.CIKARIM.value if cikarim else Kaynak.KULLANICI.value
        onceki = store.recall(key, kullanim_say=False)
        fact = store.remember(key, value, category, source=kaynak, israr=onemli)

        # Yazma REDDEDILMIS olabilir: bir cikarim, kullanicinin acikca
        # soyledigi bir seyin ustune yazamiyor. Bunu "kaydedildi: True"
        # diye bildirmek modele yalan soylemek olurdu — ve model
        # kullaniciya "kaydettim" derdi.
        yazildi = fact.value == value
        cevap: dict[str, Any] = {
            "kaydedildi": yazildi, "key": fact.key, "value": fact.value,
            "category": fact.category, "onem": fact.onem.etiket,
        }
        if not yazildi:
            cevap["not"] = (
                f"Yazılmadı: '{key}' için kullanıcının kendi söylediği "
                f"'{fact.value}' kayıtlı ve bu bir çıkarımla değiştirilemez. "
                "Değişmesi gerekiyorsa kullanıcıya sor."
            )
        elif onceki and onceki[0].value != value:
            cevap["onceki_deger"] = onceki[0].value
        return cevap

    def recall_facts(query: str = "", category: str = "") -> dict[str, Any]:
        facts = store.recall(query=query, category=category)
        return {
            "adet": len(facts),
            "sonuclar": [{"key": f.key, "value": f.value, "category": f.category,
                          "onem": f.onem.etiket} for f in facts],
        }

    def forget_fact(key: str) -> dict[str, Any]:
        removed = store.forget(key)
        return {"silindi": removed, "key": key}

    registry.register(Tool(
        name="remember_fact",
        description="Önemli bir bilgiyi kalıcı hafızaya kaydet (anahtar + değer).",
        risk=RiskLevel.MEDIUM, func=remember_fact,
        params=[
            Param("key", "string", "Kısa anahtar, ör. 'tercih_editor'", required=True),
            Param("value", "string", "Hatırlanacak bilgi", required=True),
            Param("category", "string", "Kategori, ör. 'kullanici' | 'donanim' | 'genel'"),
            Param("onemli", "boolean",
                  "Kullanıcı 'bunu hatırla', 'unutma', 'her zaman böyle yap' "
                  "gibi AÇIKÇA ısrar ettiyse true. Kendi kararınla true yapma."),
            Param("cikarim", "boolean",
                  "Bilgiyi kullanıcı söylemedi, sen konuşmadan çıkardıysan "
                  "true. Çıkarım, kullanıcının kendi söylediğinin üstüne "
                  "yazamaz — dürüst işaretle, yoksa hafıza zamanla tahmine "
                  "dönüşür."),
        ]))

    registry.register(Tool(
        name="recall_facts",
        description="Kalıcı hafızada kayıtlı bilgileri ara.",
        risk=RiskLevel.LOW, func=recall_facts,
        params=[
            Param("query", "string", "Aranacak kelime (boş bırakılırsa hepsi)"),
            Param("category", "string", "Kategoriye göre filtrele"),
        ]))

    registry.register(Tool(
        name="forget_fact",
        description="Kalıcı hafızadan bir bilgiyi sil.",
        risk=RiskLevel.MEDIUM, func=forget_fact,
        params=[Param("key", "string", "Silinecek anahtar", required=True)]))

    return registry
