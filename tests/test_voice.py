"""TTS layer. No network and no API key: HTTP is stubbed throughout."""
import io
import urllib.error

import pytest

from jarvis.config import Config
from jarvis.voice import tts as tts_mod
from jarvis.voice.tts import ElevenLabsTTS, NullTTS, TTSError, build_tts, save_stream


class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


@pytest.fixture
def fake_audio(monkeypatch):
    """Stub urlopen so synthesize() yields deterministic bytes."""
    captured = {}

    def fake_urlopen(req, timeout=None):
        captured["url"] = req.full_url
        captured["headers"] = {k.lower(): v for k, v in req.headers.items()}
        captured["body"] = req.data
        return _FakeResponse(b"AUDIO" * 3000)

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", fake_urlopen)
    return captured


def test_build_tts_without_key_does_not_reach_for_elevenlabs(monkeypatch):
    """Anahtarsızken ElevenLabs seçilmemeli — ücretsiz yollardan biri seçilir.

    Hangisi olduğu kurulu olanlara bağlı (edge → piper → hiçbiri), o yüzden
    burada sınanan tek şey ElevenLabs OLMAMASI. Sıralamanın kendisi
    tests/test_edge.py ve tests/test_piper.py içinde, kurulum sahtelenerek
    sınanıyor.
    """
    assert build_tts(None, None, "m").name != "elevenlabs"
    assert build_tts("key", None, "m").name != "elevenlabs"


def test_speech_can_always_be_switched_off():
    assert isinstance(build_tts("key", "voice", "m", provider="yok"), NullTTS)


def test_null_tts_raises_helpful_error():
    with pytest.raises(TTSError, match="ELEVENLABS_API_KEY"):
        list(NullTTS().synthesize("merhaba"))


def test_synthesize_streams_chunks(fake_audio):
    tts = ElevenLabsTTS("sk_test", "voice1", "eleven_multilingual_v2")
    chunks = list(tts.synthesize("merhaba"))
    assert len(chunks) > 1, "ses parça parça akmalı (tek seferde değil)"
    assert b"".join(chunks) == b"AUDIO" * 3000


def test_request_targets_stream_endpoint_with_key(fake_audio):
    ElevenLabsTTS("sk_test", "voice1", "eleven_multilingual_v2")._api_key  # noqa: B018
    list(ElevenLabsTTS("sk_test", "voice1", "m").synthesize("selam"))
    assert "/text-to-speech/voice1/stream?" in fake_audio["url"]
    assert "output_format=mp3_44100_128" in fake_audio["url"]
    assert fake_audio["headers"]["xi-api-key"] == "sk_test"




def test_flash_payload_forces_turkish_and_voice_settings(fake_audio):
    tts = ElevenLabsTTS(
        "sk_test", "voice1", "eleven_flash_v2_5",
        stability=0.42, similarity_boost=0.81, style=0.0,
        speaker_boost=True, speed=1.05, max_retries=0,
    )
    list(tts.synthesize("Merhaba efendim."))
    body = __import__("json").loads(fake_audio["body"].decode("utf-8"))
    assert body["language_code"] == "tr"
    assert body["voice_settings"] == {
        "stability": 0.42, "style": 0.0, "speed": 1.05,
        "similarity_boost": 0.81, "use_speaker_boost": True,
    }


def test_v3_does_not_send_unsupported_similarity_controls(fake_audio):
    tts = ElevenLabsTTS("sk_test", "voice1", "eleven_v3", max_retries=0)
    list(tts.synthesize("Merhaba."))
    body = __import__("json").loads(fake_audio["body"].decode("utf-8"))
    settings = body["voice_settings"]
    assert "similarity_boost" not in settings
    assert "use_speaker_boost" not in settings
    assert body["language_code"] == "tr"


def test_invalid_output_format_is_rejected_before_network():
    with pytest.raises(TTSError, match="output format"):
        ElevenLabsTTS("sk", "v", "m", output_format="../../secret")

def test_empty_text_makes_no_request(fake_audio):
    assert list(ElevenLabsTTS("sk_test", "v", "m").synthesize("   ")) == []
    assert "url" not in fake_audio


def test_missing_credentials_rejected():
    with pytest.raises(TTSError):
        ElevenLabsTTS("", "voice1", "m")
    with pytest.raises(TTSError):
        ElevenLabsTTS("sk", "", "m")


@pytest.mark.parametrize("code,parca", [
    (401, "geçersiz"), (404, "Voice ID"), (429, "kota"),
])
def test_http_errors_become_readable_messages(monkeypatch, code, parca):
    def raise_http(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, code, "err", {}, None)

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", raise_http)
    with pytest.raises(TTSError, match=parca):
        list(ElevenLabsTTS("sk", "v", "m").synthesize("merhaba"))


def test_network_failure_is_wrapped(monkeypatch):
    def boom(req, timeout=None):
        raise urllib.error.URLError("ağ yok")

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", boom)
    with pytest.raises(TTSError, match="ulaşılamadı"):
        list(ElevenLabsTTS("sk", "v", "m").synthesize("merhaba"))


# ---------------- voice lookup ----------------
#
# Regression guard: verification used to list every voice on the account. That
# response grew big enough to sit in resp.read() for minutes, which reads as a
# frozen command rather than a slow one.

@pytest.fixture
def fake_json(monkeypatch):
    """Stub urlopen for the JSON endpoints, recording every URL requested."""
    çağrılar: list[str] = []
    yanıtlar: list[bytes] = []

    def fake_urlopen(req, timeout=None):
        çağrılar.append(req.full_url)
        return _FakeResponse(yanıtlar.pop(0) if yanıtlar else b"{}")

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", fake_urlopen)
    return çağrılar, yanıtlar


def test_voice_info_asks_only_for_the_configured_voice(fake_json):
    çağrılar, yanıtlar = fake_json
    yanıtlar.append(b'{"voice_id": "voice1", "name": "J.A.R.V.I.S"}')
    bilgi = ElevenLabsTTS("sk", "voice1", "m").voice_info("voice1")
    assert bilgi == {"voice_id": "voice1", "name": "J.A.R.V.I.S"}
    assert len(çağrılar) == 1
    assert çağrılar[0].endswith("/v1/voices/voice1"), "tüm liste indirilmemeli"


def test_voice_info_escapes_the_id(fake_json):
    çağrılar, yanıtlar = fake_json
    yanıtlar.append(b'{"name": "x"}')
    ElevenLabsTTS("sk", "v", "m").voice_info("a/b?c")
    assert "a%2Fb%3Fc" in çağrılar[0]


def test_bad_key_is_reported_by_voice_info(monkeypatch):
    def raise_http(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "err", {}, None)

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", raise_http)
    with pytest.raises(TTSError, match="geçersiz"):
        ElevenLabsTTS("sk", "v", "m").voice_info("v")


def test_wrong_voice_id_is_reported_by_voice_info(monkeypatch):
    def raise_http(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 404, "err", {}, None)

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", raise_http)
    with pytest.raises(TTSError, match="Voice ID"):
        ElevenLabsTTS("sk", "v", "m").voice_info("v")


def test_voices_listing_is_paged(fake_json):
    """The unpaged endpoint can return the whole shared library."""
    çağrılar, yanıtlar = fake_json
    yanıtlar.append(b'{"voices": [{"voice_id": "a", "name": "Bir"}], '
                    b'"has_more": true, "next_page_token": "tok2"}')
    yanıtlar.append(b'{"voices": [{"voice_id": "b", "name": "Iki"}], "has_more": false}')
    sesler = ElevenLabsTTS("sk", "v", "m").voices()
    assert [s["name"] for s in sesler] == ["Bir", "Iki"]
    assert "page_size=100" in çağrılar[0]
    assert "next_page_token=tok2" in çağrılar[1]


def test_voices_listing_stops_at_the_limit(fake_json):
    çağrılar, yanıtlar = fake_json
    yanıtlar.append(b'{"voices": [{"voice_id": "a", "name": "Bir"}, '
                    b'{"voice_id": "b", "name": "Iki"}], '
                    b'"has_more": true, "next_page_token": "tok2"}')
    sesler = ElevenLabsTTS("sk", "v", "m").voices(limit=2)
    assert len(sesler) == 2
    assert len(çağrılar) == 1, "sınıra ulaşınca durmalı"
    assert "page_size=2" in çağrılar[0]


def test_voices_listing_stops_when_the_token_runs_out(fake_json):
    """has_more without a token would otherwise loop forever."""
    çağrılar, yanıtlar = fake_json
    yanıtlar.append(b'{"voices": [{"voice_id": "a", "name": "Bir"}], "has_more": true}')
    assert len(ElevenLabsTTS("sk", "v", "m").voices()) == 1
    assert len(çağrılar) == 1


# ---------------- quota ----------------
#
# A valid key with no credits left fails at synthesis with the same 401 a bad
# key returns. That cost a real debugging session, so the number is read up
# front — but never at the price of blocking a setup that otherwise works.

def test_quota_reports_what_is_left(fake_json):
    çağrılar, yanıtlar = fake_json
    yanıtlar.append(b'{"character_count": 2500, "character_limit": 10000, "tier": "free"}')
    assert ElevenLabsTTS("sk", "v", "m").quota() == {
        "used": 2500, "limit": 10000, "left": 7500, "tier": "free"}
    assert çağrılar[0].endswith("/v1/user/subscription")


def test_exhausted_quota_reports_zero_not_negative(fake_json):
    _, yanıtlar = fake_json
    yanıtlar.append(b'{"character_count": 10500, "character_limit": 10000}')
    assert ElevenLabsTTS("sk", "v", "m").quota()["left"] == 0


def test_quota_is_none_when_the_key_may_not_ask(monkeypatch):
    """Scoped keys can be denied this endpoint; that is not a broken setup."""
    def raise_http(req, timeout=None):
        raise urllib.error.HTTPError(req.full_url, 401, "err", {}, None)

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", raise_http)
    assert ElevenLabsTTS("sk", "v", "m").quota() is None


def test_quota_is_none_on_unexpected_shape(fake_json):
    _, yanıtlar = fake_json
    yanıtlar.append(b'{"tier": "free"}')
    assert ElevenLabsTTS("sk", "v", "m").quota() is None


def test_malformed_json_is_reported_not_raised_raw(fake_json):
    _, yanıtlar = fake_json
    yanıtlar.append(b"<html>bakim</html>")
    with pytest.raises(TTSError, match="beklenmeyen"):
        ElevenLabsTTS("sk", "v", "m").voice_info("v")


def test_save_stream_writes_file(tmp_path):
    target = save_stream(iter([b"ab", b"cd"]), tmp_path / "ses.mp3")
    assert target.read_bytes() == b"abcd"


# ---------------- secret handling ----------------

def test_key_is_masked_not_exposed():
    key = "sk_abcdefghijklmnop"          # 19 karakter
    cfg = Config(elevenlabs_api_key=key, elevenlabs_voice_id="v")
    masked = cfg.masked_key()
    assert key not in masked, "maskelenmiş çıktı anahtarın tamamını içermemeli"
    assert masked == f"sk_a…mnop ({len(key)} karakter)"


def test_masked_key_when_absent():
    assert Config(elevenlabs_api_key=None).masked_key() == "(yok)"


def test_voice_configured_requires_both():
    assert not Config(elevenlabs_api_key="k", elevenlabs_voice_id=None).voice_configured
    assert Config(elevenlabs_api_key="k", elevenlabs_voice_id="v").voice_configured


def test_key_not_in_repr_of_provider():
    # A stack trace or log line must not leak the key through the object.
    tts = ElevenLabsTTS("sk_supersecret_value", "v", "m")
    assert "sk_supersecret_value" not in repr(tts)


# ---------------- error detail surfacing ----------------

class _HTTPErrorWithBody(urllib.error.HTTPError):
    def __init__(self, code, body: bytes):
        super().__init__("http://x", code, "err", {}, None)
        self._body = body

    def read(self):
        return self._body


def test_api_error_message_is_surfaced(monkeypatch):
    """A bare status code hides a fixable problem; the API explains it."""
    def raise_http(req, timeout=None):
        raise _HTTPErrorWithBody(400, b'{"detail":{"message":"Invalid API key format"}}')

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", raise_http)
    with pytest.raises(TTSError, match="Invalid API key format"):
        list(ElevenLabsTTS("sk", "v", "m").synthesize("merhaba"))


def test_400_explains_likely_cause(monkeypatch):
    def raise_http(req, timeout=None):
        raise _HTTPErrorWithBody(400, b"")

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", raise_http)
    with pytest.raises(TTSError, match="görünmez bir karakter"):
        list(ElevenLabsTTS("sk", "v", "m").synthesize("merhaba"))


def test_unreadable_body_does_not_break_error(monkeypatch):
    def raise_http(req, timeout=None):
        raise _HTTPErrorWithBody(500, b"\xff\xfe not json")

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", raise_http)
    with pytest.raises(TTSError, match="HTTP 500"):
        list(ElevenLabsTTS("sk", "v", "m").synthesize("merhaba"))


# ---------------- key health ----------------

#: Doğru uzunlukta, temiz bir örnek anahtar (gerçek değil).
_TEMIZ_ANAHTAR = "sk_" + "a" * 48


@pytest.mark.parametrize("key,beklenen", [
    (_TEMIZ_ANAHTAR, []),
    (_TEMIZ_ANAHTAR + " ", ["başında/sonunda boşluk var"]),
    (" " + _TEMIZ_ANAHTAR, ["başında/sonunda boşluk var"]),
    ("sk_türkçe" + "a" * 42, ["ASCII olmayan karakter içeriyor"]),
    ('"' + _TEMIZ_ANAHTAR + '"', ["tırnak işareti içeriyor (gerekmez)"]),
])
def test_key_health_flags_invisible_damage(key, beklenen):
    from jarvis.voice.cli import _key_health
    problems = _key_health(key)
    for b in beklenen:
        assert any(b.split(":")[0] in p for p in problems), f"{key!r} → {problems}"
    if not beklenen:
        assert problems == []


def test_key_health_catches_embedded_newline():
    from jarvis.voice.cli import _key_health
    assert _key_health("sk_abc\rdef"), "satır sonu yakalanmalı"


def test_key_health_flags_wrong_length():
    """The API rejects a wrong-length key; catch it before the request."""
    from jarvis.voice.cli import _ELEVENLABS_KEY_LEN, _key_health
    dogru = "sk_" + "a" * (_ELEVENLABS_KEY_LEN - 3)
    assert _key_health(dogru) == []

    fazla = dogru + "x"
    assert any("uzunluk 52" in p for p in _key_health(fazla))
    assert any("fazla" in p for p in _key_health(fazla))

    eksik = dogru[:-1]
    assert any("1 karakter eksik" in p for p in _key_health(eksik))


def test_key_health_ignores_length_for_other_formats():
    """Only sk_ keys are length-checked; another provider's format is left alone."""
    from jarvis.voice.cli import _key_health
    assert _key_health("baska-format-anahtar") == []


# ---------------- speech normalisation ----------------

@pytest.mark.parametrize("yazili,soylenen", [
    ("J.A.R.V.I.S. hazır.", "Jarvis hazır."),
    ("J.A.R.V.I.S hazır.", "Jarvis hazır."),
    ("JARVIS hazır.", "Jarvis hazır."),
    ("j.a.r.v.i.s. hazır.", "Jarvis hazır."),
])
def test_dotted_name_is_spoken_as_a_word(yazili, soylenen):
    """Dots make the synthesiser spell the name out letter by letter."""
    from jarvis.voice.tts import normalize_for_speech
    assert normalize_for_speech(yazili) == soylenen


@pytest.mark.parametrize("yazili,soylenen", [
    ("**önemli** nokta", "önemli nokta"),
    ("`kod` örneği", "kod örneği"),
    ("## Başlık", "Başlık"),
    ("*vurgu* var", "vurgu var"),
])
def test_markdown_markers_are_not_read_aloud(yazili, soylenen):
    from jarvis.voice.tts import normalize_for_speech
    assert normalize_for_speech(yazili) == soylenen


def test_normalisation_leaves_ordinary_text_alone():
    """Kısaltma geçmeyen bir cümleye hiç dokunulmamalı."""
    from jarvis.voice.tts import normalize_for_speech
    metin = "İşlemci sıcaklığı 62 derece, bellek kullanımı %47."
    assert normalize_for_speech(metin) == metin


def test_abbreviations_are_read_aloud_the_turkish_way():
    """Bu cümle eskiden olduğu gibi geçiyordu ve "boz" diye okunuyordu.

    Kısaltmaların okunuşa çevrilmesi bilerek yapılan bir değişiklik;
    ayrıntısı ve ölçümü jarvis/voice/soyleyis.py içinde.
    """
    from jarvis.voice.tts import normalize_for_speech
    sonuc = normalize_for_speech("CPU sıcaklığı 62 derece, RAM kullanımı %47.")
    assert "işlemci" in sonuc and "ram" in sonuc


@pytest.mark.parametrize("istenen,beklenen", [(0.92, 0.92), (0.3, 0.7), (2.0, 1.2)])
def test_speed_is_clamped_to_api_range(istenen, beklenen):
    """A value outside the accepted range would make the API reject the request."""
    assert ElevenLabsTTS("sk", "v", "m", speed=istenen).speed == beklenen


def test_speed_is_sent_in_voice_settings(fake_audio):
    import json as _json
    list(ElevenLabsTTS("sk", "v", "m", speed=0.85).synthesize("merhaba"))
    ayarlar = _json.loads(fake_audio["body"])["voice_settings"]
    assert ayarlar["speed"] == 0.85


def test_normalised_text_is_what_gets_sent(fake_audio):
    """The transcript keeps the stylised spelling; only speech changes."""
    import json as _json
    list(ElevenLabsTTS("sk", "v", "m").synthesize("J.A.R.V.I.S. burada."))
    gonderilen = _json.loads(fake_audio["body"])["text"]
    assert gonderilen == "Jarvis burada."


@pytest.mark.parametrize("govde,beklenen", [
    (b'{"detail":{"message":"This request exceeds your quota of 10000. You have 0 credits remaining"}}',
     "krediniz bitti"),
    (b'{"detail":{"message":"Invalid API key"}}', "anahtarı geçersiz"),
])
def test_401_distinguishes_quota_from_bad_key(monkeypatch, govde, beklenen):
    """ElevenLabs returns 401 for both; the wrong message sends you to fix the wrong thing."""
    def raise_http(req, timeout=None):
        raise _HTTPErrorWithBody(401, govde)

    monkeypatch.setattr(tts_mod.urllib.request, "urlopen", raise_http)
    with pytest.raises(TTSError, match=beklenen):
        list(ElevenLabsTTS("sk", "v", "m").synthesize("merhaba"))


# ---------------- anahtar teşhisi ----------------
# "Anahtarı yeniden kopyalayın" bir kez söylenir. Aynı yapıştırma ikinci kez
# ters gittiğinde kullanıcının hangi ucun yanlış olduğunu ve kaç karakter
# fazla olduğunu bilmesi gerekiyor. Hiçbiri anahtarı yazdırmıyor.

GECERLI_ANAHTAR = "sk_" + "a1b2c3d4" * 6          # 51 karakter


def _teshis(anahtar: str) -> str:
    from jarvis.voice.cli import _key_health
    return " ".join(_key_health(anahtar))


def test_a_correctly_shaped_key_raises_nothing():
    from jarvis.voice.cli import _key_health
    assert _key_health(GECERLI_ANAHTAR) == []


def test_extra_characters_at_the_end_are_located_and_counted():
    """The real case: a valid key with 16 characters stuck to the end."""
    metin = _teshis(GECERLI_ANAHTAR + "0123456789abcdef")
    assert "SONDAKİ 16" in metin
    assert "sonundan 16 karakter silin" in metin


def test_extra_characters_at_the_start_are_located():
    metin = _teshis("ELEVENLABS_API_KEY=" + GECERLI_ANAHTAR)
    assert "BAŞTAKİ" in metin
    assert "sk_" in metin          # nereden keseceğini söylüyor


def test_a_key_pasted_twice_is_named_as_such():
    assert "iki kez" in _teshis(GECERLI_ANAHTAR + GECERLI_ANAHTAR)


def test_a_truncated_key_says_how_many_are_missing():
    assert "5 karakter eksik" in _teshis(GECERLI_ANAHTAR[:-5])


def test_an_unknown_key_format_is_left_alone():
    """Older ElevenLabs keys had no sk_ prefix; do not accuse a valid key.

    A Voice ID pasted into the key field slips through here — the API answers
    401 and says so. Guessing at unfamiliar formats costs more than it saves.
    """
    from jarvis.voice.cli import _key_health
    assert _key_health("baska-format-anahtar") == []
    assert _key_health("PrTJxakXVyga7F3hoisX") == []


def test_the_diagnosis_never_prints_the_key():
    """These messages get pasted into chat; the key must not ride along."""
    for aday in (GECERLI_ANAHTAR + "0123456789abcdef",
                 "ELEVENLABS_API_KEY=" + GECERLI_ANAHTAR,
                 GECERLI_ANAHTAR + GECERLI_ANAHTAR,
                 GECERLI_ANAHTAR[:-5]):
        metin = _teshis(aday)
        assert GECERLI_ANAHTAR not in metin
        assert GECERLI_ANAHTAR[3:20] not in metin


def test_invisible_characters_are_still_reported():
    assert "boşluk" in _teshis(" " + GECERLI_ANAHTAR)
    assert "tırnak" in _teshis('"' + GECERLI_ANAHTAR + '"')
