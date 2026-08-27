from jarvis.core.intent_router import Intent, IntentDecision
from jarvis.core.tool_router import ToolRouter


def _schema(name):
    return {"type": "function", "function": {"name": name, "parameters": {}}}


ALL = [_schema(n) for n in (
    "get_system_info", "get_ram_usage", "remember_fact", "recall_facts",
    "bilgi_ara", "bilgi_durum", "read_file", "list_directory", "write_file",
    "run_terminal_command", "web_ara", "web_oku", "uygulama_ac",
)]


def names(items):
    return {(s.get("function") or {}).get("name") for s in items}


def test_chat_exposes_nothing():
    got = ToolRouter().select(ALL, IntentDecision(Intent.CHAT, .9), "Nasılsın?")
    assert got == []


def test_memory_recall_cannot_write_or_delete():
    got = names(ToolRouter().select(
        ALL, IntentDecision(Intent.MEMORY_RECALL, .9), "Benim hakkımda ne biliyorsun?"))
    assert got == {"recall_facts"}


def test_rag_query_cannot_get_shell_or_memory():
    got = names(ToolRouter().select(
        ALL, IntentDecision(Intent.RAG_QUERY, .9), "Bu PDF'de ne yazıyor?"))
    assert got == {"bilgi_ara", "bilgi_durum"}


def test_coding_inspection_is_read_only():
    got = names(ToolRouter().select(
        ALL, IntentDecision(Intent.CODING, .9), "authentication kodunu incele"))
    assert got == {"read_file", "list_directory"}


def test_coding_edit_may_expose_write_but_not_shell_by_default():
    got = names(ToolRouter().select(
        ALL, IntentDecision(Intent.CODING, .9), "authentication kodunu düzelt"))
    assert "write_file" in got
    assert "run_terminal_command" not in got


def test_github_does_not_fall_back_to_arbitrary_shell():
    got = ToolRouter().select(
        ALL, IntentDecision(Intent.GITHUB, .9), "GitHub son commit'e bak")
    assert got == []
