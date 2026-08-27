from jarvis.core.agent import Agent
from jarvis.llm.mock_provider import MockProvider
from jarvis.memory.store import MemoryStore
from jarvis.security.audit import AuditLog
from jarvis.security.permissions import PermissionManager
from jarvis.tools.base import ToolRegistry
from jarvis.tools.manager import ToolManager


def _agent():
    reg = ToolRegistry()
    tools = ToolManager(reg, PermissionManager(audit=AuditLog(), non_interactive=True))
    return Agent(MockProvider(), tools, reg, memory=MemoryStore(":memory:"))


def test_direct_training_turn_keeps_user_assistant_pair_in_history():
    agent = _agent()
    reply = agent.ask("Eğitim süreci 1.")
    non_system = [(m.role, m.content) for m in agent.history if m.role != "system"]
    assert non_system[-2][0] == "user"
    assert non_system[-2][1] == "Eğitim süreci 1."
    assert non_system[-1] == ("assistant", reply)
    assert agent.last_trace is not None
    assert agent.last_trace.detected_intent == "TRAINING"
    assert agent.last_trace.response_status == "ok"
