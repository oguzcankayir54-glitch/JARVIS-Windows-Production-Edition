"""Akışlı cevap — beklemeyi kısaltmıyor, görünür kılıyor.

Ölçüldü (RTX 3080 Ti, qwen2.5:14b-instruct): 250 token'lık gerçekçi bir
cevap 65,8 token/sn ile **3,80 saniye** sürüyor. Akışsız çağrıda
kullanıcı bu sürenin tamamını hiçbir şey görmeden bekliyor.

Model akışla daha hızlı çalışmıyor — değişen tek şey ilk kelimenin ne
zaman göründüğü. Ama kullanıcının "yavaş" dediği şey tam olarak o.

Buradaki testler üç şeyi koruyor: parçaların GELDİĞİNİ, tamamının
birleştiğini, ve akışın yarıda kalması hâlinde turun düşmediğini.
Araç çağrıları ayrı bir mesele: model araç isteyeceğine karar verirse
metin üretmiyor, yani akış boş bitebiliyor.
"""
from __future__ import annotations

import io
import json

import pytest

from jarvis.llm import ollama_provider as mod
from jarvis.llm.base import Message
from jarvis.llm.ollama_provider import OllamaProvider

NS = 1_000_000_000


class _AkisYaniti(io.BytesIO):
    """Ollama'nın NDJSON akışı: her satıra bir JSON nesnesi."""

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _akis(monkeypatch, satirlar, gonderilen=None):
    govde = b"".join(json.dumps(s).encode("utf-8") + b"\n" for s in satirlar)

    def fake_urlopen(req, timeout=None):
        if gonderilen is not None:
            gonderilen.update(json.loads(req.data.decode("utf-8")))
        return _AkisYaniti(govde)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    return OllamaProvider("http://localhost:11434", "qwen2.5:14b")


def _metin_satirlari(*parcalar, son=None):
    satirlar = [{"message": {"content": p}, "done": False} for p in parcalar]
    satirlar.append(son or {"message": {"content": ""}, "done": True,
                            "prompt_eval_count": 5217, "eval_count": 3,
                            "prompt_eval_duration": NS // 50,
                            "eval_duration": NS // 20})
    return satirlar


# ---------------- parçalar geliyor mu ----------------

def test_chunks_arrive_one_by_one(monkeypatch):
    """Akisin butun anlami bu: cevap bitmeden parca gelmeli."""
    p = _akis(monkeypatch, _metin_satirlari("Sistem", " hazır", " efendim."))
    assert list(p.chat_stream([Message("user", "merhaba")])) == \
        ["Sistem", " hazır", " efendim."]


def test_the_full_answer_is_available_after_the_stream(monkeypatch):
    p = _akis(monkeypatch, _metin_satirlari("Sistem", " hazır", " efendim."))
    list(p.chat_stream([Message("user", "merhaba")]))
    assert p.son_yanit.content == "Sistem hazır efendim."


def test_empty_chunks_are_not_yielded(monkeypatch):
    """Ollama bos content'li satirlar da gonderiyor; onlar gurultu."""
    p = _akis(monkeypatch, _metin_satirlari("Sistem", "", " hazır"))
    assert "" not in list(p.chat_stream([Message("user", "merhaba")]))


def test_the_request_asks_for_streaming(monkeypatch):
    gonderilen: dict = {}
    p = _akis(monkeypatch, _metin_satirlari("tamam"), gonderilen)
    list(p.chat_stream([Message("user", "merhaba")]))
    assert gonderilen["stream"] is True


def test_streaming_and_plain_calls_share_the_same_settings(monkeypatch):
    """Ayri kurulsalardi num_ctx birinde degisip digerinde kalirdi —
    ve o ayar yazilmadiginda hata vermiyor, sessizce yanlis calisiyor."""
    akis: dict = {}
    p = _akis(monkeypatch, _metin_satirlari("tamam"), akis)
    list(p.chat_stream([Message("user", "merhaba")]))

    duz: dict = {}

    def fake_urlopen(req, timeout=None):
        duz.update(json.loads(req.data.decode("utf-8")))
        return _AkisYaniti(json.dumps({"message": {"content": "tamam"}}).encode())

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    p.chat([Message("user", "merhaba")])
    assert akis["options"] == duz["options"]
    assert akis["model"] == duz["model"]


# ---------------- ölçüm akışta da çalışıyor mu ----------------

def test_usage_stats_arrive_with_the_final_chunk(monkeypatch):
    """Istatistikler yalnizca SON nesnede geliyor."""
    p = _akis(monkeypatch, _metin_satirlari("Sistem", " hazır"))
    list(p.chat_stream([Message("user", "merhaba")]))
    assert p.son_kullanim["okunan_token"] == 5217
    assert p.son_kullanim["okuma_sn"] == 0.02


def test_usage_is_empty_until_the_stream_is_drained(monkeypatch):
    """Akis tuketilmeden istatistik istemek erken; bos donmeli."""
    p = _akis(monkeypatch, _metin_satirlari("Sistem", " hazır"))
    uretec = p.chat_stream([Message("user", "merhaba")])
    next(uretec)
    assert p.son_kullanim == {}


# ---------------- araç çağrısı ----------------

def test_a_tool_call_ends_the_stream_without_text(monkeypatch):
    """Model arac isteyecekse metin uretmiyor. Cagiran taraf
    son_yanit.wants_tool ile bakmali, bos metne degil."""
    p = _akis(monkeypatch, [
        {"message": {"content": "", "tool_calls": [
            {"function": {"name": "get_ram_usage", "arguments": {}}}]},
         "done": False},
        {"message": {"content": ""}, "done": True},
    ])
    assert list(p.chat_stream([Message("user", "ram?")])) == []
    assert p.son_yanit.wants_tool
    assert p.son_yanit.tool_calls[0].name == "get_ram_usage"


def test_a_previous_answer_does_not_leak_into_the_next_stream(monkeypatch):
    """son_yanit her akisin basinda sifirlanmali.

    Sifirlanmazsa, arac isteyen (yani metinsiz) bir tur bir onceki turun
    cevabini tasir ve model soylemedigi seyi soylemis gorunur.
    """
    p = _akis(monkeypatch, _metin_satirlari("ilk cevap"))
    list(p.chat_stream([Message("user", "bir")]))
    assert p.son_yanit.content == "ilk cevap"

    # Ikinci akis hic metin uretmiyor (model arac istedi).
    _akis(monkeypatch, [{"message": {"content": ""}, "done": True}])
    list(p.chat_stream([Message("user", "iki")]))
    assert p.son_yanit.content == ""


# ---------------- bozuk akış turu düşürmemeli ----------------

def test_a_malformed_line_is_skipped_not_fatal(monkeypatch):
    """Yarim bir satir butun turu dusurmemeli: kalan parcalar hâlâ
    ise yarar bir cevap olusturuyor."""
    govde = (b'{"message":{"content":"Sistem"},"done":false}\n'
             b'{bozuk json\n'
             b'{"message":{"content":" hazir"},"done":true}\n')

    def fake_urlopen(req, timeout=None):
        return _AkisYaniti(govde)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    p = OllamaProvider("http://localhost:11434", "qwen2.5:14b")
    assert list(p.chat_stream([Message("user", "merhaba")])) == ["Sistem", " hazir"]


def test_blank_lines_are_ignored(monkeypatch):
    govde = (b'{"message":{"content":"a"},"done":false}\n'
             b'\n'
             b'{"message":{"content":"b"},"done":true}\n')

    def fake_urlopen(req, timeout=None):
        return _AkisYaniti(govde)

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    p = OllamaProvider("http://localhost:11434", "qwen2.5:14b")
    assert list(p.chat_stream([Message("user", "merhaba")])) == ["a", "b"]


def test_a_connection_error_is_explained_not_raw(monkeypatch):
    """Akista da ayni acik mesaj gelmeli; ham urllib hatasi ise yaramiyor."""
    def fake_urlopen(req, timeout=None):
        raise mod.urllib.error.URLError(OSError(111, "Connection refused"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    p = OllamaProvider("http://localhost:11434", "qwen2.5:14b")
    with pytest.raises(RuntimeError) as hata:
        list(p.chat_stream([Message("user", "merhaba")]))
    assert "Ollama" in str(hata.value)
