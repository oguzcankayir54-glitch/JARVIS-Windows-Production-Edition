"""Phase 1 — immutable/layered identity contract."""
from jarvis.core.assistant_rules import ASSISTANT_RULES_PROMPT
from jarvis.core.core_identity import CoreIdentity, core_identity_prompt
from jarvis.core.persona import build_system_prompt
from jarvis.core.personality import PERSONALITY_PROMPT
from jarvis.core.owner import Owner


def test_core_identity_is_immutable():
    identity = CoreIdentity.from_assistant()
    try:
        identity.name = "HAL"  # type: ignore[misc]
    except Exception:
        pass
    assert identity.name == "J.A.R.V.I.S."


def test_core_identity_explicitly_rejects_chat_rename():
    text = core_identity_prompt()
    assert "değiştirilemez" in text
    assert "artık adın X" in text


def test_prompt_layers_are_independently_present():
    text = build_system_prompt(Owner(name="Deniz"))
    assert "CORE IDENTITY" in text
    assert PERSONALITY_PROMPT in text
    assert ASSISTANT_RULES_PROMPT in text
    assert "KORUNAN OWNER KİMLİĞİ" in text


def test_owner_is_not_described_as_normal_fact_memory():
    text = build_system_prompt(Owner(name="Deniz", role="geliştiricisi"))
    assert "ayrı Owner/Memory katmanından" in text
    assert "KORUNAN OWNER KİMLİĞİ" in text
