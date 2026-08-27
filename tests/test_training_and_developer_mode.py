from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.intent_router import Intent
from jarvis.memory.store import MemoryStore
from jarvis.core.owner import Owner


def _agent(owner=True):
    s = MemoryStore(":memory:")
    if owner:
        s.set_owner(Owner(name="Oğuz", role="tasarımcısı ve geliştiricisi",
                          address_forms=["Efendim"]))
    a = build_agent(Config(llm_provider="mock", non_interactive=True), memory=s)
    if not owner:
        s.clear_owner()
        a.reload_owner()
    return a


def test_training_start_is_stateful_and_does_not_call_rag():
    a = _agent()
    out = a.ask("Eğitim süreci 1.")
    assert a.training_active is True
    assert "başlatıldı" in out


def test_plain_statement_becomes_memory_save_while_training():
    a = _agent()
    a.ask("Eğitim süreci 1.")
    a.ask("Ben kahve içerken daha iyi çalışıyorum.")
    assert a.last_intent.intent is Intent.MEMORY_SAVE
    assert a.last_intent.subtype == "TRAINING_DATA"
    names = {a._sema_adi(s) for s in a._intent_schemas(
        a.registry.schemas(), a.last_intent, "Ben kahve içerken daha iyi çalışıyorum.")}
    assert "remember_fact" in names
    assert "bilgi_ara" not in names


def test_training_can_be_stopped():
    a = _agent()
    a.ask("Eğitim süreci 1.")
    a.ask("Eğitimi bitir.")
    assert a.training_active is False


def test_developer_mode_requires_registered_developer():
    a = _agent(owner=False)
    out = a.ask("Jarvis debug moduna geç.")
    assert a.debug_mode is False
    assert "yalnızca kayıtlı" in out


def test_registered_developer_can_enable_and_disable_debug():
    a = _agent(owner=True)
    assert "aktif" in a.ask("Jarvis debug moduna geç.")
    assert a.debug_mode is True
    assert "kapatıldı" in a.ask("debug modundan çık")
    assert a.debug_mode is False


def test_debug_still_redacts_secrets():
    a = _agent(owner=True)
    a.ask("debug moduna geç")
    raw = a.response_engine.render("api_key=sk-1234567890ABCDEFGHIJK", intent=Intent.CHAT,
                                   user_text="debug", debug=True)
    assert "sk-123" not in raw
    assert "[SECRET]" in raw
