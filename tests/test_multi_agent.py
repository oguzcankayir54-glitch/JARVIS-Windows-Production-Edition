from __future__ import annotations

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.intent_router import Intent, IntentDecision
from jarvis.core.multi_agent import AgentRole, Supervisor
from jarvis.memory.store import MemoryStore
from jarvis.llm.base import LLMResponse


def _decision(intent):
    return IntentDecision(intent, 0.95, reason="test route")


def test_supervisor_routes_only_specialist_intents():
    supervisor = Supervisor(enabled=True)
    assert supervisor.route(_decision(Intent.CODING)).role is AgentRole.CODER
    assert supervisor.route(_decision(Intent.SYSTEM_MONITOR)).role is AgentRole.SYSTEM
    assert supervisor.route(_decision(Intent.WEB_RESEARCH)).role is AgentRole.RESEARCHER
    assert supervisor.route(_decision(Intent.CHAT)) is None


def test_natural_inline_python_fix_request_reaches_coder():
    cfg = Config(llm_provider="mock", non_interactive=True, multi_agent_enabled=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))

    agent.ask("Şu Python hatasını açıklayıp düzelt: def ilk(xs): return xs[0].")

    assert agent.last_delegation is not None
    assert agent.last_delegation.role is AgentRole.CODER
    assert agent.last_trace.specialist_role == "coder"


def test_supervisor_is_opt_in_and_delegation_depth_is_hard_limited():
    assert Supervisor(enabled=False).route(_decision(Intent.CODING)) is None
    supervisor = Supervisor(enabled=True, max_delegations=99)
    decision = supervisor.route(_decision(Intent.CODING))
    assert supervisor.max_delegations == 1
    assert decision.depth == 1
    assert "başka bir role görev devredemez" in supervisor.context(decision).content


def test_enabled_agent_emits_bounded_lifecycle_and_uses_same_llm():
    cfg = Config(
        llm_provider="mock", non_interactive=True,
        multi_agent_enabled=True,
    )
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    llm = agent.llm
    events = []
    agent.events.subscribe("agent.*", events.append)
    agent.events.subscribe("supervisor.*", events.append)

    agent.ask("Bu Python kodundaki hatayı incele")

    assert agent.llm is llm
    assert agent.last_delegation.role is AgentRole.CODER
    assert agent.last_trace.specialist_role == "coder"
    assert agent.last_trace.delegation_depth == 1
    assert [event.name for event in events] == [
        "supervisor.routing", "agent.delegated", "agent.started",
        "agent.finished", "supervisor.completed",
    ]
    assert all(event.payload.get("depth", 1) <= 1 for event in events)
    role_blocks = [m for m in agent.history if m.content.startswith("AKTİF UZMAN ROLÜ —")]
    assert len(role_blocks) == 1


def test_chat_falls_back_to_normal_jarvis_and_clears_old_role_block():
    cfg = Config(llm_provider="mock", non_interactive=True, multi_agent_enabled=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    agent.ask("Python kodunu incele")
    agent.ask("Bugün nasılsın?")
    assert agent.last_delegation is None
    assert not any(m.content.startswith("AKTİF UZMAN ROLÜ —") for m in agent.history)


def test_disabled_mode_preserves_single_agent_behavior():
    cfg = Config(llm_provider="mock", non_interactive=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    events = []
    agent.events.subscribe("agent.*", events.append)
    agent.ask("Python kodunu incele")
    assert agent.last_delegation is None
    assert events == []


def test_specialist_role_cannot_widen_intent_tool_allowlist():
    cfg = Config(llm_provider="mock", non_interactive=True, multi_agent_enabled=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    offered = []

    def chat(_messages, tools=None):
        offered.extend((schema.get("function") or {}).get("name") for schema in (tools or []))
        return LLMResponse(content="İncelendi.")

    agent.llm.chat = chat
    agent.ask("Python kodunu incele")
    assert set(offered) <= {"read_file", "list_directory"}
    assert "run_terminal_command" not in offered


def test_controlled_llm_failure_does_not_trigger_recursive_delegation():
    cfg = Config(llm_provider="mock", non_interactive=True, multi_agent_enabled=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    events = []
    agent.events.subscribe("agent.*", events.append)

    def fail(*_args, **_kwargs):
        raise RuntimeError("model unavailable")

    agent.llm.chat = fail
    # Agent renders an LLM failure as a controlled user-facing response.
    agent.ask("Python kodunu incele")
    assert sum(event.name == "agent.started" for event in events) == 1
    assert sum(event.name == "agent.finished" for event in events) == 1
