from jarvis.core.context_manager import ContextManager
from jarvis.llm.base import Message


def test_dynamic_block_replaces_old_copy_without_touching_base():
    cm = ContextManager()
    base = Message(role="system", content="CORE")
    old = Message(role="system", content="INTENT: CHAT")
    hist = [base, old, Message(role="user", content="x")]
    got = cm.replace_system_block(hist, "INTENT:",
                                  Message(role="system", content="INTENT: RAG"))
    assert got[0].content == "CORE"
    assert sum(m.content.startswith("INTENT:") for m in got) == 1
    assert any(m.content == "INTENT: RAG" for m in got)


def test_prune_keeps_system_and_newest_conversation():
    cm = ContextManager(history_max_messages=4, max_chars=10000)
    hist = [Message(role="system", content="PERSONA")]
    for i in range(5):
        hist.extend([Message(role="user", content=f"u{i}"),
                     Message(role="assistant", content=f"a{i}")])
    got = cm.prune(hist)
    assert got[0].content == "PERSONA"
    non = [m for m in got if m.role != "system"]
    assert len(non) <= 4
    assert non[-1].content == "a4"
    assert non[0].role == "user"


def test_character_budget_drops_old_turns_but_keeps_persona():
    cm = ContextManager(history_max_messages=20, max_chars=120)
    hist = [Message(role="system", content="P" * 20)]
    for i in range(4):
        hist.extend([Message(role="user", content=(f"u{i}" + "x" * 35)),
                     Message(role="assistant", content=(f"a{i}" + "y" * 35))])
    got = cm.prune(hist)
    assert got[0].content == "P" * 20
    assert sum(len(m.content) for m in got) <= 120
    assert any(m.content.startswith("a3") for m in got)


def test_tool_result_truncation_preserves_both_ends():
    cm = ContextManager(tool_result_max_chars=100)
    got = cm.truncate_tool_result("A" * 100 + "B" * 100)
    assert got.startswith("A") and got.endswith("B")
    assert "kısaltıldı" in got
