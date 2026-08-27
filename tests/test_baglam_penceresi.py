"""Bağlam penceresi: yazılmayan bir ayarın sessizce yaptığı hasar.

Bu dosya bir ölçümden doğdu. Kullanıcının makinesinde çalıştırıldı:

    ollama show qwen2.5:14b-instruct --modelfile

ve çıktıda **tek bir ``PARAMETER`` satırı yoktu**. Yani ``num_ctx``
tanımsız ve Ollama'nın kendi varsayılanı (çoğu sürümde 2048) geçerli.
Ölçülen ilk tur ise 2338 token: sistem istemi 5344 karakter, bağlam
blokları, araç şemaları.

Yani pencere **ilk mesajda** taşıyordu. Taşınca kırpılan da en baştaki
mesaj oluyor — sistem istemi. Kişiliğin, "her cevabın Türkçe" kuralının
ve kullanıcının kimliğinin durduğu yer tam orası. "Beni tanımıyor",
"İngilizce cevap veriyor", "kişiliksiz" şikâyetlerinin üçü de tek bir
yazılmamış satıra bakıyor olabilir.

Buradaki testler iki şeyi koruyor: ayarın GÖNDERİLDİĞİNİ, ve taşmanın
sessiz kalmadığını.
"""
from __future__ import annotations

import io
import json

import pytest

from jarvis.llm import ollama_provider as mod
from jarvis.llm.base import Message
from jarvis.llm.ollama_provider import OllamaProvider


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _yakala(monkeypatch, payload=None, **kw):
    """Gönderilen gövdeyi yakalayan bir sağlayıcı döndür."""
    gonderilen: dict = {}

    def fake_urlopen(req, timeout=None):
        gonderilen.update(json.loads(req.data.decode("utf-8")))
        return _Resp(json.dumps(payload or {"message": {"content": "tamam"}}
                                ).encode("utf-8"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    return OllamaProvider("http://localhost:11434", "qwen2.5:14b", **kw), gonderilen


# ---------------- ayar gerçekten gidiyor mu ----------------

def test_the_context_window_is_sent_explicitly(monkeypatch):
    """Yazilmazsa Ollama'nin varsayilani geceriydi ve o varsayilan kucuktu."""
    p, gonderilen = _yakala(monkeypatch)
    p.chat([Message("user", "merhaba")])
    assert gonderilen["options"]["num_ctx"] == OllamaProvider.VARSAYILAN_NUM_CTX


def test_the_default_window_is_larger_than_a_measured_turn():
    """Olculdu: basit bir selam turu 2338 token.

    Varsayilan bunun altinda kalirsa hicbir sey duzelmez; buyume payi da
    olmali, cunku arac ciktilari tek adimda yuzlerce token ekliyor.
    """
    assert OllamaProvider.VARSAYILAN_NUM_CTX >= 2338 * 3


def test_the_window_can_be_raised_by_configuration(monkeypatch):
    p, gonderilen = _yakala(monkeypatch, num_ctx=32768)
    p.chat([Message("user", "merhaba")])
    assert gonderilen["options"]["num_ctx"] == 32768


def test_an_absurdly_small_window_is_refused(monkeypatch):
    """Sifir ya da negatif bir ayar, sessizce calismayan bir kurulum demek."""
    p, gonderilen = _yakala(monkeypatch, num_ctx=0)
    p.chat([Message("user", "merhaba")])
    assert gonderilen["options"]["num_ctx"] >= 512


def test_the_configuration_reaches_the_provider(monkeypatch):
    """Ayar Config'de var ama saglayiciya baglanmadiysa hicbir ise yaramaz."""
    from jarvis.bootstrap import build_llm
    from jarvis.config import Config

    monkeypatch.setenv("JARVIS_OLLAMA_NUM_CTX", "16384")
    llm = build_llm(Config(llm_provider="ollama"))
    assert llm.num_ctx == 16384


# ---------------- taşma sessiz kalmasın ----------------

KULLANIM = {
    "message": {"content": "tamam"},
    "prompt_eval_count": 2338,
    "eval_count": 120,
    "eval_duration": 3_000_000_000,
}


def test_context_use_is_measured_not_estimated(monkeypatch):
    """"3 karakter ~ 1 token" kabaca dogru ama tasmanin kenarinda yanilmak,
    sessizce kirpilan bir sistem istemi demek. Ollama sayiyi kendisi veriyor."""
    p, _ = _yakala(monkeypatch, KULLANIM)
    p.chat([Message("user", "merhaba")])
    assert p.son_kullanim["okunan_token"] == 2338
    assert p.son_kullanim["uretilen_token"] == 120


def test_tokens_per_second_comes_from_the_real_duration(monkeypatch):
    p, _ = _yakala(monkeypatch, KULLANIM)
    p.chat([Message("user", "merhaba")])
    assert p.son_kullanim["token_sn"] == 40.0


def test_a_full_window_raises_a_warning(monkeypatch):
    """Eski varsayilanla ayni tur: 2338/2048, yani %114."""
    p, _ = _yakala(monkeypatch, KULLANIM, num_ctx=2048)
    p.chat([Message("user", "merhaba")])
    kullanim = p.son_kullanim
    assert kullanim["doluluk"] > 1.0
    assert "uyari" in kullanim
    assert "sistem istemi" in kullanim["uyari"], "neyin kaybolacagi soylenmeli"


def test_a_comfortable_window_raises_no_warning(monkeypatch):
    p, _ = _yakala(monkeypatch, KULLANIM)
    p.chat([Message("user", "merhaba")])
    assert "uyari" not in p.son_kullanim
    assert p.son_kullanim["doluluk"] < 0.5


def test_the_warning_fires_before_the_window_is_full(monkeypatch):
    """%90'da uyarmak gec: bir sonraki tur arac ciktisiyla gelirse aradaki
    payi tek adimda yiyor."""
    assert OllamaProvider.DOLULUK_ESIGI <= 0.85


@pytest.mark.parametrize("oran,bekleniyor", [
    (0.79, False),   # esigin hemen altinda: sessiz
    (0.81, True),    # esigin hemen ustunde: uyari
])
def test_the_warning_boundary_holds_from_both_sides(monkeypatch, oran, bekleniyor):
    """Sinir tek yandan sinanirsa kayabilir ve kimse fark etmez."""
    pencere = 4096
    p, _ = _yakala(monkeypatch,
                   dict(KULLANIM, prompt_eval_count=round(pencere * oran)),
                   num_ctx=pencere)
    p.chat([Message("user", "merhaba")])
    assert ("uyari" in p.son_kullanim) is bekleniyor


def test_a_response_without_counters_does_not_crash(monkeypatch):
    """Eski Ollama surumleri bu alanlari gondermeyebilir."""
    p, _ = _yakala(monkeypatch, {"message": {"content": "tamam"}})
    p.chat([Message("user", "merhaba")])
    assert p.son_kullanim["okunan_token"] == 0
    assert "token_sn" not in p.son_kullanim


# ---------------- kurulum yeni makinelerde de yazsın ----------------

def test_the_installer_writes_the_setting():
    """Ayar kodda var ama .env'de yoksa, kuran kisi eski davranisi alirdi."""
    from pathlib import Path
    kok = Path(__file__).resolve().parents[1]
    ps1 = (kok / "windows/src/kur-windows.ps1").read_text(encoding="utf-8-sig")
    assert "JARVIS_OLLAMA_NUM_CTX=8192" in ps1
    assert "sistem istemi" in ps1, "neden gerektigi .env'de yazmali"
