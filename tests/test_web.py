"""Live panel server: routes, SSE stream, and the isolation of the demo."""
import json
import threading
import time
import urllib.error
import urllib.request

import pytest

from jarvis.bootstrap import build_agent
from jarvis.config import Config
from jarvis.memory.store import MemoryStore
from jarvis.web.server import PanelServer, collect_telemetry


def _hazir_bekle(srv, timeout: float = 5.0) -> None:
    """Wait until the server actually answers, not just until it has bound.

    Checking the attribute alone leaves a window where the socket exists but
    nothing is accepting yet — enough to make tests fail intermittently.
    """
    deadline = time.time() + timeout
    while time.time() < deadline:
        if srv._httpd is not None:
            srv.port = srv._httpd.server_address[1]
            try:
                token = f"?token={srv.token}" if srv.token else ""
                urllib.request.urlopen(
                    f"http://127.0.0.1:{srv.port}/health{token}", timeout=1
                ).read()
                return
            except urllib.error.HTTPError:
                return          # answering (401 for a gated server) = ready
            except OSError:
                pass
        time.sleep(0.02)
    raise AssertionError("sunucu zamanında hazır olmadı")


@pytest.fixture
def server():
    cfg = Config(llm_provider="mock", non_interactive=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    srv = PanelServer(agent, host="127.0.0.1", port=0)
    # port=0 lets the OS pick; serve_forever binds and we read the real port.
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _hazir_bekle(srv)
    yield srv
    srv.shutdown()


def _get(srv, path, timeout=5):
    with urllib.request.urlopen(f"http://127.0.0.1:{srv.port}{path}", timeout=timeout) as r:
        return r.status, r.read().decode("utf-8")


def _post(srv, path, obj, timeout=15):
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}{path}",
        data=json.dumps(obj).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


# ---------------- routes ----------------

def test_health(server):
    status, body = _get(server, "/health")
    assert status == 200 and json.loads(body)["ok"] is True


def test_panel_is_served_in_live_mode(server):
    status, html = _get(server, "/")
    assert status == 200
    assert 'data-live="1"' in html, "panel canlı moda geçirilmeli"
    assert "Neural Core" in html


def test_ask_returns_answer(server):
    status, body = _post(server, "/ask", {"text": "sistem durumu nedir?"})
    assert status == 200
    assert "get_system_info" not in body["answer"]
    assert "CPU" in body["answer"] or "RAM" in body["answer"]


def test_empty_ask_rejected(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post(server, "/ask", {"text": "   "})
    assert exc.value.code == 400


def test_unknown_route_404(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(server, "/gizli")
    assert exc.value.code == 404


# ---------------- SSE ----------------

def test_events_stream_replays_state_and_meta(server):
    req = urllib.request.Request(f"http://127.0.0.1:{server.port}/events")
    with urllib.request.urlopen(req, timeout=10) as r:
        assert r.headers["Content-Type"].startswith("text/event-stream")
        seen, deadline = [], time.time() + 8
        while time.time() < deadline and not {"state", "meta"} <= set(seen):
            line = r.readline().decode("utf-8")
            if line.startswith("event: "):
                seen.append(line.split(": ", 1)[1].strip())
    assert {"state", "meta"} <= set(seen), f"beklenen olaylar gelmedi: {seen}"


def test_meta_reports_unimplemented_modules_as_false(server):
    """The panel must be told what does not exist, so it shows no invented data."""
    meta = server._meta()
    assert meta["rag"] is False
    assert meta["vision"] is False
    assert meta["diagnostic_engine"] is False
    assert meta["tools"] > 0


def test_state_transitions_reach_subscribers(server):
    q = server.hub.subscribe()
    server.ask("cpu sıcaklığı?")
    kinds = []
    while not q.empty():
        payload = q.get_nowait()
        if payload.startswith("event: "):
            kinds.append(payload.split("\n")[0].split(": ", 1)[1])
    assert "state" in kinds and "transcript" in kinds


# ---------------- telemetry ----------------

def test_collect_telemetry_shape():
    t = collect_telemetry()
    assert set(t) >= {"cpu", "gpu", "ram", "disk", "ts"}
    assert t["ram"]["total_gb"] > 0
    # No GPU in CI: the field must say so rather than invent numbers.
    assert t["gpu"]["available"] in (True, False)
    if not t["gpu"]["available"]:
        assert t["gpu"]["vram_total_mb"] is None


def test_telemetry_never_raises_without_sensors():
    for _ in range(3):
        collect_telemetry()   # would raise if a missing sensor propagated


# ---------------- speech ----------------

class _StubTTS:
    """Stands in for ElevenLabs: no key, no network, deterministic bytes."""
    name = "stub"
    available = True

    def __init__(self, fail: bool = False) -> None:
        self.fail = fail
        self.spoken: list[str] = []

    def synthesize(self, text):
        from jarvis.voice.tts import TTSError
        if self.fail:
            raise TTSError("anahtar geçersiz")
        self.spoken.append(text)
        for _ in range(3):
            yield b"MP3DATA"


@pytest.fixture
def voice_server():
    cfg = Config(llm_provider="mock", non_interactive=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    tts = _StubTTS()
    srv = PanelServer(agent, host="127.0.0.1", port=0, tts=tts)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _hazir_bekle(srv)
    yield srv, tts
    srv.shutdown()


def test_ask_returns_speech_id_when_voice_configured(voice_server):
    srv, _ = voice_server
    status, body = _post(srv, "/ask", {"text": "merhaba"})
    assert status == 200 and body["speech_id"]


def test_no_speech_id_without_voice(server):
    status, body = _post(server, "/ask", {"text": "merhaba"})
    assert status == 200 and body["speech_id"] is None


def test_speech_endpoint_returns_audio(voice_server):
    srv, tts = voice_server
    _, body = _post(srv, "/ask", {"text": "merhaba"})
    url = f"http://127.0.0.1:{srv.port}/speak/{body['speech_id']}"
    with urllib.request.urlopen(url, timeout=10) as r:
        assert r.status == 200
        assert r.headers["Content-Type"] == "audio/mpeg"
        assert r.read() == b"MP3DATA" * 3
    assert tts.spoken, "metin seslendirilmeliydi"


def test_speech_has_content_length_not_chunked(voice_server):
    """A phone behind a TCP relay handles a known length far better."""
    srv, _ = voice_server
    _, body = _post(srv, "/ask", {"text": "merhaba"})
    with urllib.request.urlopen(
        f"http://127.0.0.1:{srv.port}/speak/{body['speech_id']}", timeout=10
    ) as r:
        assert r.headers.get("Content-Length") == str(len(b"MP3DATA" * 3))
        assert r.headers.get("Transfer-Encoding") is None


def test_speech_error_body_carries_the_reason(voice_server):
    """The panel shows this text, so it must say what actually went wrong."""
    srv, tts = voice_server
    _, body = _post(srv, "/ask", {"text": "merhaba"})
    tts.fail = True
    try:
        urllib.request.urlopen(f"http://127.0.0.1:{srv.port}/speak/{body['speech_id']}", timeout=10)
        raise AssertionError("hata bekleniyordu")
    except urllib.error.HTTPError as exc:
        assert exc.code == 502
        assert "anahtar geçersiz" in json.loads(exc.read())["error"]


def test_unknown_speech_id_404(voice_server):
    srv, _ = voice_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(srv, "/speak/yokboyle")
    assert exc.value.code == 404


def test_tts_failure_reports_error_and_returns_to_standby(voice_server):
    srv, tts = voice_server
    _, body = _post(srv, "/ask", {"text": "merhaba"})
    tts.fail = True
    with pytest.raises(urllib.error.HTTPError) as exc:
        _get(srv, f"/speak/{body['speech_id']}")
    assert exc.value.code == 502
    from jarvis.core.state import JarvisState
    assert srv.agent.state.state is JarvisState.STANDBY, "ses hatası durumu takılı bırakmamalı"


def test_meta_reports_voice_availability(voice_server):
    srv, _ = voice_server
    assert srv._meta()["voice"] is True


def test_panel_is_not_cached(server):
    """A cached panel silently runs old code and looks like a broken feature."""
    with urllib.request.urlopen(f"http://127.0.0.1:{server.port}/", timeout=5) as r:
        assert "no-store" in r.headers.get("Cache-Control", "")


# ---------------- microphone ----------------

class _StubSTT:
    """Stands in for faster-whisper: no model, no GPU, deterministic text."""
    name = "stub"
    available = True

    def __init__(self) -> None:
        self.fail = False
        self.duyulan: list[tuple[int, str]] = []

    def transcribe(self, audio, content_type=""):
        from jarvis.voice.stt import STTError
        if self.fail:
            raise STTError("model yüklenemedi")
        self.duyulan.append((len(audio), content_type))
        return "sistem durumu nedir"


def test_hands_free_turn_passes_structured_normalization_to_agent(monkeypatch):
    """Known STT damage is corrected, while raw evidence remains available."""
    cfg = Config(llm_provider="mock", non_interactive=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    stt = _StubSTT()
    stt.transcribe = lambda *a, **k: "Görev yerini sınaç"
    srv = PanelServer(agent, stt=stt)
    seen = {}

    def ask(text, **kwargs):
        seen["text"] = text
        seen.update(kwargs)
        return "tamam"

    monkeypatch.setattr(agent, "ask", ask)
    result = srv.konus(b"SESVERISI", "audio/webm")

    assert seen["text"] == "Görev yöneticisini aç"
    assert seen["original_text"] == "Görev yerini sınaç"
    assert seen["speech_confidence"] >= 0.9
    assert result["original_text"] == "Görev yerini sınaç"
    assert result["normalized_text"] == "Görev yöneticisini aç"


@pytest.fixture
def mic_server():
    cfg = Config(llm_provider="mock", non_interactive=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    stt = _StubSTT()
    srv = PanelServer(agent, host="127.0.0.1", port=0, stt=stt)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _hazir_bekle(srv)
    yield srv, stt
    srv.shutdown()


def _post_audio(srv, data: bytes, ctype: str = "audio/webm", timeout=10):
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}/listen", data=data,
        headers={"Content-Type": ctype},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_listen_returns_transcript(mic_server):
    srv, stt = mic_server
    status, body = _post_audio(srv, b"SESVERISI")
    assert status == 200 and body["text"] == "sistem durumu nedir"
    assert stt.duyulan == [(len(b"SESVERISI"), "audio/webm")]


def test_listen_does_not_run_the_agent(mic_server):
    """A misheard sentence must not be able to run a command unseen."""
    srv, _ = mic_server
    before = len(srv.agent.history)
    _post_audio(srv, b"SESVERISI")
    assert len(srv.agent.history) == before


def test_listen_returns_to_standby(mic_server):
    srv, _ = mic_server
    _post_audio(srv, b"SESVERISI")
    from jarvis.core.state import JarvisState
    assert srv.agent.state.state is JarvisState.STANDBY


def test_listen_failure_carries_the_reason(mic_server):
    srv, stt = mic_server
    stt.fail = True
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post_audio(srv, b"SESVERISI")
    assert exc.value.code == 502
    assert "model yüklenemedi" in json.loads(exc.value.read())["error"]


def test_listen_rejects_empty_recording(mic_server):
    srv, _ = mic_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post_audio(srv, b"")
    assert exc.value.code == 400


def test_oversized_recording_refused_before_it_is_read(mic_server):
    """The cap bounds memory, so the body must not be pulled in to check it."""
    from jarvis.voice.stt import MAX_AUDIO_BYTES
    srv, stt = mic_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}/listen", data=b"x",
        headers={"Content-Type": "audio/webm",
                 "Content-Length": str(MAX_AUDIO_BYTES + 1)},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 413
    assert not stt.duyulan


def test_listen_is_503_without_a_microphone(server):
    """Default build has no STT; it must say so rather than 404."""
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post_audio(server, b"SESVERISI")
    assert exc.value.code == 503


def test_meta_reports_microphone_availability(mic_server, server):
    srv, _ = mic_server
    assert srv._meta()["mic"] is True
    assert server._meta()["mic"] is False


def test_listen_requires_token(token_server):
    """Audio upload is gated like every other command path."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{token_server.port}/listen", data=b"SESVERISI",
        headers={"Content-Type": "audio/webm"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 401


# ---------------- eller serbest sohbet ----------------
# İstenen: "mikrofondan konuşayım ve Jarvis anlık olarak cevap versin ...
# sohbet satırına söylediklerim yazılmasın."
#
# /listen'ın vazgeçtiği koruma buydu: kimse cümleyi ajana ulaşmadan okumuyor.
# Buradaki testler yerine ne konduğunu koruyor.

def _post_konus(srv, data: bytes, ctype: str = "audio/webm", timeout=20):
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}/konus", data=data,
        headers={"Content-Type": ctype},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_konus_answers_without_a_second_request(mic_server):
    """Tek istek: duyulan cümle ve cevabı birlikte dönüyor."""
    srv, _ = mic_server
    status, body = _post_konus(srv, b"SESVERISI")
    assert status == 200
    assert body["duyulan"] == "sistem durumu nedir"
    assert body["answer"]


def test_konus_runs_the_agent_unlike_listen(mic_server):
    srv, _ = mic_server
    before = len(srv.agent.history)
    _post_konus(srv, b"SESVERISI")
    assert len(srv.agent.history) > before


def test_what_was_heard_reaches_the_transcript(mic_server):
    """Cümle önceden okunmuyor; en azından cevaptan önce GÖRÜNMELİ."""
    srv, _ = mic_server
    kuyruk = srv.hub.subscribe()
    try:
        _post_konus(srv, b"SESVERISI")
        olaylar = []
        while not kuyruk.empty():
            olaylar.append(kuyruk.get_nowait())
    finally:
        srv.hub.unsubscribe(kuyruk)
    duyulanlar = [o for o in olaylar if "sistem durumu nedir" in o]
    assert duyulanlar, "duyulan cümle transcript olayına düşmedi"


def test_silence_is_not_an_error(mic_server):
    """Bir oda dinlenirken sessizlik olağan durum, hata değil."""
    srv, stt = mic_server
    stt.transcribe = lambda audio, content_type="": "   "
    status, body = _post_konus(srv, b"SESVERISI")
    assert status == 200
    assert body["duyulan"] == "" and body["answer"] == ""
    assert body["speech_id"] is None


def test_silence_does_not_reach_the_agent(mic_server):
    srv, stt = mic_server
    stt.transcribe = lambda audio, content_type="": ""
    before = len(srv.agent.history)
    _post_konus(srv, b"SESVERISI")
    assert len(srv.agent.history) == before


def test_konus_is_503_without_a_microphone(server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post_konus(server, b"SESVERISI")
    assert exc.value.code == 503


def test_konus_requires_token(token_server):
    """Sesle gelen yol da diğer komut yolları gibi kapıdan geçiyor."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{token_server.port}/konus", data=b"SESVERISI",
        headers={"Content-Type": "audio/webm"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 401


def test_konus_bounds_the_recording_like_listen(mic_server):
    from jarvis.voice.stt import MAX_AUDIO_BYTES
    srv, stt = mic_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}/konus", data=b"x",
        headers={"Content-Type": "audio/webm",
                 "Content-Length": str(MAX_AUDIO_BYTES + 1)},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 413
    assert not stt.duyulan


def test_the_approval_floor_is_restored_after_a_spoken_turn(mic_server):
    """Yükseltilmiş bir çıtanın ortalıkta kalması sonraki her turu kilitlerdi."""
    srv, _ = mic_server
    izinler = srv.agent.tools.permissions
    onceki = izinler.taban
    _post_konus(srv, b"SESVERISI")
    assert izinler.taban == onceki


def test_a_stricter_floor_can_be_asked_for():
    """Odada başkaları varsa: yalnızca okuyan araçlar sesle çalışsın."""
    from jarvis.security.permissions import RiskLevel
    from jarvis.web.server import sesli_taban
    assert sesli_taban("low") is RiskLevel.LOW
    assert sesli_taban("düşük") is RiskLevel.LOW


@pytest.mark.parametrize("ayar", ["high", "critical", "", "saçma", None])
def test_the_floor_setting_can_never_loosen_the_gate(ayar):
    """Ayarın amacı sıkılaştırmak. HIGH'ı adlandırabilmek onu tam tersine çevirirdi."""
    from jarvis.security.permissions import RiskLevel
    from jarvis.web.server import sesli_taban
    assert sesli_taban(ayar) is RiskLevel.MEDIUM


# ---------------- modül sekmeleri ----------------
# Panelin modül şeridi tek bir uç noktadan besleniyor. Buradaki kural
# panelin ilk sürümünden beri aynı: ölçmediği bir sayıyı göstermez.

MODUL_ADLARI = {"sistem", "ses", "goruntu", "teshis",
                "hafiza", "bilgi", "araclar", "ajanda"}


def test_every_module_tab_has_data(server):
    veri = server.modul_verisi()
    assert set(veri) == MODUL_ADLARI
    for ad, d in veri.items():
        assert d["durum"] in ("hazir", "bos", "yok"), ad
        assert isinstance(d["satirlar"], list), ad


def test_modules_endpoint_is_served(server):
    status, govde = _get(server, "/moduller")
    assert status == 200
    assert set(json.loads(govde)) == MODUL_ADLARI


def test_modules_require_a_token(token_server):
    """Bu uç nokta hafızayı ve vaka müşterilerini gösteriyor."""
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(
            f"http://127.0.0.1:{token_server.port}/moduller", timeout=5)
    assert exc.value.code == 401


def test_the_tools_tab_lists_real_tools_with_their_risk(server):
    araclar = server.modul_verisi()["araclar"]
    assert araclar["satirlar"], "araç listesi boş olmamalı"
    adlar = {s["ad"] for s in araclar["satirlar"]}
    assert {"web_ara", "bilgi_ara", "run_terminal_command"} <= adlar
    assert all(s["deger"] for s in araclar["satirlar"]), "risk etiketi eksik"


def test_an_unimplemented_module_says_so_instead_of_inventing(server):
    ajanda = server.modul_verisi()["ajanda"]
    assert ajanda["durum"] == "yok"
    assert "henüz" in ajanda["ozet"]


def test_an_empty_knowledge_tab_says_how_to_fill_it(server):
    bilgi = server.modul_verisi()["bilgi"]
    assert bilgi["durum"] == "bos"
    assert any("jarvis-bilgi ekle" in s["deger"] for s in bilgi["satirlar"])


def test_the_diagnostic_tab_counts_real_cases():
    from jarvis.memory.cases import CaseStore
    cfg = Config(llm_provider="mock", non_interactive=True)
    vakalar = CaseStore(":memory:")
    vakalar.open_case("Deniz Yılmaz", "Lenovo V15", "açılmıyor")
    agent = build_agent(cfg, memory=MemoryStore(":memory:"), cases=vakalar)
    teshis = PanelServer(agent, host="127.0.0.1", port=0).modul_verisi()["teshis"]
    assert teshis["durum"] == "hazir"
    assert "1 açık vaka" in teshis["ozet"]


def test_a_broken_store_costs_its_own_tab_not_the_panel(server):
    """Bozuk bir depo yalnızca kendi sekmesini kaybetmeli."""
    class _Kirik:
        def stats(self):
            raise RuntimeError("bozuk")
    server.agent.knowledge = _Kirik()
    veri = server.modul_verisi()
    assert veri["bilgi"]["durum"] == "yok"
    assert veri["araclar"]["satirlar"], "diğer sekmeler çalışmaya devam etmeli"


# ---------------- knowledge base ----------------

def test_meta_reports_an_empty_knowledge_base_as_absent(server):
    """An empty index and a missing one must both read as "yok" in the panel."""
    m = server._meta()
    assert m["rag"] is False and m["rag_parca"] == 0


def test_meta_reports_real_knowledge_base_numbers():
    from jarvis.rag.index import KnowledgeBase
    cfg = Config(llm_provider="mock", non_interactive=True)
    kb = KnowledgeBase(":memory:")
    kb.index_text("n.md", "# N\n\nbir iki uc dort bes\n")
    agent = build_agent(cfg, memory=MemoryStore(":memory:"), knowledge=kb)
    m = PanelServer(agent, host="127.0.0.1", port=0)._meta()
    assert m["rag"] is True
    assert m["rag_parca"] == kb.stats()["parca"]
    assert m["rag_belge"] == 1
    assert m["rag_anlam"] is False        # gömme modeli yok


def test_a_broken_knowledge_base_does_not_break_meta(server):
    """The panel must still load when the index file is unreadable."""
    class _Kirik:
        def stats(self):
            raise RuntimeError("bozuk dosya")
    server.agent.knowledge = _Kirik()
    assert server._meta()["rag"] is False


# ---------------- camera ----------------

class _StubVision:
    """Stands in for OpenCV: no cascade, no image decoding, fixed geometry."""
    name = "stub"
    available = True

    def __init__(self) -> None:
        self.fail = False
        self.gorulen: list[int] = []

    def detect(self, frame):
        from jarvis.vision.detect import Face, VisionError
        if self.fail:
            raise VisionError("kare çözümlenemedi")
        self.gorulen.append(len(frame))
        return [Face(x=0.25, y=0.2, w=0.3, h=0.4)]


@pytest.fixture
def cam_server():
    cfg = Config(llm_provider="mock", non_interactive=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    vision = _StubVision()
    srv = PanelServer(agent, host="127.0.0.1", port=0, vision=vision)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _hazir_bekle(srv)
    yield srv, vision
    srv.shutdown()


def _post_frame(srv, data: bytes, ctype: str = "image/jpeg", timeout=10):
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}/gor", data=data,
        headers={"Content-Type": ctype},
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode("utf-8"))


def test_vision_returns_faces_in_frame_fractions(cam_server):
    srv, vision = cam_server
    status, body = _post_frame(srv, b"KAREVERISI")
    assert status == 200
    assert body["yuz_sayisi"] == 1
    assert body["yuzler"] == [{"x": 0.25, "y": 0.2, "w": 0.3, "h": 0.4}]
    assert vision.gorulen == [len(b"KAREVERISI")]


def test_vision_does_not_run_the_agent(cam_server):
    """Seeing a face must not be able to start a turn on its own."""
    srv, _ = cam_server
    before = len(srv.agent.history)
    _post_frame(srv, b"KAREVERISI")
    assert len(srv.agent.history) == before


def test_vision_failure_carries_the_reason(cam_server):
    srv, vision = cam_server
    vision.fail = True
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post_frame(srv, b"KAREVERISI")
    assert exc.value.code == 502
    assert "çözümlenemedi" in json.loads(exc.value.read())["error"]


def test_vision_rejects_empty_frame(cam_server):
    srv, _ = cam_server
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post_frame(srv, b"")
    assert exc.value.code == 400


def test_oversized_frame_refused_before_it_is_read(cam_server):
    from jarvis.vision.detect import MAX_FRAME_BYTES
    srv, vision = cam_server
    req = urllib.request.Request(
        f"http://127.0.0.1:{srv.port}/gor", data=b"x",
        headers={"Content-Type": "image/jpeg",
                 "Content-Length": str(MAX_FRAME_BYTES + 1)},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=10)
    assert exc.value.code == 413
    assert not vision.gorulen


def test_vision_is_503_without_a_camera(server):
    """Default build has no camera; it must say so rather than 404."""
    with pytest.raises(urllib.error.HTTPError) as exc:
        _post_frame(server, b"KAREVERISI")
    assert exc.value.code == 503


def test_meta_reports_camera_availability(cam_server, server):
    srv, _ = cam_server
    assert srv._meta()["kamera"] is True
    assert server._meta()["kamera"] is False


def test_vision_requires_token(token_server):
    """A camera frame is gated like every other command path."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{token_server.port}/gor", data=b"KAREVERISI",
        headers={"Content-Type": "image/jpeg"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 401


# ---------------- liveness ----------------
#
# Regression guard: /health used to sit behind the token gate, so an
# unauthenticated probe got a 401 — and the WSL forwarding script read that as
# "the panel is not running" while it was serving normally.

def test_health_answers_without_a_token(token_server):
    """A probe that needs the secret cannot report on a lost secret."""
    status, body = _get(token_server, "/health")      # no token supplied
    assert status == 200 and json.loads(body)["ok"] is True


def test_health_hides_the_state_from_an_unauthenticated_caller(token_server):
    """Whether the owner is mid-conversation is not for an open port to say."""
    assert "state" not in json.loads(_get(token_server, "/health")[1])


def test_health_includes_the_state_for_an_authorised_caller(token_server):
    body = _get(token_server, f"/health?token={token_server.token}")[1]
    assert json.loads(body)["state"] == "standby"


def test_health_is_the_only_route_open_without_a_token(token_server):
    """Opening liveness must not have opened anything else."""
    for yol in ("/", "/events", "/speak/abc"):
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(
                f"http://127.0.0.1:{token_server.port}{yol}", timeout=5)
        assert exc.value.code == 401, yol


# ---------------- access token ----------------

@pytest.fixture
def token_server():
    cfg = Config(llm_provider="mock", non_interactive=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    srv = PanelServer(agent, host="127.0.0.1", port=0, token="gizli-jeton")
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    _hazir_bekle(srv)
    yield srv
    srv.shutdown()


def _raw_get(srv, path, headers=None):
    req = urllib.request.Request(f"http://127.0.0.1:{srv.port}{path}", headers=headers or {})
    return urllib.request.urlopen(req, timeout=5)


def test_panel_requires_token(token_server):
    """The panel can run shell commands; an open door is not acceptable."""
    with pytest.raises(urllib.error.HTTPError) as exc:
        _raw_get(token_server, "/")
    assert exc.value.code == 401


def test_wrong_token_rejected(token_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _raw_get(token_server, "/?token=yanlis")
    assert exc.value.code == 401


def test_ask_requires_token(token_server):
    """The command path must be gated too, not just the page."""
    req = urllib.request.Request(
        f"http://127.0.0.1:{token_server.port}/ask",
        data=json.dumps({"text": "merhaba"}).encode(),
        headers={"Content-Type": "application/json"},
    )
    with pytest.raises(urllib.error.HTTPError) as exc:
        urllib.request.urlopen(req, timeout=5)
    assert exc.value.code == 401


def test_query_token_accepted_and_sets_cookie(token_server):
    resp = _raw_get(token_server, "/?token=gizli-jeton")
    assert resp.status == 200
    assert "jarvis_token=gizli-jeton" in resp.headers.get("Set-Cookie", "")


def test_header_token_accepted(token_server):
    resp = _raw_get(token_server, "/health", {"X-Jarvis-Token": "gizli-jeton"})
    assert resp.status == 200


def test_cookie_token_accepted(token_server):
    resp = _raw_get(token_server, "/health", {"Cookie": "jarvis_token=gizli-jeton"})
    assert resp.status == 200


def test_events_stream_is_gated(token_server):
    with pytest.raises(urllib.error.HTTPError) as exc:
        _raw_get(token_server, "/events")
    assert exc.value.code == 401


def test_no_token_configured_means_open(server):
    """Localhost-only default stays frictionless."""
    assert _get(server, "/health")[0] == 200


def test_health_says_whether_a_token_is_required(server, token_server):
    """A launcher needs to know it must put a token in the URL.

    Not a leak: requesting "/" already answers the same question with a 401.
    Without this the desktop launcher opened a token page instead of the panel.
    """
    assert json.loads(_get(server, "/health")[1])["jeton"] is False
    with urllib.request.urlopen(
        f"http://127.0.0.1:{token_server.port}/health", timeout=5
    ) as r:
        assert json.loads(r.read())["jeton"] is True


def test_health_never_reveals_the_token_itself(token_server):
    with urllib.request.urlopen(
        f"http://127.0.0.1:{token_server.port}/health", timeout=5
    ) as r:
        assert token_server.token not in r.read().decode("utf-8")


def test_meta_names_the_active_speech_provider():
    """Ayarı değiştirip panele bakan biri hangi sesin konuştuğunu görebilmeli."""
    class _Piper:
        name, available, mime = "piper", True, "audio/wav"

    cfg = Config(llm_provider="mock", non_interactive=True)
    agent = build_agent(cfg, memory=MemoryStore(":memory:"))
    m = PanelServer(agent, host="127.0.0.1", port=0, tts=_Piper())._meta()
    assert m["voice"] is True and m["ses_saglayici"] == "piper"


def test_meta_says_closed_when_there_is_no_speech(server):
    assert server._meta()["ses_saglayici"] == "kapalı"


# ---------------- uygulama penceresi ----------------

def test_the_app_icon_is_served(server):
    """Uygulama penceresinin başlık ve görev çubuğu simgesi buradan geliyor."""
    with urllib.request.urlopen(
        f"http://127.0.0.1:{server.port}/favicon.ico", timeout=5
    ) as r:
        govde = r.read()
    assert r.headers["Content-Type"] == "image/x-icon"
    assert govde[:4] == b"\x00\x00\x01\x00", "geçerli ICO olmalı"


def test_the_icon_does_not_need_a_token(token_server):
    """Pencere simgeyi herhangi bir gezinmeden ÖNCE istiyor; jetonu yok.

    Sızıntı değil: simge zaten depoda ve gizli bir şey taşımıyor.
    """
    with urllib.request.urlopen(
        f"http://127.0.0.1:{token_server.port}/favicon.ico", timeout=5
    ) as r:
        assert r.status == 200


def test_the_panel_points_at_that_icon():
    from jarvis.web.server import PANEL_HTML
    assert 'href="/favicon.ico"' in PANEL_HTML.read_text(encoding="utf-8")
