from jarvis.core.intent_router import Intent, IntentDecision
from jarvis.core.response_engine import ResponseEngine


def test_tool_name_prefix_is_not_exposed():
    e = ResponseEngine({"get_ram_usage"})
    out = e.render("[get_ram_usage] sonucu: {'ram_used_gb': 4.0, 'ram_total_gb': 8.0, 'ram_percent': 50, 'swap_used_gb': 0}",
                   intent=Intent.SYSTEM_MONITOR, user_text="RAM kullanımım ne?")
    assert "get_ram_usage" not in out
    assert "RAM 4/8 GB" in out


def test_stack_trace_is_hidden_in_normal_mode():
    e = ResponseEngine()
    out = e.render("Traceback (most recent call last):\n  File 'x.py', line 1\nRuntimeError: boom",
                   intent=Intent.CHAT, user_text="ne oldu?")
    assert "Traceback" not in out
    assert "RuntimeError" not in out


def test_debug_mode_may_show_raw_trace():
    e = ResponseEngine()
    raw = "Traceback (most recent call last):\nRuntimeError: boom"
    assert e.render(raw, intent=Intent.CHAT, user_text="debug", debug=True) == raw


def test_rag_word_is_allowed_when_user_asks_what_rag_is():
    e = ResponseEngine()
    out = e.render("RAG, modele ilgili belgeleri getiren bir yöntemdir.",
                   intent=Intent.CHAT, user_text="RAG ne?")
    assert "RAG" in out


def test_backend_empty_kb_cli_leak_becomes_natural_language():
    e = ResponseEngine()
    out = e.render("Bilgi tabanınız boş. jarvis-bilgi ekle <klasör> kullanın.",
                   intent=Intent.CHAT, user_text="Ben senin geliştiricinim.")
    assert "jarvis-bilgi" not in out
    assert "henüz kayıtlı" in out


def test_exception_detail_is_hidden_normally():
    e = ResponseEngine()
    out = e.error(RuntimeError("SECRET_INTERNAL_PATH /tmp/x"))
    assert "SECRET_INTERNAL_PATH" not in out
    assert "/tmp/x" not in out


def test_github_intent_still_hides_runtime_tool_identifier():
    e = ResponseEngine({"git_log"})
    out = e.render("git_log ile son commit bulundu.",
                   intent=Intent.GITHUB, user_text="GitHub'daki son commit'e bak")
    assert "git_log" not in out
    assert "iç işlem" in out


def _action_decision(confidence=0.97):
    return IntentDecision(
        Intent.COMPUTER_CONTROL,
        confidence,
        requires_tool=True,
        tool="uygulama_ac",
    )


def test_missing_tool_grounding_depends_on_execution_evidence_not_prose():
    engine = ResponseEngine({"uygulama_ac"})
    out = engine.ground_missing_tool_call(
        "Açıldı efendim.",
        decision=_action_decision(),
        offered_tools={"uygulama_ac"},
        tools_used=(),
    )
    assert "Açıldı" not in out
    assert "gerçekleştiremedim" in out


def test_missing_tool_gate_needs_confidence_and_the_required_offered_tool():
    engine = ResponseEngine({"uygulama_ac"})
    for decision, offered in (
        (_action_decision(0.89), {"uygulama_ac"}),
        (_action_decision(), {"uygulama_listesi"}),
    ):
        assert not engine.missing_required_tool_call(
            decision=decision,
            offered_tools=offered,
            tools_used=(),
        )


def test_any_real_tool_call_keeps_the_missing_call_guard_closed():
    engine = ResponseEngine({"uygulama_ac"})
    assert not engine.missing_required_tool_call(
        decision=_action_decision(),
        offered_tools={"uygulama_ac"},
        tools_used=("uygulama_listesi",),
    )
