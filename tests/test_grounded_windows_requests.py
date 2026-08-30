import pytest

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.llm.base import LLMResponse, ToolCall
from jarvis.memory.store import MemoryStore
from jarvis.tools.base import ToolResult


def _agent():
    return build_agent(
        Config(llm_provider="mock", non_interactive=True),
        memory=MemoryStore(":memory:"),
    )


@pytest.mark.parametrize("prompt, tool_name", [
    ("Jarvis windows sistemim şuan eksik update var mı", "windows_update_status"),
    ("Jarvis masaüstümde neler var?", "masaustu_listele"),
    ("ekran görüntüsü al ve o görüntüyü direkt aç", "ekran_goruntusu_al_ac"),
    ("ekran görüntüsü nerede jarvis", "son_ekran_goruntusu"),
    ("jarvis şuan bu sistem hakkında ne biliyorsun?", "get_system_summary"),
    ("jarvi kamera özelliğini aktif et", "kamera_kontrol"),
])
def test_transcript_actions_cannot_succeed_without_a_tool_call(
    prompt, tool_name, monkeypatch,
):
    agent = _agent()
    calls = []

    def chat(_messages, tools=None):
        calls.append({
            (schema.get("function") or {}).get("name")
            for schema in tools or ()
        })
        return LLMResponse(
            content=(
                "Başarıyla tamamlandı. C:\\Users\\Administrator\\uydurma.png "
                "RTX 3080 Ti, 34.2 GB RAM."
            )
        )

    monkeypatch.setattr(agent.llm, "chat", chat)

    reply = agent.ask(prompt)

    assert len(calls) == 2
    assert all(tool_name in offered for offered in calls)
    assert "başarıyla" not in reply.casefold()
    assert "uydurma.png" not in reply
    assert "RTX 3080" not in reply
    assert "gerçekleştiremedim" in reply.casefold()
    assert agent.last_trace.tools_used == []


@pytest.mark.parametrize("prompt, tool_name, trusted", [
    ("Jarvis windows sistemim şuan eksik update var mı",
     "windows_update_status", "Windows Update bekleyen güncelleme bulmadı."),
    ("Jarvis masaüstümde neler var?",
     "masaustu_listele", "Masaüstünde 1 öğe var: GERCEK.txt."),
    ("ekran görüntüsü al ve o görüntüyü direkt aç",
     "ekran_goruntusu_al_ac", r"Ekran görüntüsünü aldım ve açtım: C:\Gercek.png"),
    ("ekran görüntüsü nerede jarvis",
     "son_ekran_goruntusu", r"Son ekran görüntüsü burada: C:\Gercek.png"),
    ("jarvis şuan bu sistem hakkında ne biliyorsun?",
     "get_system_summary", "Doğrulanan sistem bilgileri: GERÇEK DONANIM."),
    ("jarvi kamera özelliğini aktif et",
     "kamera_kontrol", "Kamerayı etkinleştiremedim: kamera kapalı."),
])
def test_verified_capability_message_overrides_model_invention(
    prompt, tool_name, trusted, monkeypatch,
):
    agent = _agent()
    replies = [
        LLMResponse(tool_calls=[ToolCall(tool_name, {})]),
        LLMResponse(content="Uydurma başarı ve uydurma yol."),
    ]
    monkeypatch.setattr(agent.llm, "chat", lambda *_args, **_kwargs: replies.pop(0))
    monkeypatch.setattr(
        agent.tools,
        "dispatch",
        lambda *_args, **_kwargs: ToolResult(
            ok=True,
            verified=True,
            data={"user_message": trusted},
        ),
    )

    reply = agent.ask(prompt)

    assert reply == trusted
    assert agent.last_trace.tools_used == [tool_name]


def test_update_result_follow_up_keeps_the_grounded_update_contract(monkeypatch):
    agent = _agent()
    first = [
        LLMResponse(tool_calls=[ToolCall("windows_update_status", {})]),
        LLMResponse(content="model anlatımı"),
    ]
    monkeypatch.setattr(agent.llm, "chat", lambda *_a, **_k: first.pop(0))
    monkeypatch.setattr(
        agent.tools,
        "dispatch",
        lambda *_a, **_k: ToolResult(
            ok=True,
            verified=True,
            data={"user_message": "1 gerçek güncelleme var."},
        ),
    )
    assert agent.ask("Jarvis windows sistemim şuan eksik update var mı") == (
        "1 gerçek güncelleme var."
    )

    offered = []

    def no_tool(_messages, tools=None):
        offered.append({
            (schema.get("function") or {}).get("name")
            for schema in tools or ()
        })
        return LLMResponse(content="Uydurma sonuçlar burada.")

    monkeypatch.setattr(agent.llm, "chat", no_tool)
    reply = agent.ask("sonuçları göster")

    assert len(offered) == 2
    assert all("windows_update_status" in names for names in offered)
    assert agent.last_intent.required_tool == "windows_update_status"
    assert "uydurma" not in reply.casefold()
    assert "gerçekleştiremedim" in reply.casefold()


def test_windows_user_path_cannot_be_replaced_by_model_arguments(monkeypatch):
    agent = _agent()
    replies = [
        LLMResponse(tool_calls=[ToolCall("remember_fact", {
            "key": "bilgisayar_adi",
            "value": "Bu bilgisayarın ismi",
            "category": "genel",
        })]),
        LLMResponse(content="Bilgisayar adını da uydurarak kaydettim."),
    ]
    seen = []
    monkeypatch.setattr(agent.llm, "chat", lambda *_a, **_k: replies.pop(0))

    def dispatch(name, arguments):
        seen.append((name, dict(arguments)))
        return ToolResult(
            ok=True,
            verified=True,
            data={
                "user_message": (
                    "Windows kullanıcı yolunu aynen kaydettim: "
                    r"C:\Users\Administrator"
                ),
            },
        )

    monkeypatch.setattr(agent.tools, "dispatch", dispatch)

    reply = agent.ask(
        "Jarvis bu bilgisayarın ismi bu şeklde bunu kaydet "
        "Users\\Administrator\\"
    )

    assert seen == [("remember_fact", {
        "key": "windows_kullanici_yolu",
        "value": r"C:\Users\Administrator",
        "category": "sistem",
        "cikarim": False,
    })]
    assert reply == (
        "Windows kullanıcı yolunu aynen kaydettim: "
        r"C:\Users\Administrator"
    )
