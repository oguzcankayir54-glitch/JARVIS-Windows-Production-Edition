"""Configuration loading, especially `.env` support.

Regression guard: env-backed fields must use ``default_factory``. With a plain
``os.getenv(...)`` default the value freezes at import time — before
``load_config()`` reads ``.env`` — so the file silently does nothing and a
correct API key looks missing.
"""
import os
from pathlib import Path

import pytest

from jarvis.config import Config, load_config

_ENV_KEYS = [
    "ELEVENLABS_API_KEY", "ELEVENLABS_VOICE_ID", "ELEVENLABS_MODEL_ID",
    "ELEVENLABS_OUTPUT_FORMAT", "ELEVENLABS_LANGUAGE_CODE",
    "ELEVENLABS_STABILITY", "ELEVENLABS_SIMILARITY_BOOST", "ELEVENLABS_STYLE",
    "ELEVENLABS_SPEAKER_BOOST", "ELEVENLABS_TIMEOUT", "ELEVENLABS_MAX_RETRIES",
    "JARVIS_TTS_PROVIDER", "JARVIS_XTTS_SPEAKER", "JARVIS_XTTS_SPEED",
    "JARVIS_XTTS_DEVICE", "JARVIS_XTTS_PRELOAD", "JARVIS_XTTS_READY_BEFORE_LISTEN",
    "JARVIS_XTTS_CACHE_SIZE",
    "JARVIS_XTTS_MODEL",
    "JARVIS_MONITOR_ENABLED", "JARVIS_MONITOR_INTERVAL",
    "JARVIS_MONITOR_HEALTH_INTERVAL", "JARVIS_MONITOR_COOLDOWN",
    "JARVIS_MONITOR_RECOVERY_SAMPLES", "JARVIS_MONITOR_RAM_WARNING",
    "JARVIS_MONITOR_RAM_CRITICAL", "JARVIS_MONITOR_DISK_WARNING",
    "JARVIS_MONITOR_DISK_CRITICAL", "JARVIS_MONITOR_GPU_TEMP_WARNING",
    "JARVIS_MONITOR_GPU_TEMP_CRITICAL", "JARVIS_MONITOR_VRAM_WARNING",
    "JARVIS_MONITOR_VRAM_CRITICAL",
    "JARVIS_SCREENSHOT_ENABLED",
    "JARVIS_APPROVAL_SOUND_ENABLED",
    "JARVIS_MULTI_AGENT_ENABLED", "JARVIS_MULTI_AGENT_MAX_DELEGATIONS",
    "JARVIS_OLLAMA_PRELOAD",
    "JARVIS_LLM_PROVIDER", "JARVIS_OLLAMA_MODEL", "JARVIS_NON_INTERACTIVE",
    "JARVIS_MAX_AGENT_STEPS", "JARVIS_DATA_DIR",
    "JARVIS_TEMPERATURE", "JARVIS_TOP_P", "JARVIS_REPEAT_PENALTY",
    "JARVIS_RAG_AUTO_PATHS", "JARVIS_RAG_SYNC_INTERVAL",
]


@pytest.fixture
def clean_env(monkeypatch, tmp_path):
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("JARVIS_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.chdir(tmp_path)
    return tmp_path


def test_dotenv_values_are_loaded(clean_env):
    (clean_env / ".env").write_text(
        "ELEVENLABS_API_KEY=sk_dosyadan_gelen_anahtar\n"
        "ELEVENLABS_VOICE_ID=voice_abc\n"
        "JARVIS_LLM_PROVIDER=ollama\n",
        encoding="utf-8",
    )
    cfg = load_config()
    assert cfg.elevenlabs_api_key == "sk_dosyadan_gelen_anahtar"
    assert cfg.elevenlabs_voice_id == "voice_abc"
    assert cfg.llm_provider == "ollama"
    assert cfg.voice_configured


def test_real_env_wins_over_dotenv(clean_env, monkeypatch):
    (clean_env / ".env").write_text("JARVIS_LLM_PROVIDER=ollama\n", encoding="utf-8")
    monkeypatch.setenv("JARVIS_LLM_PROVIDER", "mock")
    assert load_config().llm_provider == "mock"


def test_defaults_without_dotenv(clean_env):
    cfg = load_config()
    assert cfg.llm_provider == "mock"
    assert cfg.elevenlabs_api_key is None
    assert cfg.screenshot_enabled is False
    assert cfg.approval_sound_enabled is True
    assert cfg.multi_agent_enabled is False
    assert cfg.multi_agent_max_delegations == 1
    assert cfg.ollama_preload is False
    assert not cfg.voice_configured
    assert cfg.elevenlabs_model_id == "eleven_flash_v2_5"
    assert cfg.elevenlabs_output_format == "mp3_44100_128"
    assert cfg.elevenlabs_language_code == "tr"
    assert cfg.elevenlabs_stability == 0.50
    assert cfg.elevenlabs_similarity_boost == 0.75
    assert cfg.elevenlabs_speaker_boost is True
    assert cfg.tts_provider == "xtts"
    assert cfg.xtts_speaker == "Craig Gutsy"
    assert cfg.xtts_speed == 1.04
    assert cfg.xtts_preload is True
    assert cfg.xtts_ready_before_listen is True
    assert cfg.monitor_enabled is True
    assert cfg.monitor_ram_warning == 85.0
    assert cfg.monitor_ram_critical == 95.0


def test_dotenv_ignores_comments_and_quotes(clean_env):
    (clean_env / ".env").write_text(
        "# yorum satırı\n"
        "\n"
        'ELEVENLABS_VOICE_ID="tırnaklı_deger"\n',
        encoding="utf-8",
    )
    assert load_config().elevenlabs_voice_id == "tırnaklı_deger"


def test_each_config_instance_reads_current_env(monkeypatch):
    """Config() must not cache values from import time."""
    monkeypatch.setenv("JARVIS_OLLAMA_MODEL", "birinci")
    assert Config().ollama_model == "birinci"
    monkeypatch.setenv("JARVIS_OLLAMA_MODEL", "ikinci")
    assert Config().ollama_model == "ikinci"


def test_fallback_defaults_off_but_can_be_configured(monkeypatch):
    monkeypatch.delenv("JARVIS_OLLAMA_FALLBACK_MODEL", raising=False)
    assert Config().ollama_fallback_model == ""
    monkeypatch.setenv("JARVIS_OLLAMA_FALLBACK_MODEL", "qwen2.5:7b-instruct")
    assert Config().ollama_fallback_model == "qwen2.5:7b-instruct"


def test_data_dir_creates_directory(clean_env):
    cfg = load_config()
    assert cfg.data_dir.is_dir()
    assert cfg.memory_db_path.parent == cfg.data_dir


# ---------------- numeric settings ----------------

def test_comma_decimal_is_accepted(clean_env, monkeypatch):
    """A Turkish keyboard writes 0,96 — that must not stop the app starting."""
    monkeypatch.setenv("ELEVENLABS_SPEED", "0,96")
    assert load_config().elevenlabs_speed == 0.96


def test_unparsable_number_falls_back_instead_of_crashing(clean_env, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_SPEED", "hızlı")
    assert load_config().elevenlabs_speed == 1.0


def test_blank_number_uses_default(clean_env, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_SPEED", "   ")
    assert load_config().elevenlabs_speed == 1.0


def test_surrounding_whitespace_is_tolerated(clean_env, monkeypatch):
    monkeypatch.setenv("ELEVENLABS_SPEED", " 1.05 ")
    assert load_config().elevenlabs_speed == 1.05


def test_bad_step_count_does_not_crash(clean_env, monkeypatch):
    monkeypatch.setenv("JARVIS_MAX_AGENT_STEPS", "çok")
    assert load_config().max_agent_steps == 6


# ---------------- microphone ----------------

def test_stt_defaults(clean_env):
    cfg = load_config()
    assert cfg.stt_enabled is True
    assert cfg.stt_model == "small"
    assert cfg.stt_device == "auto"
    assert cfg.stt_language == "tr"


def test_stt_settings_come_from_dotenv(clean_env):
    (clean_env / ".env").write_text(
        "JARVIS_STT_MODEL=medium\nJARVIS_STT_DEVICE=cpu\nJARVIS_STT_ENABLED=false\n",
        encoding="utf-8",
    )
    cfg = load_config()
    assert (cfg.stt_model, cfg.stt_device) == ("medium", "cpu")
    assert cfg.stt_enabled is False


# ---------------- automatic knowledge sync ----------------

def test_rag_auto_sync_is_opt_in(clean_env):
    cfg = load_config()
    assert cfg.rag_auto_paths == ()
    assert cfg.rag_sync_interval == 60.0


def test_rag_auto_paths_are_expanded_and_empty_items_ignored(clean_env, monkeypatch):
    monkeypatch.setenv("JARVIS_RAG_AUTO_PATHS", "~/notlar, ,/srv/belgeler")
    monkeypatch.setenv("JARVIS_RAG_SYNC_INTERVAL", "2")
    cfg = load_config()
    assert [str(p) for p in cfg.rag_auto_paths] == [
        str(Path("~/notlar").expanduser()), str(Path("/srv/belgeler"))]
    assert cfg.rag_sync_interval == 10.0, "çok sık tarama sınırlandırılmalı"


# ---------------- sampling ----------------
#
# Ollama's own default is temperature 0.8, tuned for prose. That looseness is
# what mangles Turkish inflection: at every token the model is nudged toward a
# less likely word, and a wrong suffix wrecks the sentence rather than just
# colouring it.

def test_sampling_defaults_are_tighter_than_ollama(clean_env):
    cfg = load_config()
    assert cfg.temperature <= 0.5, "teknik asistan için 0.8 çok gevşek"
    assert 0.0 < cfg.top_p <= 1.0
    assert cfg.repeat_penalty >= 1.0


def test_sampling_can_be_tuned_from_dotenv(clean_env):
    (clean_env / ".env").write_text("JARVIS_TEMPERATURE=0,15\n", encoding="utf-8")
    assert load_config().temperature == 0.15      # virgüllü yazım da kabul


# ---------------- .env'i Windows'tan düzenlemek ----------------

def _yukle(tmp_path, ham: bytes, monkeypatch):
    from jarvis.config import _load_dotenv
    for anahtar in ("DENEME_ANAHTAR", "DENEME_IKINCI"):
        monkeypatch.delenv(anahtar, raising=False)
    yol = tmp_path / ".env"
    yol.write_bytes(ham)
    _load_dotenv(yol)
    return os.environ.get("DENEME_ANAHTAR"), os.environ.get("DENEME_IKINCI")


def test_a_bom_does_not_swallow_the_first_setting(tmp_path, monkeypatch):
    """Notepad can save a UTF-8 BOM, and it lands on the first line.

    That line is normally the API key. Read as plain utf-8 the key becomes
    "﻿ELEVENLABS_API_KEY" and never matches — silently, looking exactly
    like a key that was never set.
    """
    ham = b"\xef\xbb\xbfDENEME_ANAHTAR=deger\r\nDENEME_IKINCI=iki\r\n"
    assert _yukle(tmp_path, ham, monkeypatch) == ("deger", "iki")


def test_windows_line_endings_are_accepted(tmp_path, monkeypatch):
    ham = b"DENEME_ANAHTAR=deger\r\nDENEME_IKINCI=iki\r\n"
    assert _yukle(tmp_path, ham, monkeypatch) == ("deger", "iki")


def test_unix_line_endings_still_work(tmp_path, monkeypatch):
    ham = b"DENEME_ANAHTAR=deger\nDENEME_IKINCI=iki\n"
    assert _yukle(tmp_path, ham, monkeypatch) == ("deger", "iki")


def test_quotes_around_a_value_are_stripped(tmp_path, monkeypatch):
    ham = b'DENEME_ANAHTAR="deger"\r\nDENEME_IKINCI=\'iki\'\r\n'
    assert _yukle(tmp_path, ham, monkeypatch) == ("deger", "iki")


def test_a_mangled_byte_does_not_stop_jarvis_from_starting(tmp_path, monkeypatch):
    """A bad paste should fail as a rejected credential, not as a crash."""
    ham = b"DENEME_ANAHTAR=de\xffger\nDENEME_IKINCI=iki\n"
    anahtar, ikinci = _yukle(tmp_path, ham, monkeypatch)
    assert ikinci == "iki"
    assert anahtar and anahtar.startswith("de")
