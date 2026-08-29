"""Memory store and the tools that gate access to it."""
from jarvis.memory.store import MemoryStore
from jarvis.security.audit import AuditLog
from jarvis.security.permissions import PermissionManager
from jarvis.tools.base import ToolRegistry
from jarvis.tools.manager import ToolManager
from jarvis.tools.memory_tools import register_memory_tools


def _store():
    return MemoryStore(":memory:")


def test_remember_and_recall():
    s = _store()
    s.remember("editor", "neovim", "kullanici")
    facts = s.recall("editor")
    assert len(facts) == 1 and facts[0].value == "neovim"


def test_remember_is_idempotent_and_updates():
    s = _store()
    s.remember("gpu", "RTX 3080")
    s.remember("gpu", "RTX 3080 Ti")
    facts = s.recall("gpu")
    assert len(facts) == 1 and facts[0].value == "RTX 3080 Ti"


def test_recall_filters_by_category():
    s = _store()
    s.remember("editor", "neovim", "kullanici")
    s.remember("anakart", "B550", "donanim")
    assert len(s.recall(category="donanim")) == 1


def test_forget_removes_fact():
    s = _store()
    s.remember("gecici", "veri")
    assert s.forget("gecici") is True
    assert s.recall("gecici") == []
    assert s.forget("gecici") is False


def test_empty_key_rejected():
    s = _store()
    try:
        s.remember("   ", "x")
    except ValueError:
        return
    raise AssertionError("boş anahtar kabul edilmemeliydi")


def test_conversation_is_logged():
    s = _store()
    s.add_message("sess1", "user", "merhaba")
    s.add_message("sess1", "assistant", "buradayım")
    s.add_message("sess2", "user", "başka oturum")
    msgs = s.recent_messages("sess1")
    assert [m.role for m in msgs] == ["user", "assistant"]
    assert s.session_count("sess2") == 1


def test_fact_count_is_exact_and_does_not_mark_usage():
    s = _store()
    s.remember("a", "1")
    s.remember("b", "2")
    assert s.fact_count() == 2
    assert all(f.usage_count == 0 for f in s.all_facts())


def test_memory_tools_roundtrip_through_manager():
    s = _store()
    reg = register_memory_tools(ToolRegistry(), s)
    mgr = ToolManager(reg, PermissionManager(audit=AuditLog(), non_interactive=True))

    saved = mgr.dispatch("remember_fact", {"key": "kahve", "value": "sütlü", "category": "kullanici"})
    assert saved.ok and saved.data["kaydedildi"]

    found = mgr.dispatch("recall_facts", {"query": "kahve"})
    assert found.ok and found.data["adet"] == 1

    gone = mgr.dispatch("forget_fact", {"key": "kahve"})
    assert gone.ok and gone.data["silindi"]
