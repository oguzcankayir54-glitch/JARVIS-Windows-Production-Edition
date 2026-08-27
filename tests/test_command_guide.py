from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.command_guide import COMMAND_EXAMPLES, command_guide_prompt
from jarvis.core.intent_router import Intent, IntentRouter
from jarvis.core.persona import build_system_prompt
from jarvis.memory.store import MemoryStore
from jarvis.web.server import PanelServer


def test_command_examples_are_short_unique_and_natural():
    texts = [item.text for item in COMMAND_EXAMPLES]
    assert len(texts) >= 12
    assert len(texts) == len(set(texts))
    assert all(8 <= len(text) <= 90 for text in texts)
    assert all(not text.startswith("/") for text in texts)


def test_qwen_system_prompt_contains_the_same_examples_as_the_panel():
    prompt = build_system_prompt()
    assert command_guide_prompt() in prompt
    for item in COMMAND_EXAMPLES:
        assert item.text in prompt


def test_panel_exposes_clickable_command_examples():
    agent = build_agent(Config(llm_provider="mock", non_interactive=True),
                        memory=MemoryStore(":memory:"))
    data = PanelServer(agent, port=0).modul_verisi()["komutlar"]
    assert data["durum"] == "hazir"
    assert len(data["satirlar"]) == len(COMMAND_EXAMPLES)
    assert all(row["komut"] == row["deger"] for row in data["satirlar"])


def test_advertised_action_examples_reach_the_expected_intents():
    router = IntentRouter()
    expected = {
        "Sistem durumu nasıl?": Intent.SYSTEM_MONITOR,
        "Görev yöneticisini aç.": Intent.COMPUTER_CONTROL,
        "Bunu hatırla: Ana çalışma diskim C sürücüsü.": Intent.MEMORY_SAVE,
        "Açık vakaları göster.": Intent.TASK,
        "Bilgi tabanında NVMe sorununu ara.": Intent.RAG_QUERY,
        "İnternette RTX 3080 Ti sürücüsünü araştır.": Intent.WEB_RESEARCH,
        "Klasörü listele: C:\\Projeler": Intent.CODING,
        "GitHub'daki son commitlere bak.": Intent.GITHUB,
    }
    for text, intent in expected.items():
        assert router.route(text).intent is intent, text


def test_panel_html_has_the_command_tab_and_safe_text_insertion():
    html = __import__("pathlib").Path(
        "docs/mockups/jarvis-panel.html"
    ).read_text(encoding="utf-8")
    assert 'data-modul="komutlar"' in html
    assert "kutu.value = s.komut" in html
    assert "v.textContent = s.deger" in html
