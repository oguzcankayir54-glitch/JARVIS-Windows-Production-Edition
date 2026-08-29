"""Free local speech: provider selection, and what Piper does when it can't.

The binary and the 63 MB voice model are not test dependencies. What is
tested is everything around them — which provider a configuration resolves
to, what the failures say, and that the audio format travels with the
provider instead of being assumed.

That last one is the bug this layer could most easily have shipped: the
server used to hardcode ``audio/mpeg``, which was true for ElevenLabs and
silently wrong for Piper's WAV.
"""
import subprocess
from pathlib import Path

import pytest

from jarvis.voice.piper import PiperTTS, VARSAYILAN_SES, indirme_yolu, piper_modeli, ses_klasoru
from jarvis.voice.tts import NullTTS, TTSError, build_tts

ANAHTAR = "sk_" + "a" * 48


@pytest.fixture
def edge_yok(monkeypatch):
    """Edge kurulu değilmiş gibi davran.

    Sıralama testleri Edge'in kurulu olup olmamasına göre farklı cevap
    verirdi; hangisinin sınandığı açık olmalı.
    """
    monkeypatch.setattr("jarvis.voice.edge.edge_hazir",
                        lambda: ("Edge sesi için kütüphane kurulu değil.\n"
                                 "    pip install edge-tts"))


@pytest.fixture
def hazir(tmp_path, monkeypatch, edge_yok):
    """Kurulu bir Piper: ikili yerinde, model ve yapılandırma dosyası var.

    Gerçek ikiliye ve 63 MB'lık modele bağlanmamak için sahte. Denenen şey
    zaten Piper'ın ses kalitesi değil, etrafındaki seçim mantığı.
    """
    monkeypatch.setattr("shutil.which", lambda ad: "/usr/bin/piper")
    sesler = tmp_path / "sesler"
    sesler.mkdir()
    (sesler / f"{VARSAYILAN_SES}.onnx").write_bytes(b"sahte")
    (sesler / f"{VARSAYILAN_SES}.onnx.json").write_text("{}")
    return str(tmp_path)


# ---------------- sağlayıcı seçimi ----------------

def test_no_key_and_no_choice_lands_on_the_free_provider(hazir):
    """Ücretsiz yol varsayılan olmalı: ses için kimse anahtar aramak zorunda değil."""
    assert build_tts(None, None, "m", data_dir=hazir).name == "piper"


def test_a_configured_key_still_wins_when_nothing_is_chosen():
    """Mevcut kurulumlar aynı sesle çalmaya devam etmeli."""
    assert build_tts(ANAHTAR, "voice", "m").name == "elevenlabs"


def test_piper_can_be_chosen_even_with_a_key_present(hazir):
    """Kredi bitmesin diye anahtarı silmek zorunda kalmamalı."""
    secilen = build_tts(ANAHTAR, "voice", "m", provider="piper", data_dir=hazir)
    assert secilen.name == "piper"


def test_speech_can_be_switched_off_entirely():
    saglayici = build_tts(ANAHTAR, "voice", "m", provider="yok")
    assert saglayici.available is False
    with pytest.raises(TTSError) as exc:
        saglayici.synthesize("merhaba")
    assert "kapalı" in str(exc.value)


def test_choosing_elevenlabs_without_a_key_names_what_is_missing():
    saglayici = build_tts(None, None, "m", provider="elevenlabs")
    assert saglayici.available is False
    assert "ELEVENLABS_API_KEY" in saglayici.reason


def test_an_unknown_provider_lists_the_valid_ones():
    saglayici = build_tts(None, None, "m", provider="saçma")
    assert saglayici.available is False
    for ad in ("xtts", "edge", "piper", "elevenlabs"):
        assert ad in saglayici.reason


# ---------------- ses biçimi ----------------

def test_each_provider_declares_its_own_audio_type(hazir):
    """Sunucu türü sağlayıcıdan alıyor; sabit yazmak WAV'da sessizce bozardı."""
    assert build_tts(None, None, "m", provider="piper", data_dir=hazir).mime == "audio/wav"
    assert build_tts(ANAHTAR, "v", "m").mime == "audio/mpeg"
    assert NullTTS().mime


def test_the_panel_serves_the_providers_own_type():
    import inspect

    from jarvis.web import server
    kaynak = inspect.getsource(server)
    assert 'getattr(server.tts, "mime"' in kaynak, "tür sağlayıcıdan okunmalı"


# ---------------- model yolu ----------------

def test_a_bare_name_is_looked_up_in_the_voices_folder(tmp_path):
    yol = piper_modeli("tr_TR-dfki-medium", tmp_path)
    assert yol == tmp_path / "sesler" / "tr_TR-dfki-medium.onnx"


def test_a_path_is_taken_as_given(tmp_path):
    """Başka yere indirilmiş bir ses de kullanılabilmeli."""
    hedef = tmp_path / "baska" / "ses.onnx"
    assert piper_modeli(str(hedef), tmp_path) == hedef


def test_an_empty_name_falls_back_to_the_default(tmp_path):
    assert piper_modeli("", tmp_path).name == f"{VARSAYILAN_SES}.onnx"


def test_the_download_path_is_built_from_the_voice_name():
    """tr_TR-dfki-medium → tr/tr_TR/dfki/medium"""
    yol = indirme_yolu("tr_TR-dfki-medium")
    assert yol.endswith("/tr/tr_TR/dfki/medium")


def test_an_unparsable_voice_name_says_so():
    with pytest.raises(TTSError):
        indirme_yolu("bozukad")


def test_the_voices_folder_sits_under_the_data_directory(tmp_path):
    assert ses_klasoru(tmp_path) == tmp_path / "sesler"


# ---------------- hatalar ----------------

def test_a_missing_model_says_how_to_get_one(tmp_path):
    tts = PiperTTS(tmp_path / "yok.onnx")
    with pytest.raises(TTSError) as exc:
        list(tts.synthesize("merhaba"))
    assert "--piper-kur" in str(exc.value)


def test_a_missing_config_file_is_named(tmp_path):
    """Model tek başına yetmiyor; .onnx.json olmadan piper başlamıyor."""
    model = tmp_path / "ses.onnx"
    model.write_bytes(b"sahte")
    tts = PiperTTS(model)
    with pytest.raises(TTSError) as exc:
        list(tts.synthesize("merhaba"))
    assert ".onnx.json" in str(exc.value) or "yapılandırma" in str(exc.value)


def test_a_missing_binary_says_how_to_install_it(tmp_path):
    model = tmp_path / "ses.onnx"
    model.write_bytes(b"sahte")
    (tmp_path / "ses.onnx.json").write_text("{}")
    tts = PiperTTS(model, binary="boyle-bir-program-yok")
    with pytest.raises(TTSError) as exc:
        list(tts.synthesize("merhaba"))
    assert "pip install piper-tts" in str(exc.value)


def test_empty_text_is_refused(tmp_path):
    with pytest.raises(TTSError):
        list(PiperTTS(tmp_path / "ses.onnx").synthesize("   "))


def test_output_that_is_not_wav_is_rejected(tmp_path, monkeypatch):
    """Sessizce bozuk ses yollamaktansa hata vermek iyi."""
    model = tmp_path / "ses.onnx"
    model.write_bytes(b"sahte")
    (tmp_path / "ses.onnx.json").write_text("{}")

    class _Sahte:
        returncode = 0

        def communicate(self, girdi, timeout=None):
            return b"bu WAV degil", b""

    monkeypatch.setattr("shutil.which", lambda ad: "/usr/bin/piper")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _Sahte())
    with pytest.raises(TTSError) as exc:
        list(PiperTTS(model).synthesize("merhaba"))
    assert "WAV" in str(exc.value)


def test_new_piper_writes_directly_to_a_named_file(tmp_path, monkeypatch):
    model = tmp_path / "ses.onnx"
    model.write_bytes(b"sahte")
    (tmp_path / "ses.onnx.json").write_text("{}")
    calls = []

    class _Sahte:
        returncode = 0

        def __init__(self, command):
            self.command = command

        def communicate(self, girdi, timeout=None):
            calls.append(self.command)
            output = self.command[self.command.index("-f") + 1]
            assert output != "-"
            Path(output).write_bytes(b"RIFF" + b"x" * 20)
            return b"", b""

    monkeypatch.setattr("shutil.which", lambda ad: "/usr/bin/piper")
    monkeypatch.setattr(subprocess, "Popen", lambda command, **k: _Sahte(command))
    assert b"".join(PiperTTS(model).synthesize("merhaba")).startswith(b"RIFF")
    assert len(calls) == 1


def test_a_piper_failure_carries_its_last_line(tmp_path, monkeypatch):
    model = tmp_path / "ses.onnx"
    model.write_bytes(b"sahte")
    (tmp_path / "ses.onnx.json").write_text("{}")

    class _Sahte:
        returncode = 1

        def communicate(self, girdi, timeout=None):
            return b"", b"uyari satiri\nasil sebep burada"

    monkeypatch.setattr("shutil.which", lambda ad: "/usr/bin/piper")
    monkeypatch.setattr(subprocess, "Popen", lambda *a, **k: _Sahte())
    with pytest.raises(TTSError) as exc:
        list(PiperTTS(model).synthesize("merhaba"))
    assert "asil sebep burada" in str(exc.value)


# ---------------- hız ----------------

def test_speed_is_inverted_for_piper(tmp_path):
    """Piper'ın ölçüsü ters: length_scale büyüdükçe ses yavaşlıyor."""
    tts = PiperTTS(tmp_path / "ses.onnx", speed=2.0)
    komut = tts._komut()
    olcek = float(komut[komut.index("--length-scale") + 1])
    assert olcek == pytest.approx(0.5)


def test_an_absurd_speed_is_clamped(tmp_path):
    assert PiperTTS(tmp_path / "s.onnx", speed=99).speed == 2.0
    assert PiperTTS(tmp_path / "s.onnx", speed=0.01).speed == 0.5
    assert PiperTTS(tmp_path / "s.onnx", speed=0).speed == 1.0


def test_gpu_is_only_requested_when_asked(tmp_path):
    assert "--cuda" not in PiperTTS(tmp_path / "s.onnx")._komut()
    assert "--cuda" in PiperTTS(tmp_path / "s.onnx", cuda=True)._komut()


# ---------------- gerçek piper (varsa) ----------------

def _gercek_piper(tmp_path_factory):
    import shutil
    if shutil.which("piper") is None:
        pytest.skip("piper kurulu değil")
    model = piper_modeli(VARSAYILAN_SES, Path("~/.jarvis"))
    if not model.is_file():
        pytest.skip("Türkçe ses modeli indirilmemiş (jarvis-ses --piper-kur)")
    return model


def test_real_piper_produces_playable_turkish_audio(tmp_path_factory):
    import io
    import wave
    model = _gercek_piper(tmp_path_factory)
    ham = b"".join(PiperTTS(model).synthesize("Anakartın ışığı yanıyor efendim."))
    ses = wave.open(io.BytesIO(ham))
    assert ses.getnframes() > 0
    assert ses.getframerate() >= 16000


# ---------------- hazır olmayan kurulum ----------------
# Kamera katmanı bu hatayı bir kez yaptı: "kurulu ama çalışmıyor" durumu
# available=True diyordu, panel çalışmayan bir düğme gösteriyordu ve hata
# konuşmanın ortasında çıkıyordu. Ses katmanı aynısını yapmamalı.

def test_piper_without_the_binary_is_not_reported_as_available(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda ad: None)
    saglayici = build_tts(None, None, "m", provider="piper", data_dir=str(tmp_path))
    assert saglayici.available is False
    assert "pip install piper-tts" in saglayici.reason


def test_piper_without_the_model_is_not_reported_as_available(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda ad: "/usr/bin/piper")
    saglayici = build_tts(None, None, "m", provider="piper", data_dir=str(tmp_path))
    assert saglayici.available is False
    assert "--piper-kur" in saglayici.reason


def test_a_model_without_its_config_is_not_reported_as_available(tmp_path, monkeypatch):
    monkeypatch.setattr("shutil.which", lambda ad: "/usr/bin/piper")
    sesler = tmp_path / "sesler"
    sesler.mkdir()
    (sesler / f"{VARSAYILAN_SES}.onnx").write_bytes(b"sahte")
    saglayici = build_tts(None, None, "m", provider="piper", data_dir=str(tmp_path))
    assert saglayici.available is False
    assert ".onnx.json" in saglayici.reason


def test_a_ready_piper_is_available(hazir):
    saglayici = build_tts(None, None, "m", provider="piper", data_dir=hazir)
    assert saglayici.available is True and saglayici.name == "piper"


# ---------------- kurulum ayarı da yazsın ----------------
# Bu adım iki kez atlandı ve her seferinde "ses hâlâ ElevenLabs" olarak geri
# döndü. Modeli indirip ayarı kullanıcıya bırakmak, işin yarısını bırakmaktır.

def test_the_setting_is_written_into_a_fresh_env(tmp_path, monkeypatch):
    from jarvis.voice.cli import _env_ayarla
    monkeypatch.chdir(tmp_path)
    assert _env_ayarla("JARVIS_TTS_PROVIDER", "piper")
    assert "JARVIS_TTS_PROVIDER=piper" in (tmp_path / ".env").read_text(encoding="utf-8")


def test_an_existing_value_is_replaced_not_appended(tmp_path, monkeypatch):
    """İkinci bir satır, geçerli değeri okuma sırasına bağlı kılardı."""
    from jarvis.voice.cli import _env_ayarla
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "ELEVENLABS_API_KEY=sk_x\nJARVIS_TTS_PROVIDER=elevenlabs\n", encoding="utf-8")
    _env_ayarla("JARVIS_TTS_PROVIDER", "piper")
    metin = (tmp_path / ".env").read_text(encoding="utf-8")
    assert metin.count("JARVIS_TTS_PROVIDER") == 1
    assert "JARVIS_TTS_PROVIDER=piper" in metin


def test_the_rest_of_the_file_survives(tmp_path, monkeypatch):
    from jarvis.voice.cli import _env_ayarla
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text(
        "# yorum\nELEVENLABS_API_KEY=sk_x\nJARVIS_LLM_PROVIDER=ollama\n", encoding="utf-8")
    _env_ayarla("JARVIS_TTS_PROVIDER", "piper")
    metin = (tmp_path / ".env").read_text(encoding="utf-8")
    for satir in ("# yorum", "ELEVENLABS_API_KEY=sk_x", "JARVIS_LLM_PROVIDER=ollama"):
        assert satir in metin


def test_a_commented_out_key_is_left_alone(tmp_path, monkeypatch):
    from jarvis.voice.cli import _env_ayarla
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_text("# JARVIS_TTS_PROVIDER=eski\n", encoding="utf-8")
    _env_ayarla("JARVIS_TTS_PROVIDER", "piper")
    metin = (tmp_path / ".env").read_text(encoding="utf-8")
    assert "# JARVIS_TTS_PROVIDER=eski" in metin
    assert "JARVIS_TTS_PROVIDER=piper" in metin


def test_a_bom_written_env_is_read_back_correctly(tmp_path, monkeypatch):
    """Not Defteri'yle düzenlenmiş bir .env'i bozmadan güncelleyebilmeli."""
    from jarvis.voice.cli import _env_ayarla
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".env").write_bytes(
        "﻿ELEVENLABS_API_KEY=sk_x\r\n".encode("utf-8"))
    _env_ayarla("JARVIS_TTS_PROVIDER", "piper")
    metin = (tmp_path / ".env").read_text(encoding="utf-8-sig")
    assert "ELEVENLABS_API_KEY=sk_x" in metin
    assert "JARVIS_TTS_PROVIDER=piper" in metin
