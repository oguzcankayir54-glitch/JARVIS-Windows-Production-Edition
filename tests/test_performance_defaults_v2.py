from jarvis.config import Config
from jarvis.core.context_manager import ContextManager


def test_qwen_14b_is_the_default_reasoning_model(monkeypatch):
    monkeypatch.delenv("JARVIS_OLLAMA_MODEL", raising=False)
    assert Config().ollama_model == "qwen2.5:14b-instruct"


def test_context_budget_leaves_room_inside_8192_window(monkeypatch):
    monkeypatch.delenv("JARVIS_CONTEXT_MAX_CHARS", raising=False)
    cfg = Config()
    # 18k message chars is deliberately below a full 8192-token window;
    # system/tool schemas and answer generation still need headroom.
    assert cfg.context_max_chars <= 18000
    assert ContextManager().max_chars <= 18000


def test_env_template_documents_context_budget():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / ".env.example").read_text()
    assert "JARVIS_OLLAMA_MODEL=qwen2.5:14b-instruct" in text
    assert "JARVIS_CONTEXT_MAX_CHARS=18000" in text
