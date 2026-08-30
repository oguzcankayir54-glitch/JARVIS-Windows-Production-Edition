from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.intent_router import Intent, IntentRouter
from jarvis.llm.base import LLMResponse, ToolCall
from jarvis.memory.store import MemoryStore
from jarvis.tools.base import ToolResult


def _agent():
    return build_agent(
        Config(llm_provider="mock", non_interactive=True),
        memory=MemoryStore(":memory:"),
    )


def test_router_distinguishes_inline_advice_inspection_edit_and_test():
    router = IntentRouter()

    advice = router.route("Şu hatayı düzelt: def ilk(xs): return xs[0]")
    inspect = router.route("Jarvis projesindeki authentication kodunu incele")
    edit = router.route("Jarvis projesindeki authentication kodunu düzelt")
    test = router.route("Jarvis projesinin testlerini çalıştır")

    assert (advice.intent, advice.subtype, advice.requires_tool) == (
        Intent.CODING, "CODE_ADVICE", False,
    )
    assert inspect.subtype == "CODE_INSPECT" and inspect.requires_tool
    assert edit.subtype == "CODE_EDIT" and edit.requires_tool
    assert test.subtype == "CODE_TEST" and test.requires_tool


def test_code_inspection_without_source_evidence_is_retried_then_refused(monkeypatch):
    agent = _agent()
    calls = []

    def chat(_messages, tools=None):
        calls.append({
            (schema.get("function") or {}).get("name")
            for schema in tools or ()
        })
        return LLMResponse(content="Dosyayı inceledim, hata 42. satırda.")

    monkeypatch.setattr(agent.llm, "chat", chat)

    reply = agent.ask("Jarvis projesindeki authentication kodunu incele")

    assert len(calls) == 2
    assert all("code_search" in offered for offered in calls)
    assert "42. satır" not in reply
    assert "gerçekleştiremedim" in reply.casefold()


def test_partial_code_edit_evidence_cannot_claim_completion(monkeypatch):
    agent = _agent()
    replies = [
        LLMResponse(tool_calls=[ToolCall("read_file", {"path": "app.py"})]),
        LLMResponse(content="Düzelttim, bütün testler geçti."),
        LLMResponse(content="Düzelttim, bütün testler geçti."),
    ]
    monkeypatch.setattr(agent.llm, "chat", lambda *_a, **_k: replies.pop(0))
    monkeypatch.setattr(
        agent.tools, "dispatch",
        lambda *_a, **_k: ToolResult(
            ok=True, verified=True, data={"path": "app.py", "icerik": "x"},
        ),
    )

    reply = agent.ask("Jarvis projesindeki app.py hatasını düzelt")

    assert "testler geçti" not in reply.casefold()
    assert "gerçekleştiremedim" in reply.casefold()
    assert agent.last_trace.tools_used == ["read_file"]


def test_complete_code_chain_returns_only_verified_edit_and_test_result(monkeypatch):
    agent = _agent()
    replies = [
        LLMResponse(tool_calls=[ToolCall("code_search", {"query": "bug"})]),
        LLMResponse(tool_calls=[ToolCall("edit_file", {
            "path": "app.py", "old_text": "bug", "new_text": "fixed",
        })]),
        LLMResponse(tool_calls=[ToolCall("run_project_tests", {})]),
        LLMResponse(content="On dosyayı değiştirdim, 999 test geçti."),
    ]
    results = {
        "code_search": ToolResult(
            ok=True, verified=True, data={"matches": [{"path": "app.py", "line": 1}]},
        ),
        "edit_file": ToolResult(
            ok=True, verified=True, data={"path": "/repo/app.py", "edited": True},
        ),
        "run_project_tests": ToolResult(
            ok=True, verified=True,
            data={"passed": True, "framework": "pytest", "exit_code": 0},
        ),
    }
    monkeypatch.setattr(agent.llm, "chat", lambda *_a, **_k: replies.pop(0))
    monkeypatch.setattr(
        agent.tools, "dispatch", lambda name, _args: results[name],
    )

    reply = agent.ask("Jarvis projesindeki app.py hatasını düzelt")

    assert reply == (
        "Kod değişikliği gerçekten uygulandı: /repo/app.py. "
        "Test doğrulaması tamamlandı: pytest testleri gerçekten geçti "
        "(çıkış kodu 0)."
    )
    assert "999" not in reply


def test_failed_code_test_overrules_model_success_claim(monkeypatch):
    agent = _agent()
    replies = [
        LLMResponse(tool_calls=[ToolCall("run_project_tests", {})]),
        LLMResponse(content="Bütün testler geçti."),
    ]
    monkeypatch.setattr(agent.llm, "chat", lambda *_a, **_k: replies.pop(0))
    monkeypatch.setattr(
        agent.tools,
        "dispatch",
        lambda *_a, **_k: ToolResult(
            ok=False, verified=False, error="1 test failed",
            data={"passed": False, "exit_code": 1},
        ),
    )

    reply = agent.ask("Jarvis projesinin testlerini çalıştır")

    assert "testler geçti" not in reply.casefold()
    assert "tamamlanamadı" in reply.casefold()


def test_inline_code_advice_remains_a_tool_free_conversation(monkeypatch):
    agent = _agent()
    seen = []

    def chat(_messages, tools=None):
        seen.append(list(tools or ()))
        return LLMResponse(content="Boş liste için önce kontrol ekleyin.")

    monkeypatch.setattr(agent.llm, "chat", chat)

    reply = agent.ask("Şu hatayı düzelt: def ilk(xs): return xs[0]")

    assert reply == "Boş liste için önce kontrol ekleyin."
    assert seen == [[]]
