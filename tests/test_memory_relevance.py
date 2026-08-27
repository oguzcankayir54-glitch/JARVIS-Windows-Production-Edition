from jarvis.memory.store import MemoryStore
from jarvis.core.intent_router import Intent


def test_unrelated_memory_is_not_injected_into_smalltalk():
    s = MemoryStore(":memory:")
    s.remember("anakart", "MSI B550-A PRO", "donanim")
    s.remember("kahve", "sütlü içer", "tercih")
    got = s.retrieve_relevant("Nasılsın Jarvis?", intent=Intent.CHAT.value)
    assert got == []


def test_relevant_technical_memory_is_selected():
    s = MemoryStore(":memory:")
    s.remember("anakart", "MSI B550-A PRO", "donanim")
    s.remember("kahve", "sütlü içer", "tercih")
    got = s.retrieve_relevant("anakart modelim neydi?", intent=Intent.CHAT.value)
    assert [f.key for f in got] == ["anakart"]


def test_broad_memory_recall_returns_profile_slice():
    s = MemoryStore(":memory:")
    s.remember("editor", "Cursor", "tercih")
    s.remember("proje", "Jarvis", "proje")
    got = s.retrieve_relevant("Benim hakkımda ne biliyorsun?",
                              intent=Intent.MEMORY_RECALL.value)
    assert {f.key for f in got} == {"editor", "proje"}


def test_standing_instruction_is_available_without_keyword_overlap():
    s = MemoryStore(":memory:")
    s.remember("cevap_kurali", "Yanıtları kısa tut", "kural")
    got = s.retrieve_relevant("Bugün nasılsın?", intent=Intent.CHAT.value)
    assert [f.key for f in got] == ["cevap_kurali"]


def test_merge_is_explicit_and_preserves_combined_content():
    s = MemoryStore(":memory:")
    s.remember("editor", "Cursor", "tercih")
    s.remember("tema", "koyu", "tercih")
    merged = s.merge_facts(["editor", "tema"], "calisma_tercihleri", category="tercih")
    assert "Cursor" in merged.value and "koyu" in merged.value
    keys = {f.key for f in s.all_facts()}
    assert "editor" not in keys
    assert "tema" not in keys
    assert "calisma_tercihleri" in keys
