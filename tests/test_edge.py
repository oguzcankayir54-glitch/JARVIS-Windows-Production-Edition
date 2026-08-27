"""Edge sesi: seçim sırası, hız çevrimi, ve hatanın ne dediği.

Hiçbir test Microsoft'a bağlanmıyor — ağ bir birim testinin bağımlılığı
olamaz. Denenen şey etrafı: hangi ayar hangi sağlayıcıya çıkıyor, kurulu
olmayan bir kütüphane "hazır" diyor mu, ve bir ağ hatası kullanıcının bir şey
yapabileceği cümleye dönüşüyor mu.

Sonuncusu bu projede iki kez ısırdı (OpenCV 5'te kamera, sonra Piper): bir
sağlayıcının ``available`` deyip ilk cümlede patlaması, panelde çalışmayan
bir düğme ve konuşmanın ortasında bir hata demek.
"""
import pytest

from jarvis.voice.edge import EdgeTTS, VARSAYILAN_SES, _yuzde, edge_hazir
from jarvis.voice.tts import TTSError, build_tts

ANAHTAR = "sk_" + "a" * 48


@pytest.fixture
def edge_var(monkeypatch):
    monkeypatch.setattr("jarvis.voice.edge.edge_hazir", lambda: "")


@pytest.fixture
def edge_yok(monkeypatch):
    monkeypatch.setattr("jarvis.voice.edge.edge_hazir",
                        lambda: ("Edge sesi için kütüphane kurulu değil.\n"
                                 "    pip install edge-tts"))


# ---------------- sağlayıcı seçimi ----------------

def test_edge_can_be_chosen_by_name(edge_var):
    assert build_tts(None, None, "m", provider="edge").name == "edge"


def test_edge_is_preferred_over_piper_when_nothing_is_chosen(edge_var, tmp_path):
    """Ölçüm karar verdi: 0.87'ye karşı 0.85, ve tonlama farkı daha büyük."""
    assert build_tts(None, None, "m", data_dir=str(tmp_path)).name == "edge"


def test_a_configured_key_still_wins_over_edge(edge_var):
    """Anahtarını girmiş biri ElevenLabs bekliyor; sessizce değişmemeli."""
    assert build_tts(ANAHTAR, "voice", "m").name == "elevenlabs"


def test_choosing_piper_explicitly_keeps_everything_local(edge_var, tmp_path):
    """'Metin makineden çıkmasın' tek ayarla söylenebilmeli."""
    secilen = build_tts(None, None, "m", provider="piper", data_dir=str(tmp_path))
    assert secilen.name != "edge"


def test_edge_without_the_library_is_not_reported_as_available(edge_yok):
    """Yetenek KURULURKEN denetleniyor, ilk cümlede değil."""
    saglayici = build_tts(None, None, "m", provider="edge")
    assert saglayici.available is False
    assert "edge-tts" in saglayici.reason


def test_a_missing_library_falls_through_to_piper(edge_yok, tmp_path):
    saglayici = build_tts(None, None, "m", data_dir=str(tmp_path))
    assert saglayici.name != "edge"


# ---------------- hız ----------------

@pytest.mark.parametrize("hiz,beklenen", [
    (1.0, "+0%"),
    (1.1, "+10%"),
    (0.9, "-10%"),
])
def test_speed_becomes_the_percentage_edge_expects(hiz, beklenen):
    assert _yuzde(hiz) == beklenen


def test_an_absurd_speed_is_clamped():
    assert _yuzde(9.0) == "+50%"
    assert _yuzde(0.01) == "-40%"


def test_a_broken_speed_setting_does_not_crash_speech():
    assert _yuzde("hızlı") == "+0%"      # type: ignore[arg-type]
    assert _yuzde(0) == "+0%"


def test_the_default_speed_is_natural():
    """Ölçümde +12% anlaşılırlığı 0.82'den 0.76'ya düşürdü."""
    assert EdgeTTS().rate == "+0%"


# ---------------- ses seçimi ----------------

def test_an_empty_voice_name_falls_back_to_the_default():
    assert EdgeTTS("").voice == VARSAYILAN_SES
    assert EdgeTTS("  ").voice == VARSAYILAN_SES


def test_a_chosen_voice_is_kept():
    assert EdgeTTS("tr-TR-EmelNeural").voice == "tr-TR-EmelNeural"


# ---------------- hatalar ----------------

def test_empty_text_is_refused():
    with pytest.raises(TTSError):
        list(EdgeTTS().synthesize("   "))


def test_synthesis_without_the_library_says_how_to_install_it(edge_yok):
    with pytest.raises(TTSError) as exc:
        list(EdgeTTS().synthesize("merhaba"))
    assert "pip install edge-tts" in str(exc.value)


@pytest.mark.parametrize("ham,aranan", [
    (OSError("[Errno -2] getaddrinfo failed"), "piper"),
    (RuntimeError("certificate verify failed"), "JARVIS_EDGE_CA"),
    (RuntimeError("Invalid response status 403"), "pip install -U edge-tts"),
])
def test_a_failure_says_what_to_do_about_it(ham, aranan):
    assert aranan in EdgeTTS._acikla(ham)


def test_an_unrecognised_failure_still_carries_its_message():
    assert "tuhaf bir şey" in EdgeTTS._acikla(RuntimeError("tuhaf bir şey"))


# ---------------- ses biçimi ----------------

def test_edge_declares_its_own_audio_type():
    """Sunucu türü sağlayıcıdan okuyor; sabit yazmak WAV'da sessizce bozardı."""
    assert EdgeTTS().mime == "audio/mpeg"


# ---------------- gerçek servis (isteğe bağlı) ----------------

@pytest.mark.skipif(not __import__("os").environ.get("JARVIS_EDGE_TEST"),
                    reason="ağ ister; JARVIS_EDGE_TEST=1 ile çalışır")
def test_real_edge_produces_playable_turkish_audio():
    """Gerçek servise bağlanır. Diğer her şey sahte veriyle sınanıyor."""
    if edge_hazir():
        pytest.skip("edge-tts kurulu değil")
    import os
    ses = EdgeTTS(ca_bundle=os.environ.get("JARVIS_EDGE_CA", ""))
    try:
        ham = b"".join(ses.synthesize("Sistem hazır efendim."))
    except TTSError as exc:
        pytest.skip(f"servise ulaşılamadı: {exc}")
    assert len(ham) > 1000
    # MP3: ya ID3 etiketi ya da bir çerçeve senkron baytı ile başlar.
    assert ham[:3] == b"ID3" or ham[0] == 0xFF
