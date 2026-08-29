import json
import pytest

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.core.events import EventBus
from jarvis.memory.store import MemoryStore
from jarvis.web.server import PanelServer


def _agent():
    return build_agent(
        Config(llm_provider="mock", non_interactive=True),
        memory=MemoryStore(":memory:"),
    )


def test_exact_prefix_and_wildcard_subscriptions_receive_once():
    bus = EventBus()
    seen = []
    listener = lambda event: seen.append(event.name)
    bus.subscribe("tool.finished", listener)
    bus.subscribe("tool.*", listener)
    bus.subscribe("*", listener)
    bus.publish("tool.finished", {"tool": "x"})
    assert seen == ["tool.finished"]


def test_listener_failure_isolated_and_unsubscribe_is_idempotent(caplog):
    bus = EventBus()
    bus.subscribe("jarvis.ready",
                  lambda _event: (_ for _ in ()).throw(RuntimeError("boom")))
    seen = []
    unsubscribe = bus.subscribe("jarvis.*", lambda event: seen.append(event.name))
    bus.publish("jarvis.ready")
    unsubscribe()
    unsubscribe()
    bus.publish("jarvis.error")
    assert seen == ["jarvis.ready"]
    assert "event listener failed" in caplog.text


def test_history_is_bounded_and_payload_is_copied():
    bus = EventBus(history_size=2)
    payload = {"value": 1}
    bus.publish("jarvis.started", payload)
    payload["value"] = 99
    bus.publish("jarvis.ready")
    bus.publish("llm.started")
    recent = bus.recent()
    assert [event.name for event in recent] == ["jarvis.ready", "llm.started"]
    assert bus.recent("llm.*")[0].name == "llm.started"


def test_agent_emits_llm_tool_and_state_events():
    agent = _agent()
    events = []
    agent.events.subscribe("*", events.append)
    agent.ask("sistem durumu nedir?")
    names = [event.name for event in events]
    assert "llm.started" in names and "llm.finished" in names
    assert "tool.started" in names and "tool.finished" in names
    assert "state.changed" in names
    tool_event = next(event for event in events if event.name == "tool.started")
    assert set(tool_event.payload) == {"tool"}, "tool argümanları event'e sızmamalı"


def test_agent_lifecycle_events_are_available_in_bounded_history():
    agent = _agent()
    names = [event.name for event in agent.events.recent("jarvis.*")]
    assert names[:2] == ["jarvis.started", "jarvis.ready"]


def test_handled_llm_failure_emits_llm_error_without_raw_message():
    agent = _agent()
    events = []
    agent.events.subscribe("llm.*", events.append)
    agent.llm.chat = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("secret detail"))
    agent.ask("merhaba")
    error = next(event for event in events if event.name == "llm.error")
    assert error.payload == {"model": "mock", "error_type": "RuntimeError"}
    assert "secret detail" not in json.dumps(error.as_dict())


def test_unexpected_core_failure_emits_jarvis_error():
    agent = _agent()
    events = []
    agent.events.subscribe("jarvis.error", events.append)
    agent.intent_router.route = lambda *a, **k: (
        _ for _ in ()).throw(ValueError("private input"))
    with pytest.raises(ValueError):
        agent.ask("merhaba")
    assert events[0].payload == {"error_type": "ValueError"}


def test_agent_emits_memory_events():
    agent = _agent()
    names = []
    agent.events.subscribe("memory.*", lambda event: names.append(event.name))
    agent.ask("hatırla: kahve = sütlü")
    agent.ask("hafızanda ne var?")
    assert "memory.saved" in names
    assert "memory.retrieved" in names


def test_panel_bridges_core_events_to_sse():
    agent = _agent()
    panel = PanelServer(agent)
    q = panel.hub.subscribe()
    agent.events.publish("system.warning", {"code": "demo"}, source="test")
    payloads = []
    while not q.empty():
        raw = q.get_nowait()
        if raw.startswith("event: system.warning"):
            payloads.append(json.loads(raw.split("data: ", 1)[1]))
    assert payloads[0]["name"] == "system.warning"
    assert payloads[0]["payload"] == {"code": "demo"}
    panel.shutdown()


def test_panel_emits_voice_input_lifecycle():
    class STT:
        name = "stub"
        available = True

        def transcribe(self, _audio, _content_type):
            return "merhaba"

    agent = _agent()
    panel = PanelServer(agent, stt=STT())
    names = []
    agent.events.subscribe("voice.*", lambda event: names.append(event.name))
    assert panel.listen(b"audio", "audio/wav") == "merhaba"
    assert names == ["voice.input", "voice.listening", "voice.finished"]
    panel.shutdown()
