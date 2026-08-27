"""Ollama provider — the response shapes a real model can actually return.

This path has no coverage from a live model in CI, so the parsing is tested
against the shapes that differ between models and Ollama versions. A malformed
tool call must never take down the turn.
"""
import io
import json

import pytest

from jarvis.llm import ollama_provider as mod
from jarvis.llm.base import Message
from jarvis.llm.ollama_provider import OllamaProvider
from jarvis.llm.errors import ErrorType, LLMProviderError


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _provider(monkeypatch, payload):
    def fake_urlopen(req, timeout=None):
        return _Resp(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    return OllamaProvider("http://localhost:11434", "qwen2.5:7b")


def test_plain_text_answer(monkeypatch):
    p = _provider(monkeypatch, {"message": {"content": "Merhaba, buradayım."}})
    res = p.chat([Message("user", "selam")])
    assert res.content == "Merhaba, buradayım." and not res.wants_tool


def test_tool_call_with_dict_arguments(monkeypatch):
    p = _provider(monkeypatch, {"message": {"content": "", "tool_calls": [
        {"function": {"name": "get_ram_usage", "arguments": {}}}
    ]}})
    res = p.chat([Message("user", "ram?")])
    assert res.wants_tool
    assert res.tool_calls[0].name == "get_ram_usage"


def test_arguments_as_json_string_are_parsed(monkeypatch):
    """Some builds serialise arguments as a string; tools need a dict."""
    p = _provider(monkeypatch, {"message": {"tool_calls": [
        {"function": {"name": "run_terminal_command", "arguments": '{"command": "df -h"}'}}
    ]}})
    call = p.chat([Message("user", "disk")]).tool_calls[0]
    assert call.arguments == {"command": "df -h"}


def test_malformed_arguments_fall_back_to_empty(monkeypatch):
    p = _provider(monkeypatch, {"message": {"tool_calls": [
        {"function": {"name": "get_ram_usage", "arguments": "{bozuk json"}}
    ]}})
    assert p.chat([Message("user", "x")]).tool_calls[0].arguments == {}


def test_flat_shape_without_function_wrapper(monkeypatch):
    p = _provider(monkeypatch, {"message": {"tool_calls": [
        {"name": "get_system_info", "arguments": {}}
    ]}})
    assert p.chat([Message("user", "x")]).tool_calls[0].name == "get_system_info"


@pytest.mark.parametrize("bad", [
    [{"function": {}}],                 # isimsiz
    [{"function": {"name": ""}}],       # boş isim
    ["düz metin"],                      # sözlük değil
    [{"function": "metin"}],            # function sözlük değil
    [None],
])
def test_malformed_calls_are_skipped_not_fatal(monkeypatch, bad):
    p = _provider(monkeypatch, {"message": {"content": "yine de cevap", "tool_calls": bad}})
    res = p.chat([Message("user", "x")])
    assert res.tool_calls == []
    assert res.content == "yine de cevap", "bozuk çağrı metni yutmamalı"


def test_mixed_valid_and_invalid_calls_keeps_valid(monkeypatch):
    p = _provider(monkeypatch, {"message": {"tool_calls": [
        {"function": {}},
        {"function": {"name": "get_ram_usage", "arguments": {}}},
    ]}})
    calls = p.chat([Message("user", "x")]).tool_calls
    assert [c.name for c in calls] == ["get_ram_usage"]


def test_unreachable_server_raises_readable_error(monkeypatch):
    def boom(req, timeout=None):
        raise mod.urllib.error.URLError("bağlantı yok")

    monkeypatch.setattr(mod.urllib.request, "urlopen", boom)
    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    with pytest.raises(LLMProviderError, match="Ollama'ya ulaşılamadı") as exc:
        p.chat([Message("user", "x")])
    assert exc.value.kind is ErrorType.SERVER_UNAVAILABLE
    assert exc.value.retryable is False
    assert exc.value.fallback_allowed is False


def test_timeout_is_typed_and_allows_one_controlled_retry(monkeypatch):
    monkeypatch.setattr(
        mod.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(TimeoutError("timed out")),
    )
    with pytest.raises(LLMProviderError) as exc:
        OllamaProvider("http://localhost:11434", "qwen", timeout=2).chat(
            [Message("user", "x")]
        )
    assert exc.value.kind is ErrorType.TIMEOUT
    assert exc.value.retryable is True


def test_missing_model_is_typed_for_model_fallback(monkeypatch):
    error = mod.urllib.error.HTTPError(
        "http://x", 404, "not found", {},
        io.BytesIO(b'{"error":"model not found"}'),
    )
    monkeypatch.setattr(
        mod.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(error),
    )
    with pytest.raises(LLMProviderError) as exc:
        OllamaProvider("http://localhost:11434", "missing").chat(
            [Message("user", "x")]
        )
    assert exc.value.kind is ErrorType.MODEL_MISSING
    assert exc.value.server_available is True
    assert exc.value.fallback_allowed is True


def test_oom_is_distinct_from_generic_http_failure(monkeypatch):
    error = mod.urllib.error.HTTPError(
        "http://x", 500, "error", {},
        io.BytesIO(b'{"error":"model requires more system memory: out of memory"}'),
    )
    monkeypatch.setattr(
        mod.urllib.request, "urlopen",
        lambda *a, **k: (_ for _ in ()).throw(error),
    )
    with pytest.raises(LLMProviderError) as exc:
        OllamaProvider("http://localhost:11434", "large").chat(
            [Message("user", "x")]
        )
    assert exc.value.kind is ErrorType.MODEL_OOM
    assert exc.value.fallback_allowed is True


def test_tool_result_messages_carry_name(monkeypatch):
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["body"] = json.loads(req.data)
        return _Resp(json.dumps({"message": {"content": "ok"}}).encode())

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    p = OllamaProvider("http://localhost:11434", "qwen2.5:7b")
    p.chat([Message("tool", "sonuç", name="get_ram_usage")])
    assert captured["body"]["messages"][0]["name"] == "get_ram_usage"


# ---------------- sampling options ----------------

def test_sampling_options_are_sent(monkeypatch):
    """Without options Ollama silently applies temperature 0.8."""
    from jarvis.llm import ollama_provider as op

    gonderilen = {}

    class _Yanit:
        def __enter__(self): return self
        def __exit__(self, *e): return False
        def read(self): return b'{"message": {"content": "tamam"}}'

    def sahte(req, timeout=None):
        gonderilen.update(json.loads(req.data))
        return _Yanit()

    monkeypatch.setattr(op.urllib.request, "urlopen", sahte)
    op.OllamaProvider("http://x", "m", temperature=0.2, top_p=0.8,
                      repeat_penalty=1.2).chat([Message(role="user", content="selam")])

    # num_ctx da bu sozlukte: yazilmazsa Ollama'nin varsayilani geceriydi ve
    # o varsayilan olculen ilk turumuzdan kucuktu (bkz. test_baglam_penceresi).
    assert gonderilen["options"] == {
        "temperature": 0.2, "top_p": 0.8, "repeat_penalty": 1.2,
        "num_ctx": op.OllamaProvider.VARSAYILAN_NUM_CTX,
        "num_predict": 512}
    assert gonderilen["think"] is False
    assert gonderilen["keep_alive"] == "30m"


def test_provider_defaults_are_conservative():
    from jarvis.llm.ollama_provider import OllamaProvider
    p = OllamaProvider("http://x", "m")
    assert p.temperature <= 0.5 and p.repeat_penalty >= 1.0


def test_reasoning_profile_bounds_generation_and_thinking():
    p = OllamaProvider("http://x", "m", num_predict=512, think=False)
    p.apply_reasoning(1)
    assert p.num_predict == 192 and p.think is False
    p.apply_reasoning(5)
    assert p.num_predict == 1280 and p.think is True


def test_assistant_tool_calls_are_encoded_back_to_ollama(monkeypatch):
    sent = {}
    def fake_urlopen(req, timeout=None):
        sent.update(json.loads(req.data.decode("utf-8")))
        return _Resp(json.dumps({"message": {"content": "tamam"}}).encode("utf-8"))
    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    p = OllamaProvider("http://localhost:11434", "qwen")
    p.chat([
        Message("user", "ram"),
        Message("assistant", "", tool_calls=[{
            "function": {"name": "get_ram_usage", "arguments": {}}
        }]),
        Message("tool", "{\"ram\": 42}", name="get_ram_usage"),
    ])
    assert sent["messages"][1]["tool_calls"][0]["function"]["name"] == "get_ram_usage"
