"""Live panel server — serves the Neural Core panel and streams real state.

Standard library only: the panel receives updates over Server-Sent Events,
which is a plain HTTP response that stays open. The panel only ever needs
server→browser updates (state, telemetry, transcript), so SSE covers it
without pulling in a WebSocket dependency — and a demo running in a VM is
exactly where an extra dependency is least welcome.

    GET  /          panel HTML (live mode)
    GET  /events    SSE stream: state · telemetry · transcript
    POST /ask       {"text": "..."} → runs one agent turn
    POST /listen    raw audio body → transcribed text (local, never uploaded)
    POST /konus     raw audio body → transcribed text AND the answer
    POST /gor       raw image body → faces found (local, frame not kept)
    GET  /moduller  per-module detail for the module bar
    GET  /health    liveness probe

**Binds to 127.0.0.1 by default and should stay there.** This endpoint can
run terminal commands through the agent, so exposing it on a LAN address
hands that capability to anyone who can reach the port.
"""
from __future__ import annotations

import hmac
import json
import queue
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psutil

from ..core.agent import Agent
from ..core.state import JarvisState
from ..core.asistan import asistan_bul
from ..security.permissions import RiskLevel
from ..vision.detect import MAX_FRAME_BYTES, VisionError, build_vision
from ..core.command_guide import panel_rows
from ..vision.objects import build_object_vision
from ..vision.ocr import build_ocr
from ..vision.identity import build_face_recognizer
from ..voice.stt import MAX_AUDIO_BYTES, STTError, build_stt
from ..voice.normalization import SpeechNormalization, SpeechNormalizer
from ..voice.tts import NullTTS, TTSError
from ..tools.system_tools import (
    get_cpu_temperature,
    get_disk_health,
    get_gpu_temperature,
    get_ram_usage,
    get_system_info,
)

PANEL_HTML = Path(__file__).resolve().parents[2] / "docs" / "mockups" / "jarvis-panel.html"
#: Uygulama penceresinin baslik cubugundaki ve gorev cubugundaki simge
#: buradan geliyor: tarayici sayfanin favicon'unu kullaniyor.
PANEL_ICO = Path(__file__).resolve().parents[2] / "windows" / "jarvis.ico"

#: How often telemetry is pushed to connected panels.
TELEMETRY_PERIOD_S = 4.0


class EventHub:
    """Fan-out of events to every connected panel."""

    def __init__(self) -> None:
        self._subscribers: list[queue.Queue[str]] = []
        self._lock = threading.Lock()
        self._last: dict[str, str] = {}

    def subscribe(self) -> queue.Queue[str]:
        q: queue.Queue[str] = queue.Queue(maxsize=100)
        with self._lock:
            self._subscribers.append(q)
            # Replay the latest of each event kind so a panel that connects
            # late still paints a correct screen instead of an empty one.
            for payload in self._last.values():
                try:
                    q.put_nowait(payload)
                except queue.Full:
                    pass
        return q

    def unsubscribe(self, q: queue.Queue[str]) -> None:
        with self._lock:
            if q in self._subscribers:
                self._subscribers.remove(q)

    def publish(self, kind: str, data: dict[str, Any], *, retain: bool = True) -> None:
        payload = f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        with self._lock:
            if retain:
                self._last[kind] = payload
            targets = list(self._subscribers)
        for q in targets:
            try:
                q.put_nowait(payload)
            except queue.Full:
                # A panel that stopped reading must not stall the agent.
                pass


def collect_telemetry() -> dict[str, Any]:
    """One telemetry snapshot; every field degrades to None when unavailable."""
    info = get_system_info()
    ram = get_ram_usage()
    cpu_t = get_cpu_temperature()
    gpu = get_gpu_temperature()
    disk = get_disk_health()

    try:
        freq = psutil.cpu_freq()
        freq_ghz = round(freq.current / 1000, 2) if freq and freq.current else None
    except (AttributeError, OSError):
        freq_ghz = None

    root = next((p for p in disk["partitions"] if p["mount"] == "/"), None)
    return {
        "cpu": {
            "percent": info["cpu_percent"],
            "cores": info["cpu_cores"],
            "threads": info["cpu_threads"],
            "temp_c": cpu_t.get("cpu_temp_c") if cpu_t.get("available") else None,
            "freq_ghz": freq_ghz,
        },
        "gpu": {
            "available": gpu.get("available", False),
            "name": gpu.get("name"),
            "temp_c": gpu.get("gpu_temp_c"),
            "util": gpu.get("gpu_util_percent"),
            "vram_used_mb": gpu.get("vram_used_mb"),
            "vram_total_mb": gpu.get("vram_total_mb"),
            "note": gpu.get("note"),
        },
        "ram": {
            "used_gb": ram["ram_used_gb"],
            "total_gb": ram["ram_total_gb"],
            "percent": ram["ram_percent"],
            "swap_gb": ram["swap_used_gb"],
        },
        "disk": {
            "used_percent": root["used_percent"] if root else info["disk_used_percent"],
            "total_gb": root["total_gb"] if root else None,
            "smart": disk["smart_overall"],
        },
        "ts": time.time(),
    }


#: Sesle gelen bir turda onaysız çalışabilen en yüksek risk, ad → seviye.
SESLI_TABANLAR = {
    "low": RiskLevel.LOW, "dusuk": RiskLevel.LOW, "düşük": RiskLevel.LOW,
    "medium": RiskLevel.MEDIUM, "orta": RiskLevel.MEDIUM,
}


def sesli_taban(ad: str) -> RiskLevel:
    """Read the hands-free approval floor from a setting.

    Only LOW and MEDIUM are namable on purpose. The floor exists to make the
    unattended path *stricter*; letting a setting name HIGH would turn it into
    a way to run destructive tools without approval, which is the opposite of
    what it is for. Anything unrecognised falls back to the default rather
    than to the permissive end.
    """
    return SESLI_TABANLAR.get((ad or "").strip().lower(), RiskLevel.MEDIUM)


class PanelServer:
    def __init__(self, agent: Agent, host: str = "127.0.0.1", port: int = 8765,
                 tts=None, token: str | None = None, stt=None, vision=None,
                 object_vision=None, ocr=None,
                 face_recognizer=None,
                 sesli_onay_tabani: RiskLevel = RiskLevel.MEDIUM,
                 llm_uyari: str = "") -> None:
        self.agent = agent
        self.host = host
        self.port = port
        # Ses VERİLMEDİYSE sessiz. Burada bir sağlayıcı kurmak, panelin
        # gömülü kullanıldığı her yerde habersiz bir ağ isteği demek olurdu —
        # Edge sağlayıcısı eklendiğinde varsayılan tam olarak buna dönüştü.
        # Sesi kim istiyorsa açıkça veriyor (bkz. jarvis/web/cli.py).
        self.tts = tts if tts is not None else NullTTS(
            "Panel sessiz başlatıldı (sağlayıcı verilmedi).")
        self.stt = stt if stt is not None else build_stt(enabled=False)
        self.speech_normalizer = SpeechNormalizer()
        self.vision = vision if vision is not None else build_vision(enabled=False)
        self.object_vision = object_vision if object_vision is not None else build_object_vision(False)
        self.ocr = ocr if ocr is not None else build_ocr(False)
        self.face_recognizer = face_recognizer if face_recognizer is not None else build_face_recognizer(False)
        # An access token is required whenever the panel is reachable beyond
        # this machine: it can run terminal commands, so anyone who can open
        # the page can drive the host. Empty token = no check (localhost only).
        self.token = token or ""
        self.sesli_onay_tabani = sesli_onay_tabani
        #: LLM acilista yoklanip buraya yaziliyor; bos ise sorun yok.
        self.llm_uyari = llm_uyari
        self.hub = EventHub()
        self._agent_lock = threading.Lock()
        self._speech: dict[str, str] = {}
        self._speech_lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._stop = threading.Event()

        agent.state.subscribe(self._on_state)
        self.hub.publish("state", {"state": agent.state.state.value,
                                   "label": agent.state.state.label_tr})
        self.hub.publish("meta", self._meta())

    def _kimlik_betigi(self) -> str:
        """Asistan kimliğini sayfaya gömen kısa betik.

        Sayfanın ilk çizimi buna bağlı; SSE ile gelmesini beklemek girişte
        yanlış adın bir an görünmesi demek.
        """
        a = getattr(self.agent, "asistan", None) or asistan_bul()
        return (
            "<script>"
            f"window.__asistanAd={json.dumps(a.ad)};"
            f"window.__asistanSade={json.dumps(a.sade_ad)};"
            f"window.__asistanKod={json.dumps(a.kod)};"
            "</script>"
            "<style>:root{"
            f"--accent:{a.vurgu};"
            "}</style>"
        )

    def _meta(self) -> dict[str, Any]:
        """What this build actually has — so the panel shows no invented data."""
        cfg = getattr(self.agent.llm, "model", None)
        a = getattr(self.agent, "asistan", None) or asistan_bul()
        return {
            # Panel adini ve rengini SUNUCUDAN aliyor: kimlik tek yerde
            # (core/asistan.py) duruyor, HTML'de ikinci bir kopyasi yok.
            # LLM gercekten cevap verebiliyor mu. Panel bunu bir uyari
            # olarak gosteriyor; "acilir ama cevap vermez" durumunun sessiz
            # kalmasi, kullanicinin hatayi ilk soruda ogrenmesi demekti.
            "llm_uyari": self.llm_uyari,
            "asistan": a.kod,
            "asistan_ad": a.ad,
            "asistan_sade": a.sade_ad,
            "asistan_vurgu": a.vurgu,
            "owner": getattr(self.agent.owner, "name", "") or "",
            "model": cfg or self.agent.llm.name,
            "provider": self.agent.llm.name,
            "tools": len(self.agent.registry.all()),
            "memory_layers": 3,           # conversation + user facts + service cases
            "voice": self.tts.available,
            # Hangi saglayici konusuyor. Ayari degistirip panele bakan biri
            # bunu gorebilmeli: ".env'i degistirdim ama ses ayni" sorusunun
            # cevabi cogunlukla "panel eski surecte calismaya devam ediyor".
            "ses_saglayici": self.tts.name if self.tts.available else "kapalı",
            "mic": self.stt.available,
            # "kamera" is the camera being usable at all; "vision" below is
            # understanding what it sees. Stage one has the first and not the
            # second, and the panel must not imply otherwise.
            "kamera": self.vision.available,
            "nesne": self.object_vision.available,
            "ocr": self.ocr.available,
            "face_recognition": self.face_recognizer.available,
            **self._rag_meta(),
            # Not implemented yet — the panel marks these instead of faking them.
            "vision": False,
            "diagnostic_engine": False,
        }

    def _rag_meta(self) -> dict[str, Any]:
        """Knowledge-base numbers, or an honest zero.

        An empty index and a broken one look the same from the panel, so the
        count is what decides whether the row reads as live — not the mere
        presence of a store.
        """
        kb = getattr(self.agent, "knowledge", None)
        if kb is None:
            return {"rag": False, "rag_parca": 0, "rag_belge": 0, "rag_anlam": False}
        try:
            d = kb.stats()
        except Exception:
            return {"rag": False, "rag_parca": 0, "rag_belge": 0, "rag_anlam": False}
        return {
            "rag": bool(d.get("parca")),
            "rag_parca": int(d.get("parca", 0)),
            "rag_belge": int(d.get("belge", 0)),
            "rag_anlam": bool(d.get("anlam_aramasi")),
        }

    def modul_verisi(self) -> dict[str, Any]:
        """Per-module detail for the panel's module bar.

        One endpoint rather than one per module, and every value read from
        something that actually exists. A module with nothing behind it says
        so — the panel's rule since the first version is that it never shows
        a number it did not measure, because an invented figure on a
        diagnostic tool is worse than an empty one.

        Every section is wrapped: a broken store may cost its own tab, never
        the whole panel.
        """
        def guvenli(uret, yedek):
            try:
                return uret()
            except Exception:
                return yedek

        def araclar() -> dict[str, Any]:
            liste = sorted(self.agent.registry.all(), key=lambda t: t.name)
            return {
                "durum": "hazir",
                "ozet": f"{len(liste)} araç · izinli",
                "satirlar": [{"ad": t.name, "deger": t.risk.label} for t in liste],
            }

        def hafiza() -> dict[str, Any]:
            store = self.agent.memory
            if store is None:
                return {"durum": "yok", "ozet": "hafıza bağlı değil", "satirlar": []}
            gercekler = store.all_facts(limit=12)
            sahip = getattr(self.agent.owner, "name", "") or "(tanıtılmadı)"
            satirlar = [{"ad": "Sahip", "deger": sahip},
                        {"ad": "Bu oturum", "deger":
                         f"{store.session_count(self.agent.session_id)} mesaj"}]
            satirlar += [{"ad": f.key, "deger": f.value} for f in gercekler]
            return {"durum": "hazir",
                    "ozet": f"{len(gercekler)} kayıtlı bilgi", "satirlar": satirlar}

        def teshis() -> dict[str, Any]:
            cases = self.agent.cases
            if cases is None:
                return {"durum": "yok", "ozet": "vaka defteri bağlı değil", "satirlar": []}
            acik = cases.open_cases(limit=8)
            toplam = cases.count_open()
            return {
                "durum": "hazir" if toplam else "bos",
                "ozet": f"{toplam} açık vaka" if toplam else "açık vaka yok",
                "satirlar": [{"ad": f"#{v.id} {v.customer}", "deger": v.device}
                             for v in acik],
            }

        def bilgi() -> dict[str, Any]:
            kb = getattr(self.agent, "knowledge", None)
            if kb is None:
                return {"durum": "yok", "ozet": "bilgi tabanı bağlı değil", "satirlar": []}
            d = kb.stats()
            if not d.get("parca"):
                return {"durum": "bos", "ozet": "boş — henüz belge eklenmedi",
                        "satirlar": [{"ad": "Eklemek için",
                                      "deger": "jarvis-bilgi ekle <klasör>"}]}
            belgeler = kb.documents(limit=8)
            return {
                "durum": "hazir",
                "ozet": f"{d['belge']} belge · {d['parca']} parça",
                "satirlar": [
                    {"ad": "Arama", "deger":
                     "anlam + kelime" if d["anlam_aramasi"] else "yalnızca kelime"},
                    {"ad": "Gömme modeli", "deger": d["model"] or "(yok)"},
                ] + [{"ad": b["yol"].rsplit("/", 1)[-1], "deger": f"{b['parca']} parça"}
                     for b in belgeler],
            }

        def ses() -> dict[str, Any]:
            satirlar = [
                {"ad": "Seslendirme", "deger": self.tts.name if self.tts.available else "kapalı"},
                {"ad": "Mikrofon", "deger":
                 f"{self.stt.name} · {getattr(self.stt, 'model_size', '')}"
                 if self.stt.available else "kapalı"},
            ]
            acik = self.tts.available or self.stt.available
            return {"durum": "hazir" if acik else "bos",
                    "ozet": "ses ve mikrofon" if acik else "ses kapalı",
                    "satirlar": satirlar}

        def goruntu() -> dict[str, Any]:
            var = self.vision.available
            return {"durum": "hazir" if var else "bos",
                    "ozet": self.vision.name if var else "kamera kapalı",
                    "satirlar": [{"ad": "Sağlayıcı",
                                  "deger": self.vision.name if var else
                                  getattr(self.vision, "reason", "kapalı").splitlines()[0]}]}

        def sistem() -> dict[str, Any]:
            return {"durum": "hazir",
                    "ozet": self.agent.llm.name,
                    "satirlar": [
                        {"ad": "Model", "deger": getattr(self.agent.llm, "model", "")
                         or self.agent.llm.name},
                        {"ad": "Sağlayıcı", "deger": self.agent.llm.name},
                        {"ad": "Durum", "deger": self.agent.state.state.label_tr},
                        {"ad": "Makine", "deger": self.agent.machine or "(okunamadı)"},
                    ]}

        def komutlar() -> dict[str, Any]:
            satirlar = panel_rows()
            return {
                "durum": "hazir",
                "ozet": f"{len(satirlar)} kolay örnek",
                "satirlar": satirlar,
            }

        return {
            "sistem": guvenli(sistem, {"durum": "yok", "ozet": "", "satirlar": []}),
            "ses": guvenli(ses, {"durum": "yok", "ozet": "", "satirlar": []}),
            "goruntu": guvenli(goruntu, {"durum": "yok", "ozet": "", "satirlar": []}),
            "teshis": guvenli(teshis, {"durum": "yok", "ozet": "", "satirlar": []}),
            "hafiza": guvenli(hafiza, {"durum": "yok", "ozet": "", "satirlar": []}),
            "bilgi": guvenli(bilgi, {"durum": "yok", "ozet": "", "satirlar": []}),
            "araclar": guvenli(araclar, {"durum": "yok", "ozet": "", "satirlar": []}),
            "komutlar": guvenli(komutlar, {"durum": "yok", "ozet": "", "satirlar": []}),
            # Henüz yok. Uydurma veri yerine açıkça söylüyoruz.
            "ajanda": {"durum": "yok",
                       "ozet": "bu modül henüz yapılmadı",
                       "satirlar": [{"ad": "Planlanan",
                                     "deger": "randevu ve teslim tarihleri"}]},
        }

    # ---------------- agent plumbing ----------------

    def _on_state(self, old: JarvisState, new: JarvisState) -> None:
        self.hub.publish("state", {"state": new.value, "label": new.label_tr})

    def ask(self, text: str, *, speech: SpeechNormalization | None = None
            ) -> tuple[str, str | None]:
        """One agent turn, serialised — the agent holds mutable history.

        Returns the answer and, when speech is configured, an id the panel can
        stream audio from. The text is synthesised on request rather than here
        so the written answer appears immediately instead of waiting on audio.
        """
        self.hub.publish("transcript", {"role": "user", "text": text}, retain=False)
        with self._agent_lock:
            if speech is None:
                answer = self.agent.ask(text)
            else:
                answer = self.agent.ask(
                    text,
                    original_text=speech.original_text,
                    speech_confidence=speech.confidence,
                    speech_ambiguity=speech.ambiguity,
                )
        self.hub.publish("transcript", {"role": "assistant", "text": answer}, retain=False)

        speech_id = None
        if self.tts.available and answer.strip():
            speech_id = uuid.uuid4().hex[:16]
            with self._speech_lock:
                self._speech[speech_id] = answer
                # Keep the cache small; these are only needed for one playback.
                while len(self._speech) > 20:
                    self._speech.pop(next(iter(self._speech)))
        return answer, speech_id

    def listen(self, audio: bytes, content_type: str = "") -> str:
        """Transcribe a recording. Returns the text; does not ask anything.

        Deliberately separate from :meth:`ask`: the agent can run terminal
        commands, and a misheard sentence must not be able to trigger one
        unseen. The panel puts the text in the input box for the user to send.
        """
        self.agent.state.transition(JarvisState.LISTENING)
        try:
            return self.listen_result(audio, content_type).normalized_text
        finally:
            self.agent.state.transition(JarvisState.STANDBY)

    def listen_result(self, audio: bytes, content_type: str = "") -> SpeechNormalization:
        """Return auditable raw/normalized speech data without executing it."""
        raw = self.stt.transcribe(audio, content_type)
        preliminary = self.speech_normalizer.normalize(raw)
        risk = self.agent.intent_router.route(preliminary.normalized_text).risk
        return self.speech_normalizer.normalize(raw, risk=risk)

    def konus(self, audio: bytes, content_type: str = "") -> dict[str, Any]:
        """Hands-free turn: hear it, answer it, in one round trip.

        This is what was asked for — *"mikrofondan konuşayım ve Jarvis anlık
        olarak cevap versin"* — and it gives up what :meth:`listen` was built
        around: nobody reads the sentence before the agent acts on it.

        What that costs is smaller than it first looks, and worth being exact
        about. MEDIUM in this codebase already means *visible and reversible*;
        "YouTube aç" lives there, and refusing it because it arrived by
        microphone would defeat the feature. Everything destructive is
        HIGH/CRITICAL and still needs approval — which in the panel means a
        refusal with a reason (see
        :func:`~jarvis.security.permissions.panel_approver`).

        So the default floor is unchanged, and the real mitigations are that
        what was heard reaches the transcript before the answer, and that a
        room with other people in it can be made stricter with one setting:
        ``JARVIS_SESLI_TABAN=low`` leaves only read-only tools running
        unattended.

        Something inaudible comes back as an empty answer rather than an
        error: silence is the normal case when a room is being listened to.
        """
        self.agent.state.transition(JarvisState.LISTENING)
        try:
            speech = self.listen_result(audio, content_type)
        finally:
            self.agent.state.transition(JarvisState.STANDBY)
        duyulan = speech.normalized_text.strip()
        if not duyulan:
            return {"duyulan": "", "answer": "", "speech_id": None}

        izinler = getattr(getattr(self.agent, "tools", None), "permissions", None)
        yukselt = getattr(izinler, "yukselt", None)
        if yukselt is None:
            answer, speech_id = self.ask(duyulan, speech=speech)
        else:
            with yukselt(self.sesli_onay_tabani):
                answer, speech_id = self.ask(duyulan, speech=speech)
        return {
            "duyulan": duyulan,
            "original_text": speech.original_text,
            "normalized_text": speech.normalized_text,
            "confidence": speech.confidence,
            "ambiguity": speech.ambiguity,
            "needs_confirmation": speech.needs_confirmation,
            "answer": answer,
            "speech_id": speech_id,
        }

    def speech_text(self, speech_id: str) -> str | None:
        with self._speech_lock:
            return self._speech.get(speech_id)

    # ---------------- background telemetry ----------------

    def _telemetry_loop(self) -> None:
        while not self._stop.is_set():
            try:
                self.hub.publish("telemetry", collect_telemetry())
            except Exception:
                pass  # a telemetry hiccup must never kill the server
            self._stop.wait(TELEMETRY_PERIOD_S)

    # ---------------- lifecycle ----------------

    def serve_forever(self) -> None:
        handler = _make_handler(self)
        self._httpd = ThreadingHTTPServer((self.host, self.port), handler)
        self._httpd.daemon_threads = True
        threading.Thread(target=self._telemetry_loop, daemon=True).start()
        try:
            self._httpd.serve_forever()
        finally:
            self._stop.set()

    def shutdown(self) -> None:
        self._stop.set()
        if self._httpd is not None:
            self._httpd.shutdown()


def _make_handler(server: PanelServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt: str, *args: Any) -> None:
            pass  # keep the terminal readable; the agent prints its own lines

        # ---- access control ----
        def _authorised(self) -> bool:
            """True when the caller proved it holds the access token.

            Accepted from a query parameter (first visit, easy to type or scan),
            a header (for scripted calls), or the cookie set after a successful
            query-param visit so later navigation needs no token in the URL.
            """
            if not server.token:
                return True

            parsed = urllib.parse.urlparse(self.path)
            supplied = urllib.parse.parse_qs(parsed.query).get("token", [""])[0]
            if not supplied:
                supplied = self.headers.get("X-Jarvis-Token", "")
            if not supplied:
                cookie = self.headers.get("Cookie", "")
                for part in cookie.split(";"):
                    name, _, value = part.strip().partition("=")
                    if name == "jarvis_token":
                        supplied = value
                        break
            # compare_digest keeps a wrong guess from leaking its length by timing.
            return hmac.compare_digest(supplied, server.token)

        def _reject(self) -> None:
            body = (
                "<!doctype html><meta charset='utf-8'>"
                "<style>body{font-family:system-ui;background:#05090e;color:#cfeaf7;"
                "display:flex;align-items:center;justify-content:center;height:100vh;margin:0}"
                "div{text-align:center;max-width:30rem;padding:2rem}"
                "code{background:#0e1826;padding:.2rem .4rem;border-radius:3px}</style>"
                "<div><h2>Erişim jetonu gerekli</h2>"
                "<p>Bu panel terminal komutu çalıştırabildiği için jetonsuz açılmaz.</p>"
                "<p>Sunucuyu başlattığınız terminalde yazan adresi kullanın: "
                "<code>...:PORT/?token=...</code></p></div>"
            ).encode("utf-8")
            self.send_response(401)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        # ---- helpers ----
        def _send(self, code: int, body: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _json(self, code: int, obj: dict[str, Any]) -> None:
            self._send(code, json.dumps(obj, ensure_ascii=False).encode("utf-8"),
                       "application/json; charset=utf-8")

        # ---- routes ----
        def do_GET(self) -> None:
            path = urllib.parse.urlparse(self.path).path

            # Liveness answers before the token gate. A probe that needs the
            # secret cannot tell the person who lost it whether the service is
            # up — and it was doing worse than that: a diagnostic script read
            # the 401 as "not running" while the panel was serving fine.
            # The open port already reveals that something is listening, so
            # a bare {"ok": true} gives an observer nothing new. Whether the
            # owner is mid-conversation is a different matter, so the state
            # is added only for a caller that holds the token.
            if path == "/health":
                # "jeton" tells a caller whether it needs one — not what it is.
                # An observer learns nothing new: requesting "/" already
                # answers the same question with a 401. Saying it here lets a
                # launcher open the right URL instead of a token page, which
                # is exactly the mistake the desktop launcher was making.
                govde: dict[str, Any] = {"ok": True, "jeton": bool(server.token)}
                if self._authorised():
                    govde["state"] = server.agent.state.state.value
                return self._json(200, govde)

            if path == "/favicon.ico":
                return self._serve_ico()

            if not self._authorised():
                return self._reject()
            if path in ("/", "/index.html"):
                return self._serve_panel()
            if path == "/moduller":
                return self._json(200, server.modul_verisi())
            if path.startswith("/speak/"):
                return self._serve_speech(path.rsplit("/", 1)[-1])
            if path == "/events":
                return self._serve_events()
            self._json(404, {"error": "bulunamadı"})

        def do_POST(self) -> None:
            if not self._authorised():
                return self._reject()
            path = urllib.parse.urlparse(self.path).path
            if path == "/listen":
                return self._handle_listen()
            if path == "/konus":
                return self._handle_konus()
            if path == "/gor":
                return self._handle_vision()
            if path == "/nesne":
                return self._handle_objects()
            if path == "/ocr":
                return self._handle_ocr()
            if path != "/ask":
                return self._json(404, {"error": "bulunamadı"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                payload = json.loads(self.rfile.read(length) or b"{}")
                text = str(payload.get("text", "")).strip()
            except (ValueError, json.JSONDecodeError):
                return self._json(400, {"error": "geçersiz istek"})
            if not text:
                return self._json(400, {"error": "boş mesaj"})
            try:
                answer, speech_id = server.ask(text)
                return self._json(200, {"answer": answer, "speech_id": speech_id})
            except Exception as exc:
                return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

        def _handle_listen(self) -> None:
            """Transcribe the posted recording locally and return the text."""
            audio = self._okunan_ses()
            if audio is None:
                return
            try:
                text = server.listen(audio, self.headers.get("Content-Type", ""))
            except STTError as exc:
                print(f"[mikrofon] çözümleme başarısız: {exc}", flush=True)
                return self._json(502, {"error": str(exc)})
            except Exception as exc:
                print(f"[mikrofon] beklenmeyen hata: {type(exc).__name__}: {exc}", flush=True)
                return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            return self._json(200, {"text": text})

        def _okunan_ses(self) -> bytes | None:
            """Read and bound the posted recording, or answer and return None.

            Shared by ``/listen`` and ``/konus``: two copies of a size check
            is one copy too many when the check is what keeps an arbitrary
            amount of audio out of memory.
            """
            if not server.stt.available:
                reason = getattr(server.stt, "reason", "Mikrofon yapılandırılmamış.")
                self._json(503, {"error": reason})
                return None
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(400, {"error": "geçersiz uzunluk"})
                return None
            if length <= 0:
                self._json(400, {"error": "boş kayıt"})
                return None
            # Okumadan ÖNCE denetleniyor: sınırın amacı zaten belleğe rastgele
            # büyüklükte veri çekilmesini engellemek.
            if length > MAX_AUDIO_BYTES:
                # Gövde okunmadan reddedildi; bu bağlantı artık kullanılamaz,
                # boşaltılmamış ses bir sonraki istek gibi görünürdü.
                self.close_connection = True
                self._json(413, {"error": "kayıt çok büyük"})
                return None
            return self.rfile.read(length)

        def _handle_konus(self) -> None:
            """Hands-free turn: transcribe and answer in one request.

            Separate from ``/listen`` because the trade-off is different, not
            because the code is: here nobody sees the sentence before the
            agent does, so the approval bar is raised for the turn (see
            :meth:`PanelServer.konus`).
            """
            audio = self._okunan_ses()
            if audio is None:
                return
            try:
                return self._json(200, server.konus(
                    audio, self.headers.get("Content-Type", "")))
            except STTError as exc:
                print(f"[mikrofon] çözümleme başarısız: {exc}", flush=True)
                return self._json(502, {"error": str(exc)})
            except Exception as exc:
                print(f"[mikrofon] beklenmeyen hata: {type(exc).__name__}: {exc}", flush=True)
                return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

        def _handle_vision(self) -> None:
            """Find faces in the posted frame. The frame itself is not kept."""
            if not server.vision.available:
                reason = getattr(server.vision, "reason", "Kamera yapılandırılmamış.")
                return self._json(503, {"error": reason})
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._json(400, {"error": "geçersiz uzunluk"})
            if length <= 0:
                return self._json(400, {"error": "boş kare"})
            if length > MAX_FRAME_BYTES:
                # Refused unread, so this connection cannot be reused.
                self.close_connection = True
                return self._json(413, {"error": "kare çok büyük"})

            kare = self.rfile.read(length)
            try:
                yuzler = server.vision.detect(kare)
            except VisionError as exc:
                print(f"[kamera] çözümleme başarısız: {exc}", flush=True)
                return self._json(502, {"error": str(exc)})
            except Exception as exc:
                print(f"[kamera] beklenmeyen hata: {type(exc).__name__}: {exc}", flush=True)
                return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})
            identity = None
            if server.face_recognizer.available and len(yuzler) == 1:
                try:
                    identity = server.face_recognizer.identify(kare).as_dict()
                except Exception as exc:
                    identity = {"known": False, "error": str(exc)}
            return self._json(200, {"yuz_sayisi": len(yuzler),
                                    "yuzler": [y.as_dict() for y in yuzler],
                                    "kimlik": identity})

        def _frame_for(self, provider) -> bytes | None:
            if not provider.available:
                self._json(503, {"error": getattr(provider, "reason", "Görsel analiz kapalı.")})
                return None
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                self._json(400, {"error": "geçersiz uzunluk"}); return None
            if length <= 0:
                self._json(400, {"error": "boş kare"}); return None
            if length > MAX_FRAME_BYTES:
                self.close_connection = True
                self._json(413, {"error": "kare çok büyük"}); return None
            return self.rfile.read(length)

        def _handle_objects(self) -> None:
            frame = self._frame_for(server.object_vision)
            if frame is None: return
            try:
                items = server.object_vision.detect(frame)
                return self._json(200, {"nesneler": [x.as_dict() for x in items]})
            except Exception as exc:
                return self._json(502, {"error": str(exc)})

        def _handle_ocr(self) -> None:
            frame = self._frame_for(server.ocr)
            if frame is None: return
            try:
                return self._json(200, server.ocr.read(frame).as_dict())
            except Exception as exc:
                return self._json(502, {"error": str(exc)})

        def _serve_ico(self) -> None:
            """Serve the app icon. Not secret, so it answers without a token:
            the window asks for it before any navigation carries one."""
            if not PANEL_ICO.is_file():
                return self._json(404, {"error": "simge yok"})
            govde = PANEL_ICO.read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "image/x-icon")
            self.send_header("Content-Length", str(len(govde)))
            self.send_header("Cache-Control", "max-age=86400")
            self.end_headers()
            self.wfile.write(govde)

        def _serve_panel(self) -> None:
            if not PANEL_HTML.is_file():
                return self._json(500, {"error": f"panel dosyası yok: {PANEL_HTML}"})
            html = PANEL_HTML.read_text(encoding="utf-8")
            # Asistan kimligi SAYFA ICINE gomuluyor, SSE ile beklenmiyor.
            # Acilis girisi harfleri sayfa yuklenir yuklenmez ciziyor; meta
            # olayini beklemek F.R.I.D.A.Y.'in girisinde bir an "J.A.R.V.I.S."
            # yazmasi demekti.
            html = html.replace("</head>", server._kimlik_betigi() + "</head>", 1)
            # Flip the panel into live mode without duplicating the file.
            html = html.replace("<body>", '<body data-live="1">', 1)
            body = html.encode("utf-8")
            # The panel changes as the project does; a cached copy silently
            # keeps running yesterday's code and looks like a broken feature.
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store, must-revalidate")
            if server.token:
                # Set once so later requests (and the SSE stream) carry it
                # without the token sitting in every URL.
                self.send_header(
                    "Set-Cookie",
                    f"jarvis_token={server.token}; Path=/; SameSite=Strict; Max-Age=604800",
                )
            self.end_headers()
            self.wfile.write(body)

        def _serve_speech(self, speech_id: str) -> None:
            """Return the answer as audio.

            The audio is buffered rather than chunk-streamed: a phone reaching
            this through a TCP relay, and Safari in particular, handle a plain
            response with a known length far more reliably than a chunked one.
            Answers are short, so the wait is small and the playback certain.
            """
            text = server.speech_text(speech_id)
            if text is None:
                return self._json(404, {"error": "ses bulunamadı"})
            if not server.tts.available:
                return self._json(503, {"error": "ses yapılandırılmamış"})

            # State is restored before any response is written: sending first
            # lets a client observe the reply while the machine is still marked
            # SPEAKING, which is both wrong and racy.
            server.agent.state.transition(JarvisState.SPEAKING)
            audio, hata = b"", None
            try:
                audio = b"".join(server.tts.synthesize(text))
            except TTSError as exc:
                # Printed, not swallowed: the panel tells the user to look here.
                print(f"[ses] sentez başarısız: {exc}", flush=True)
                hata = (502, str(exc))
            except Exception as exc:
                print(f"[ses] beklenmeyen hata: {type(exc).__name__}: {exc}", flush=True)
                hata = (500, f"{type(exc).__name__}: {exc}")
            server.agent.state.transition(JarvisState.STANDBY)

            if hata is not None:
                return self._json(hata[0], {"error": hata[1]})

            if not audio:
                print("[ses] sentezleyici boş yanıt döndü", flush=True)
                return self._json(502, {"error": "ses üretilemedi (boş yanıt)"})

            self.send_response(200)
            # Tür sağlayıcıdan geliyor: ElevenLabs MP3, Piper WAV veriyor.
            # Sabit yazmak ikinci sağlayıcıda sessizce bozardı.
            self.send_header("Content-Type",
                             getattr(server.tts, "mime", "audio/mpeg"))
            self.send_header("Content-Length", str(len(audio)))
            self.send_header("Accept-Ranges", "none")
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try:
                self.wfile.write(audio)
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass

        def _serve_events(self) -> None:
            q = server.hub.subscribe()
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Connection", "keep-alive")
            self.end_headers()
            try:
                while True:
                    try:
                        payload = q.get(timeout=15)
                    except queue.Empty:
                        payload = ": keep-alive\n\n"   # keeps proxies from closing us
                    self.wfile.write(payload.encode("utf-8"))
                    self.wfile.flush()
            except (BrokenPipeError, ConnectionResetError, OSError):
                pass
            finally:
                server.hub.unsubscribe(q)

    return Handler
