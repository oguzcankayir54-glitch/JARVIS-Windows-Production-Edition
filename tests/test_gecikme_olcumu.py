"""Bekleme süresi nereye gidiyor — tahmin değil, ölçüm.

"Jarvis yavaş" tek bir şikâyet gibi görünüyor ama en az üç ayrı sebebi
var ve üçünün çaresi de farklı:

* **Model yükleme** — Ollama modeli diskten karta alıyor. Turda bir kez
  ve saniyelerce sürebiliyor; ``keep_alive`` bunu engelliyor.
* **İstemi okuma (prefill)** — sistem istemi + araç şemaları + geçmiş.
  Ölçüldü: basit bir "Nasılsın?" turunda 4.545 token.
* **Cevabı üretme** — asıl konuşma. Saniyede üretilen token sayısı.

Hangisinin baskın olduğunu bilmeden yapılan iyileştirme, tahmine yapılan
yatırım. Ollama üç süreyi de cevabın içinde veriyor; buradaki testler
bunların okunduğunu ve doğru yorumlandığını koruyor.

Asıl aranan şey **okuma darboğazı**. Qwen'in şablonu araç şemalarını
SİSTEM bloğunun içine koyuyor; araç listesi turdan tura değişince blok
değişiyor ve Ollama'nın istem önbelleği kullanılamıyor. O zaman bütün
istem her turda yeniden işleniyor. Ölçüm bunu görünür kılıyor.
"""
from __future__ import annotations

import io
import json

import pytest

from jarvis.llm import ollama_provider as mod
from jarvis.llm.base import Message
from jarvis.llm.ollama_provider import OllamaProvider

NS = 1_000_000_000


class _Resp(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def _cevap(monkeypatch, payload):
    def fake_urlopen(req, timeout=None):
        return _Resp(json.dumps(payload).encode("utf-8"))

    monkeypatch.setattr(mod.urllib.request, "urlopen", fake_urlopen)
    p = OllamaProvider("http://localhost:11434", "qwen2.5:14b")
    p.chat([Message(role="user", content="merhaba")])
    return p.son_kullanim


#: Saglikli bir tur: okuma hizli (onbellek tuttu), uretim baskin.
SAGLIKLI = {
    "message": {"content": "tamam"},
    "prompt_eval_count": 210, "prompt_eval_duration": NS // 5,      # 0.20 sn
    "eval_count": 180, "eval_duration": 6 * NS,                     # 6.00 sn
    "total_duration": 6 * NS + NS // 5,
}

#: Onbellegin tutmadigi tur: 4.545 token bastan okunuyor.
OKUMA_BASKIN = {
    "message": {"content": "tamam"},
    "prompt_eval_count": 4545, "prompt_eval_duration": 45 * NS // 10,   # 4.50 sn
    "eval_count": 180, "eval_duration": 6 * NS,                         # 6.00 sn
    "total_duration": 105 * NS // 10,
}


# ---------------- süre dağılımı okunuyor mu ----------------

def test_the_three_durations_are_read_separately(monkeypatch):
    """Uc ayri yavaslik, uc ayri care. Tek bir "yavas" sayisi ise yaramaz."""
    k = _cevap(monkeypatch, SAGLIKLI)
    assert k["okuma_sn"] == 0.2
    assert k["uretim_sn"] == 6.0
    assert k["toplam_sn"] == 6.2


def test_prefill_speed_is_reported_in_tokens_per_second(monkeypatch):
    """Token/sn, ham sureden daha karsilastirilabilir: istem uzunlugu
    turdan tura degisiyor."""
    k = _cevap(monkeypatch, SAGLIKLI)
    assert k["okuma_token_sn"] == round(210 / 0.2, 1)


def test_generation_speed_is_still_reported(monkeypatch):
    k = _cevap(monkeypatch, SAGLIKLI)
    assert k["token_sn"] == 30.0


# ---------------- darboğaz teşhisi ----------------

def test_a_healthy_turn_reports_no_bottleneck(monkeypatch):
    """Onbellek tuttugunda okuma uretimin yaninda kayboluyor."""
    assert "darbogaz" not in _cevap(monkeypatch, SAGLIKLI)


def test_a_prefill_heavy_turn_is_flagged(monkeypatch):
    """Olculen gercek durum: 4.545 token her turda bastan okunuyor."""
    k = _cevap(monkeypatch, OKUMA_BASKIN)
    assert "darbogaz" in k
    assert "İSTEMİ OKUMAKTA" in k["darbogaz"]


def test_the_bottleneck_message_names_the_actual_cause(monkeypatch):
    """Tesbit tek basina ise yaramiyor; ne yapilacagini soylemeli."""
    mesaj = _cevap(monkeypatch, OKUMA_BASKIN)["darbogaz"]
    # Kok yumusama sinirindan ONCE kesiliyor: "önbellek" cekimlenince
    # "önbelleğinin" oluyor ve k -> ğ donusumu tam koku eslesmez yapiyor.
    # Bu testi ilk yazdigimda tam olarak buna takildi — projenin kendi
    # dersi (bkz. core/arac_secici.py).
    assert "önbelle" in mesaj
    assert "araç listesi" in mesaj


@pytest.mark.parametrize("okuma_sn,bekleniyor", [
    (2.0, False),   # uretimin (6 sn) yarisinin altinda: sessiz
    (4.0, True),    # yarisinin ustunde: uyari
])
def test_the_bottleneck_threshold_holds_from_both_sides(monkeypatch, okuma_sn, bekleniyor):
    """Sinir tek yandan sinanirsa kayabilir ve kimse fark etmez."""
    k = _cevap(monkeypatch, dict(
        SAGLIKLI, prompt_eval_count=4000,
        prompt_eval_duration=int(okuma_sn * NS)))
    assert ("darbogaz" in k) is bekleniyor


# ---------------- model yükleme ayrı bir şey ----------------

def test_a_cold_load_is_reported_separately(monkeypatch):
    """Model diskten yuklendiginde o tur digerlerine benzemiyor.

    Ayri raporlanmazsa "bir anda yavasladi" diye yanlis bir sonuca
    varilir; oysa sonraki turlar normale donuyor.
    """
    k = _cevap(monkeypatch, dict(SAGLIKLI, load_duration=8 * NS))
    assert k["model_yukleme_sn"] == 8.0


def test_a_warm_turn_does_not_mention_loading(monkeypatch):
    """keep_alive calisirken her turda "yukleme" gormek gurultu olurdu."""
    k = _cevap(monkeypatch, dict(SAGLIKLI, load_duration=NS // 100))
    assert "model_yukleme_sn" not in k


# ---------------- eski sürümler kırılmasın ----------------

def test_a_response_without_timings_does_not_crash(monkeypatch):
    """Eski Ollama surumleri bu alanlari gondermeyebilir."""
    k = _cevap(monkeypatch, {"message": {"content": "tamam"}})
    assert k["okunan_token"] == 0
    for alan in ("okuma_sn", "uretim_sn", "toplam_sn", "darbogaz"):
        assert alan not in k


def test_zero_durations_do_not_divide_by_zero(monkeypatch):
    k = _cevap(monkeypatch, {
        "message": {"content": "tamam"},
        "prompt_eval_count": 100, "prompt_eval_duration": 0,
        "eval_count": 10, "eval_duration": 0,
    })
    assert "okuma_token_sn" not in k
    assert "token_sn" not in k
