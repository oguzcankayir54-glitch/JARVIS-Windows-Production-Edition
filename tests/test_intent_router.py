"""Phase 2 — intent contract from the J.A.R.V.I.S. 2.0 refactor spec."""
import pytest

from jarvis.core.intent_router import Intent, IntentRouter
from jarvis.security.permissions import RiskLevel


@pytest.mark.parametrize("text, expected", [
    ("Ben senin geliştiricinim.", Intent.MEMORY_SAVE),
    ("Eğitim süreci 1.", Intent.TRAINING),
    ("Nasılsın Jarvis?", Intent.CHAT),
    ("Bugün ne yapabiliriz?", Intent.CHAT),
    ("Geçen gün sana ne öğretmiştim?", Intent.MEMORY_RECALL),
    ("Benim hakkımda neler biliyorsun?", Intent.MEMORY_RECALL),
    ("Jarvis klasöründeki authentication kodunu incele.", Intent.CODING),
    ("GitHub'daki son commit'e bak.", Intent.GITHUB),
    ("Chrome'u aç.", Intent.COMPUTER_CONTROL),
    ("CPU neden bu kadar yüksek?", Intent.SYSTEM_MONITOR),
    ("Bu PDF'de authentication nasıl çalışıyor?", Intent.RAG_QUERY),
    ("İnternette Qwen 2.5 14B'nin son sürümünü araştır.", Intent.WEB_RESEARCH),
    ("Bugün biraz yoruldum.", Intent.CHAT),
    ("RAG ne?", Intent.CHAT),
])
def test_spec_examples_route_correctly(text, expected):
    got = IntentRouter().route(text)
    assert got.intent is expected, got


@pytest.mark.parametrize("text", [
    "Şu Python hatasını açıklayıp düzelt: def ilk(xs): return xs[0].",
    "Bu JavaScript fonksiyonunda neden bug var, incele.",
    "Traceback veren metodu debug edip iyileştir.",
])
def test_natural_coding_requests_route_to_coder(text):
    assert IntentRouter().route(text).intent is Intent.CODING


@pytest.mark.parametrize("text", [
    "Bu hata neden oluyor?",
    "Python nedir?",
    "Fonksiyon nedir?",
])
def test_generic_error_and_concept_questions_stay_chat(text):
    assert IntentRouter().route(text).intent is Intent.CHAT


def test_windows_error_code_research_is_not_source_coding():
    got = IntentRouter().route("İnternette bu hata kodunu araştır: 0x80070005.")
    assert got.intent is Intent.WEB_RESEARCH


def test_identity_statement_is_not_rag():
    got = IntentRouter().route("Ben senin geliştiricinim.")
    assert got.subtype == "IDENTITY"
    assert got.requires_memory is True
    assert got.requires_rag is False


def test_structured_result_matches_contract():
    got = IntentRouter().route("RAM kullanımım ne kadar?").as_dict()
    assert got["intent"] == "SYSTEM_MONITOR"
    assert 0 <= got["confidence"] <= 1
    assert got["requires_tool"] is True
    assert got["requires_memory"] is False
    assert got["requires_rag"] is False
    assert got["requires_confirmation"] is False
    assert got["required_tool"] is None
    assert got["entities"] == {}
    assert got["risk"] == "LOW"
    assert got["ambiguity"] is False
    assert got["needs_confirmation"] is False
    assert got["reasoning_level"] == 2
    assert got["original_text"] == "RAM kullanımım ne kadar?"
    assert got["normalized_text"] == "RAM kullanımım ne kadar?"


def test_computer_control_contract_exposes_required_tool_and_risk():
    got = IntentRouter().route("Chrome'u aç.")
    assert got.required_tool == "uygulama_ac"
    assert got.risk is RiskLevel.MEDIUM
    assert got.reasoning_level == 2


@pytest.mark.parametrize("text, expected_intent, expected_tool", [
    ("Jarvis windows sistemim şuan eksik update var mı",
     Intent.SYSTEM_MONITOR, "windows_update_status"),
    ("Jarvis masaüstümde neler var?",
     Intent.COMPUTER_CONTROL, "masaustu_listele"),
    ("ekran görüntüsü al ve o görüntüyü direkt aç",
     Intent.COMPUTER_CONTROL, "ekran_goruntusu_al_ac"),
    ("ekran görüntüsü nerede jarvis",
     Intent.COMPUTER_CONTROL, "son_ekran_goruntusu"),
    ("jarvis şuan bu sistem hakkında ne biliyorsun?",
     Intent.SYSTEM_MONITOR, "get_system_summary"),
    ("jarvi kamera özelliğini aktif et",
     Intent.COMPUTER_CONTROL, "kamera_kontrol"),
])
def test_reported_hallucination_prompts_require_the_exact_capability(
    text, expected_intent, expected_tool,
):
    got = IntentRouter().route(text)

    assert got.intent is expected_intent
    assert got.confidence == 0.99
    assert got.requires_tool is True
    assert got.required_tool == expected_tool


def test_explicit_windows_user_path_is_canonicalized_for_memory():
    got = IntentRouter().route(
        "Jarvis bu bilgisayarın ismi bu şeklde bunu kaydet "
        "Users\\Administrator\\"
    )

    assert got.intent is Intent.MEMORY_SAVE
    assert got.required_tool == "remember_fact"
    assert got.entities["windows_user_path"] == r"C:\Users\Administrator"


def test_speech_metadata_survives_intent_routing():
    got = IntentRouter().route(
        "Görev yöneticisini aç", original_text="Görev yerini sınaç",
        speech_confidence=0.94, ambiguity=False,
    )
    assert got.original_text == "Görev yerini sınaç"
    assert got.normalized_text == "Görev yöneticisini aç"
    assert got.confidence <= 0.94


@pytest.mark.parametrize("wake", [
    "Jarvis", "Jarvis?", "J.A.R.V.I.S.",
    "Jarvis aktif misin?", "J.A.R.V.I.S. aktif mi?",
    "Oğuz, aktif misin Jarvis?",
])
def test_bare_wake_word_is_level_zero(wake):
    got = IntentRouter().route(wake)
    assert got.intent is Intent.CHAT
    assert got.reasoning_level == 0


def _schema_names(schemas):
    return {(s.get("function") or {}).get("name") for s in schemas}


def test_agent_intent_gate_gives_chat_no_tools():
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore
    agent = build_agent(Config(llm_provider="mock", non_interactive=True),
                        memory=MemoryStore(":memory:"))
    decision = agent.intent_router.route("Nasılsın Jarvis?")
    schemas = agent._intent_schemas(agent.registry.schemas(), decision, "Nasılsın Jarvis?")
    assert schemas == []


def test_rag_concept_question_does_not_get_rag_tools():
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore
    agent = build_agent(Config(llm_provider="mock", non_interactive=True),
                        memory=MemoryStore(":memory:"))
    decision = agent.intent_router.route("RAG ne?")
    names = _schema_names(agent._intent_schemas(agent.registry.schemas(), decision, "RAG ne?"))
    assert "bilgi_ara" not in names and "bilgi_durum" not in names


def test_system_intent_only_gets_telemetry_tools():
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore
    agent = build_agent(Config(llm_provider="mock", non_interactive=True),
                        memory=MemoryStore(":memory:"))
    decision = agent.intent_router.route("RAM kullanımım ne kadar?")
    names = _schema_names(agent._intent_schemas(agent.registry.schemas(), decision,
                                                 "RAM kullanımım ne kadar?"))
    assert "get_ram_usage" in names
    assert "bilgi_ara" not in names
    assert "remember_fact" not in names
    assert "run_terminal_command" not in names


def test_coding_read_request_does_not_offer_write_or_shell():
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore
    agent = build_agent(Config(llm_provider="mock", non_interactive=True),
                        memory=MemoryStore(":memory:"))
    text = "Jarvis klasöründeki authentication kodunu incele."
    names = _schema_names(agent._intent_schemas(agent.registry.schemas(),
                                                 agent.intent_router.route(text), text))
    assert {"read_file", "list_directory"} <= names
    assert "write_file" not in names
    assert "run_terminal_command" not in names


def test_current_turn_intent_block_replaces_previous_one(monkeypatch):
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore
    from jarvis.llm.base import LLMResponse
    agent = build_agent(Config(llm_provider="mock", non_interactive=True),
                        memory=MemoryStore(":memory:"))
    monkeypatch.setattr(agent.llm, "chat", lambda *a, **k: LLMResponse(content="tamam"))
    agent.ask("Nasılsın?")
    agent.ask("RAM kullanımım ne kadar?")
    blocks = [m for m in agent.history if m.content.startswith(agent.INTENT_ONEKI)]
    assert len(blocks) == 1
    assert "SYSTEM_MONITOR" in blocks[0].content
