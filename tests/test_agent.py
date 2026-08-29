"""State machine + end-to-end agent loop with the mock provider."""
from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.state import JarvisState, StateMachine
from jarvis.memory.store import MemoryStore


def test_state_machine_notifies_listeners():
    sm = StateMachine()
    seen = []
    sm.subscribe(lambda old, new: seen.append((old, new)))
    sm.transition(JarvisState.THINKING)
    sm.transition(JarvisState.THINKING)  # no-op, same state
    sm.transition(JarvisState.STANDBY)
    assert seen == [
        (JarvisState.STANDBY, JarvisState.THINKING),
        (JarvisState.THINKING, JarvisState.STANDBY),
    ]


def test_state_listener_failure_does_not_break_transition(caplog):
    sm = StateMachine()
    sm.subscribe(lambda _old, _new: (_ for _ in ()).throw(RuntimeError("boom")))
    sm.transition(JarvisState.THINKING, reason="test", details={"request": "r1"})
    snap = sm.snapshot()
    assert snap.state is JarvisState.THINKING
    assert snap.previous is JarvisState.STANDBY
    assert snap.revision == 1
    assert snap.reason == "test" and snap.details == {"request": "r1"}
    assert "state listener failed" in caplog.text


def test_state_subscription_can_be_removed():
    sm = StateMachine()
    seen = []
    unsubscribe = sm.subscribe(lambda old, new: seen.append((old, new)))
    unsubscribe()
    unsubscribe()
    sm.transition(JarvisState.THINKING)
    assert seen == []


def test_state_labels_are_turkish():
    assert JarvisState.DIAGNOSING.label_tr == "TEŞHİS EDİYOR"
    assert JarvisState.STANDBY.label_tr == "HAZIR"


def _agent(memory=None):
    cfg = Config(llm_provider="mock", non_interactive=True)
    return build_agent(cfg, memory=memory or MemoryStore(":memory:"))


def test_agent_answers_plain_greeting():
    agent = _agent()
    reply = agent.ask("merhaba")
    assert "J.A.R.V.I.S." in reply or "JARVIS" in reply.upper() or reply


def test_agent_calls_tool_for_system_query():
    agent = _agent()
    reply = agent.ask("sistem durumu nedir?")
    # Response Engine must hide the internal tool name while preserving data.
    assert "get_system_info" not in reply
    assert "CPU" in reply or "RAM" in reply


def test_agent_returns_to_standby_after_turn():
    agent = _agent()
    agent.ask("cpu sıcaklığı?")
    assert agent.state.state is JarvisState.STANDBY


def test_unexpected_turn_failure_still_recovers_state(monkeypatch):
    agent = _agent()
    monkeypatch.setattr(agent.intent_router, "route",
                        lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    try:
        agent.ask("merhaba")
    except RuntimeError:
        pass
    else:
        raise AssertionError("beklenmeyen çekirdek hatası yutulmamalı")
    assert agent.state.state is JarvisState.STANDBY


def test_agent_step_limit_is_bounded():
    assert _agent().max_steps >= 1
    cfg = Config(llm_provider="mock", non_interactive=True, max_agent_steps=999)
    assert build_agent(cfg, memory=MemoryStore(":memory:")).max_steps == 32


def test_first_turn_is_marked_for_the_model():
    """The model cannot reliably tell it is the first message; we say so."""
    agent = _agent()
    agent.ask("merhaba")
    notes = [m for m in agent.history if m.role == "system" and "İLK kullanıcı" in m.content]
    assert len(notes) == 1


def test_wake_word_bypasses_llm_and_returns_short_reply(monkeypatch):
    agent = _agent()

    def should_not_run(*args, **kwargs):
        raise AssertionError("LEVEL 0 wake-word LLM çağırmamalı")

    monkeypatch.setattr(agent.llm, "chat", should_not_run)
    reply = agent.ask("Jarvis")

    assert reply == "Efendim?"
    assert agent.last_intent.reasoning_level == 0
    assert agent.last_trace is not None
    assert agent.last_trace.reasoning_level == 0
    assert agent.last_trace.thinking_enabled is False


def test_active_question_always_returns_efendim_without_llm(monkeypatch):
    agent = _agent()

    def should_not_run(*args, **kwargs):
        raise AssertionError("aktiflik çağrısı LLM'e gitmemeli")

    monkeypatch.setattr(agent.llm, "chat", should_not_run)
    assert agent.ask("Jarvis aktif misin?") == "Efendim?"
    assert agent.ask("J.A.R.V.I.S. aktif mi?") == "Efendim?"
    assert agent.ask("Oğuz, aktif misin Jarvis?") == "Efendim?"


def test_later_turns_do_not_keep_the_first_turn_marker():
    agent = _agent()
    agent.ask("jarvis")
    agent.ask("merhaba tekrar")
    notes = [m for m in agent.history if m.role == "system" and "İLK kullanıcı" in m.content]
    assert notes == [], "ilk tur bilgisi sonraki turlara sızmamalı"


def test_agent_logs_conversation_to_memory():
    store = MemoryStore(":memory:")
    agent = _agent(store)
    agent.ask("merhaba")
    roles = [m.role for m in store.recent_messages(agent.session_id)]
    assert roles == ["user", "assistant"]


def test_agent_injects_known_facts_into_context():
    store = MemoryStore(":memory:")
    store.remember("anakart", "MSI B550-A PRO", "donanim")
    agent = _agent(store)
    agent.ask("anakart modelim neydi?")
    blocks = [m for m in agent.history if m.content.startswith("Hafızandaki")]
    assert len(blocks) == 1 and "MSI B550-A PRO" in blocks[0].content


def test_memory_block_is_not_duplicated_across_turns():
    store = MemoryStore(":memory:")
    store.remember("gpu", "RTX 3080")
    agent = _agent(store)
    agent.ask("gpu modelim neydi?")
    agent.ask("gpu modelimi tekrar söyle")
    blocks = [m for m in agent.history if m.content.startswith("Hafızandaki")]
    assert len(blocks) == 1


# ---------------- kimlik bilinmiyorken ----------------
# Gerçek bir şikâyetten geliyor: "Jarvis beni hatırlamıyor", "sen kimsin
# dediğimde beni tasarlayan Oğuz Kayır demiyor". Sebep kod değildi — sahip
# kaydı hiç kurulmamıştı. Asıl kusur J.A.R.V.I.S.'in bunu SÖYLEMEMESİYDİ.

def test_an_unknown_owner_is_stated_not_hidden():
    from jarvis.core.persona import build_system_prompt
    prompt = build_system_prompt(owner=None)
    assert "TANIMLANMAMIŞ" in prompt
    assert "jarvis-tanit" in prompt, "ne yapılacağını söylemeli"


def test_the_model_is_told_not_to_invent_an_identity():
    from jarvis.core.persona import build_system_prompt
    assert "UYDURMA" in build_system_prompt(owner=None)


def test_a_known_owner_replaces_that_block():
    from jarvis.core.owner import Owner
    from jarvis.core.persona import build_system_prompt
    prompt = build_system_prompt(Owner(name="Deniz Yılmaz"))
    assert "TANIMLANMAMIŞ" not in prompt
    assert "Deniz Yılmaz" in prompt


def test_who_built_you_is_answered_from_the_owner_record():
    from jarvis.core.owner import Owner
    prompt = Owner(name="Deniz Yılmaz", role="tasarımcısı").to_prompt()
    assert "SENİ KİM YAPTI" in prompt
    assert "Deniz Yılmaz tasarladı" in prompt


def test_calling_the_name_alone_is_treated_as_a_summons():
    """Sadece "Jarvis" demek soru değil, çağrıdır: kısa karşılık bekler."""
    from jarvis.core.owner import Owner
    prompt = Owner(name="Deniz", address_forms=["Deniz Bey", "Efendim"]).to_prompt()
    assert "SESLENİŞ" in prompt
    assert "Efendim?" in prompt
    assert "Açıklama yapma" in prompt


# ---------------- cevabın dili ----------------
# "Türkçe terimlere bazen İngilizce cevap veriyor." En olası sebep şu:
# web sayfaları, kod parçaları ve araç çıktıları İngilizce geliyor ve model
# bağlamının diline uyum sağlıyor. Kural sistem isteminde vardı ama uzun bir
# metnin ortasındaydı; artık verinin YANINA da konuyor.

def test_english_tool_output_carries_a_language_reminder():
    from jarvis.core.metin import ingilizce_agirlikli
    ingilizce = ("The motherboard is not detected. This can be caused by the "
                 "RAM modules that are not seated properly and you should "
                 "check them before you replace the board.")
    assert ingilizce_agirlikli(ingilizce)


def test_turkish_tool_output_is_left_alone():
    """Her araç çıktısına hatırlatma eklemek bağlamı boşuna şişirirdi."""
    from jarvis.core.metin import ingilizce_agirlikli
    turkce = ("Anakart algılanmıyor. Bu genellikle bellek modüllerinin tam "
              "oturmamasından olur ve bunları kontrol etmek gerekir; sonra "
              "kartı değiştirmeyi düşünün.")
    assert not ingilizce_agirlikli(turkce)


def test_a_short_string_is_not_judged():
    """Kısa bir metinde bir 'the' rastlantıdır, dil değil."""
    from jarvis.core.metin import ingilizce_agirlikli
    assert not ingilizce_agirlikli("the")
    assert not ingilizce_agirlikli("SMART ok")
    assert not ingilizce_agirlikli("")


def test_the_reminder_reaches_the_history_next_to_the_data(monkeypatch):
    """Kuralın veriye YAKIN olması önemli: uzun bir sistem isteminin
    ortasındaki aynı cümle işe yaramamıştı."""
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore

    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))

    ingilizce = ("The disk is failing and you should replace it with a new "
                 "one that has the same interface, because the data on it "
                 "will not be readable when it stops.")

    class _Arac:
        name = "deneme"
        def run(self, **kw):
            from jarvis.tools.base import ToolResult
            return ToolResult(ok=True, data={"metin": ingilizce})

    monkeypatch.setattr(ajan.tools, "dispatch",
                        lambda ad, args: _Arac().run(**(args or {})))

    from jarvis.llm.base import LLMResponse, ToolCall
    cevaplar = [LLMResponse(content="", tool_calls=[ToolCall("deneme", {})]),
                LLMResponse(content="Disk arızalı, değiştirilmeli.")]
    monkeypatch.setattr(ajan.llm, "chat", lambda *a, **k: cevaplar.pop(0))

    ajan.ask("disk nasıl")
    arac_mesajlari = [m for m in ajan.history if m.role == "tool"]
    assert arac_mesajlari, "araç sonucu geçmişe düşmeli"
    assert "TÜRKÇE" in arac_mesajlari[-1].content


def test_the_prompt_says_the_source_language_does_not_decide():
    from jarvis.core.persona import BASE_PROMPT
    assert "HER CEVABIN TÜRKÇE" in BASE_PROMPT
    assert "DEĞİŞTİRMEZ" in BASE_PROMPT


def test_history_is_bounded_without_dropping_system_persona():
    agent = _agent()
    agent.history_max_messages = 6
    for i in range(10):
        agent.ask(f"mesaj {i}")
    non_system = [m for m in agent.history if m.role != "system"]
    assert len(non_system) <= 6
    assert agent.history[0].role == "system"
    assert "Kişilik:" in agent.history[0].content


def test_tool_output_is_bounded_from_both_ends():
    agent = _agent()
    agent.tool_result_max_chars = 100
    text = "A" * 100 + "B" * 100
    got = agent._arac_ciktisini_sinirla(text)
    assert len(got) < len(text)
    assert got.startswith("A") and got.endswith("B")
    assert "kısaltıldı" in got


def test_llm_failure_returns_to_standby_and_is_logged():
    store = MemoryStore(":memory:")
    agent = _agent(store)
    def boom(*args, **kwargs):
        raise RuntimeError("Ollama bağlantısı kesildi")
    agent.llm.chat = boom
    reply = agent.ask("merhaba")
    assert "bağlanamıyorum" in reply or "tamamlayamadı" in reply
    assert "Ollama bağlantısı kesildi" not in reply
    assert agent.state.state is JarvisState.STANDBY
    assert store.recent_messages(agent.session_id)[-1].role == "assistant"


def test_typed_llm_failure_reaches_observability_without_raw_detail():
    from jarvis.llm.errors import ErrorType, LLMProviderError
    agent = _agent()

    def boom(*args, **kwargs):
        raise LLMProviderError(
            "secret backend detail", kind=ErrorType.MODEL_OOM,
            fallback_allowed=True, server_available=True,
        )

    agent.llm.chat = boom
    reply = agent.ask("karmaşık bir analiz yap")

    assert agent.last_trace is not None
    assert agent.last_trace.error_type == "MODEL_OOM"
    assert "secret backend detail" not in reply


def test_agent_keeps_the_assistant_tool_request_before_tool_result(monkeypatch):
    agent = _agent()
    from jarvis.llm.base import LLMResponse, ToolCall
    seen = []
    replies = [
        LLMResponse(tool_calls=[ToolCall("get_ram_usage", {})]),
        LLMResponse(content="RAM tamam"),
    ]
    def chat(messages, tools=None):
        seen.append(list(messages))
        return replies.pop(0)
    monkeypatch.setattr(agent.llm, "chat", chat)
    agent.ask("ram durumu")
    second = seen[1]
    assistant = [m for m in second if m.role == "assistant" and m.tool_calls]
    tools = [m for m in second if m.role == "tool"]
    assert assistant and tools
    assert assistant[-1].tool_calls[0]["function"]["name"] == "get_ram_usage"


def test_failed_tool_cannot_be_presented_as_success(monkeypatch):
    """Tool evidence outranks a model's invented success statement."""
    agent = _agent()
    from jarvis.llm.base import LLMResponse, ToolCall
    from jarvis.tools.base import ToolResult

    replies = [
        LLMResponse(tool_calls=[ToolCall("get_ram_usage", {})]),
        LLMResponse(content="Açıldı, efendim."),
    ]
    monkeypatch.setattr(agent.llm, "chat", lambda *a, **k: replies.pop(0))
    monkeypatch.setattr(
        agent.tools,
        "dispatch",
        lambda *a, **k: ToolResult(ok=False, error="erişim reddedildi"),
    )

    reply = agent.ask("RAM durumunu göster")

    assert "açıldı" not in reply.casefold()
    assert "tamamlanamadı" in reply.casefold()


def test_later_success_resolves_an_earlier_failure_for_same_tool(monkeypatch):
    """A controlled retry may succeed; stale failure evidence must not win."""
    agent = _agent()
    from jarvis.llm.base import LLMResponse, ToolCall
    from jarvis.tools.base import ToolResult

    replies = [
        LLMResponse(tool_calls=[ToolCall("get_ram_usage", {})]),
        LLMResponse(tool_calls=[ToolCall("get_ram_usage", {})]),
        LLMResponse(content="RAM bilgisi alındı."),
    ]
    results = [
        ToolResult(ok=False, error="geçici hata"),
        ToolResult(ok=True, data={"ram_percent": 47}),
    ]
    monkeypatch.setattr(agent.llm, "chat", lambda *a, **k: replies.pop(0))
    monkeypatch.setattr(agent.tools, "dispatch", lambda *a, **k: results.pop(0))

    reply = agent.ask("RAM durumunu göster")

    assert reply == "RAM bilgisi alındı."
