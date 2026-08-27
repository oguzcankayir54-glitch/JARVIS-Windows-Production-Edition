from jarvis.llm.base import LLMResponse, Message
from jarvis.llm.errors import ErrorType, LLMProviderError
from jarvis.llm.fallback_provider import FallbackProvider


class _Provider:
    name = "ollama"

    def __init__(self, model, outcomes):
        self.model = model
        self.outcomes = list(outcomes)
        self.calls = 0
        self.son_kullanim = {}

    def chat(self, messages, tools=None):
        self.calls += 1
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def _error(kind, **kwargs):
    return LLMProviderError("hata", kind=kind, **kwargs)


def test_missing_primary_model_uses_fallback():
    primary = _Provider("14b", [_error(
        ErrorType.MODEL_MISSING, fallback_allowed=True, server_available=True)])
    fallback = _Provider("7b", [LLMResponse(content="yedek cevap")])
    provider = FallbackProvider(primary, fallback)

    assert provider.chat([Message("user", "x")]).content == "yedek cevap"
    assert provider.fallback_used is True
    assert provider.active_model == "7b"


def test_dead_server_never_tries_another_model_on_same_server():
    primary = _Provider("14b", [_error(
        ErrorType.SERVER_UNAVAILABLE, fallback_allowed=False,
        server_available=False)])
    fallback = _Provider("7b", [LLMResponse(content="olmamalı")])
    provider = FallbackProvider(primary, fallback)

    try:
        provider.chat([Message("user", "x")])
    except LLMProviderError as exc:
        assert exc.kind is ErrorType.SERVER_UNAVAILABLE
    else:
        raise AssertionError("sunucu hatası yükseltilmeliydi")
    assert fallback.calls == 0
    assert provider.circuit_open is True


def test_timeout_gets_exactly_one_controlled_retry():
    primary = _Provider("14b", [
        _error(ErrorType.TIMEOUT, retryable=True, fallback_allowed=True),
        LLMResponse(content="ikinci denemede tamam"),
    ])
    fallback = _Provider("7b", [LLMResponse(content="gereksiz")])
    provider = FallbackProvider(primary, fallback, max_retries=1)

    assert provider.chat([Message("user", "x")]).content == "ikinci denemede tamam"
    assert primary.calls == 2
    assert fallback.calls == 0
    assert provider.retry_count == 1


def test_persistent_timeout_falls_back_after_retry_budget():
    timeout = lambda: _error(
        ErrorType.TIMEOUT, retryable=True, fallback_allowed=True)
    primary = _Provider("14b", [timeout(), timeout()])
    fallback = _Provider("7b", [LLMResponse(content="hızlı yedek")])
    provider = FallbackProvider(primary, fallback, max_retries=1)

    assert provider.chat([Message("user", "x")]).content == "hızlı yedek"
    assert primary.calls == 2 and fallback.calls == 1


def test_bootstrap_builds_fallback_only_when_explicitly_configured():
    from jarvis.bootstrap import build_llm
    from jarvis.config import Config
    from jarvis.llm.ollama_provider import OllamaProvider

    direct = build_llm(Config(
        llm_provider="ollama", ollama_model="14b", ollama_fallback_model=""))
    routed = build_llm(Config(
        llm_provider="ollama", ollama_model="14b", ollama_fallback_model="7b"))

    assert isinstance(direct, OllamaProvider)
    assert isinstance(routed, FallbackProvider)
    assert routed.primary.model == "14b" and routed.fallback.model == "7b"
