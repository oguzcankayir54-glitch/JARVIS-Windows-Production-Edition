from jarvis.llm.base import Message
from jarvis.memory.working import WorkingMemory


def test_working_memory_snapshot_cannot_mutate_live_sequence():
    memory = WorkingMemory([Message(role="system", content="CORE")])
    snapshot = memory.snapshot()
    memory.append(Message(role="user", content="merhaba"))
    assert len(snapshot) == 1
    assert len(memory.snapshot()) == 2


def test_working_memory_reports_real_stats():
    memory = WorkingMemory([
        Message(role="system", content="CORE"),
        Message(role="user", content="abc"),
        Message(role="assistant", content="defg"),
    ])
    stats = memory.stats()
    assert stats.messages == 3
    assert stats.system_messages == 1
    assert stats.conversation_messages == 2
    assert stats.characters == 11


def test_clearing_working_memory_preserves_system_messages():
    memory = WorkingMemory([
        Message(role="system", content="CORE"),
        Message(role="user", content="temporary"),
        Message(role="assistant", content="temporary answer"),
    ])
    memory.clear_conversation()
    assert [(m.role, m.content) for m in memory.snapshot()] == [("system", "CORE")]
