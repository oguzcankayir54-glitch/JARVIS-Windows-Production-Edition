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
    GET  /manifest.webmanifest  installable mobile-app metadata (no secrets)

**Binds to 127.0.0.1 by default and should stay there.** This endpoint can
run terminal commands through the agent, so exposing it on a LAN address
hands that capability to anyone who can reach the port.
"""
from __future__ import annotations

import hmac
import json
import queue
import sys
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import psutil

from ..core.agent import Agent
from ..core.events import Event
from ..core.state import JarvisState
from ..rag.index import RagError
from ..core.asistan import asistan_bul
from ..security.permissions import RiskLevel
from ..vision.detect import MAX_FRAME_BYTES, VisionError, build_vision
from ..core.command_guide import panel_rows
from ..core.maintenance_commands import command_catalog, run_maintenance
from ..core.custom_commands import CustomCommandStore
from ..diagnostics import DiagnosticEngine, DiagnosticError
from ..diagnostics.health import collect_health
from ..diagnostics.duyuru import DuyuruAyari, Duyurucu
from ..diagnostics.monitor import MonitorConfig, ProactiveMonitor
from ..vision.objects import build_object_vision
from ..vision.ocr import build_ocr
from ..vision.identity import build_face_recognizer
from ..vision.pipeline import VisionPipeline
from ..vision.screenshot import build_screenshot
from ..tools.vision_tools import register_vision_tools
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
from ..agenda.notifier import ReminderService
from ..agenda.store import AgendaError

PANEL_HTML = Path(__file__).resolve().parents[2] / "docs" / "mockups" / "jarvis-panel.html"
#: Uygulama penceresinin baslik cubugundaki ve gorev cubugundaki simge
#: buradan geliyor: tarayici sayfanin favicon'unu kullaniyor.
PANEL_ICO = Path(__file__).resolve().parents[2] / "windows" / "jarvis.ico"

# Panel aramasının model bağlamını veya tarayıcıyı sınırsız içerikle
# doldurmasına izin verilmez.
RAG_SORGU_KARAKTER = 500
RAG_SONUC_LIMITI = 8
RAG_ONIZLEME_KARAKTER = 900


class _PanelHTTPServer(ThreadingHTTPServer):
    """Hide routine browser disconnects without hiding real server errors."""

    def handle_error(self, request, client_address) -> None:
        error = sys.exc_info()[1]
        if isinstance(error, (ConnectionResetError, BrokenPipeError)):
            return
        super().handle_error(request, client_address)

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
                 screenshot=None, vision_pipeline: VisionPipeline | None = None,
                 custom_commands: CustomCommandStore | None = None,
                 sesli_onay_tabani: RiskLevel = RiskLevel.MEDIUM,
                 rag_auto_paths=(), rag_sync_interval: float = 60.0,
                 llm_uyari: str = "", reminder_interval: float = 30.0,
                 acceptance_report=None,
                 monitor_config: MonitorConfig | None = None,
                 duyuru_ayari: DuyuruAyari | None = None) -> None:
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
        self.screenshot = screenshot if screenshot is not None else build_screenshot(False)
        camera_controller = getattr(agent, "camera_controller", None)
        if camera_controller is not None:
            camera_controller.bind(self.vision)
        self.vision_pipeline = vision_pipeline or VisionPipeline(
            faces=self.vision, objects=self.object_vision, ocr=self.ocr,
            identity=self.face_recognizer, screenshot=self.screenshot,
            state=agent.state, events=agent.events,
        )
        if self.screenshot.available:
            register_vision_tools(agent.registry, self.vision_pipeline)
            agent.response_engine.tool_names.add("masaustu_analiz")
        # An access token is required whenever the panel is reachable beyond
        # this machine: it can run terminal commands, so anyone who can open
        # the page can drive the host. Empty token = no check (localhost only).
        self.token = token or ""
        self.sesli_onay_tabani = sesli_onay_tabani
        #: LLM acilista yoklanip buraya yaziliyor; bos ise sorun yok.
        self.llm_uyari = llm_uyari
        trace_path = getattr(agent.trace_log, "path", None)
        custom_path = trace_path.parent / "custom_commands.json" if trace_path else None
        self.custom_commands = custom_commands or CustomCommandStore(custom_path)
        self.diagnostics = DiagnosticEngine(agent.cases) if agent.cases is not None else None
        self.agenda = getattr(agent, "agenda", None)
        self.reminders = ReminderService(self.agenda, agent.cases) if self.agenda else None
        self.reminder_interval = max(1.0, float(reminder_interval))
        self.acceptance_report = acceptance_report
        self.hub = EventHub()
        self._agent_lock = threading.Lock()
        self._speech: dict[str, str] = {}
        self._speech_lock = threading.Lock()
        self._httpd: ThreadingHTTPServer | None = None
        self._stop = threading.Event()
        self._background_threads: list[threading.Thread] = []
        self._health_lock = threading.Lock()
        self._health_cache: dict[str, Any] | None = None
        self._health_cached_at = 0.0
        self._command_lock = threading.Lock()
        self._command_results: dict[str, dict[str, Any]] = {}
        self.monitor = ProactiveMonitor(
            agent.events, monitor_config or MonitorConfig(enabled=False))
        # Monitor ölçüyordu, panel gösteriyordu, ama kimse SÖYLEMİYORDU.
        # Ekrana bakmıyorsanız diskin %97 olduğunu öğrenmiyordunuz.
        self.duyurucu = Duyurucu(agent.events, self._duyuruyu_seslendir,
                                 duyuru_ayari or DuyuruAyari())
        self._last_resource_monitor = 0.0
        self.rag_auto_paths = tuple(Path(p).expanduser() for p in rag_auto_paths)
        self.rag_sync_interval = max(0.05, float(rag_sync_interval))
        self._rag_sync_lock = threading.Lock()
        self._rag_sync = {
            "durum": "bekliyor" if self.rag_auto_paths else "kapalı",
            "yollar": len(self.rag_auto_paths), "son": 0.0, "hata": "",
            "eklenen": 0, "guncellenen": 0, "silinen": 0,
        }

        self._state_unsubscribe = agent.state.subscribe(self._on_state)
        self._event_unsubscribe = agent.events.subscribe("*", self._on_core_event)
        self.hub.publish("state", {"state": agent.state.state.value,
                                   "label": agent.state.state.label_tr})
        self.hub.publish("meta", self._meta())

    def health_report(self, *, refresh: bool = False) -> dict[str, Any]:
        """Return a measured report; avoid repeating heavy probes on every paint."""
        with self._health_lock:
            if (not refresh and self._health_cache is not None
                    and time.time() - self._health_cached_at < 15.0):
                return self._health_cache
            report = collect_health(self.agent, tts=self.tts, stt=self.stt)
            self._health_cache = report
            self._health_cached_at = time.time()
        self.agent.events.publish(
            "system.health", {"score": report["score"], "status": report["status"]},
            source="health",
        )
        return report

    def maintenance_rows(self) -> list[dict[str, Any]]:
        with self._command_lock:
            results = dict(self._command_results)
        rows = []
        for item in command_catalog():
            row = item.as_dict()
            row.update({"ad": "Bakım", "deger": item.command,
                        "aciklama": item.label, "komut": item.command,
                        "bakim": "1", "last_result": results.get(item.id)})
            rows.append(row)
        return rows

    def run_maintenance(self, command_id: str) -> dict[str, Any]:
        item = next((x for x in command_catalog() if x.id == command_id), None)
        if item is None:
            raise ValueError("bilinmeyen bakım komutu")
        self.agent.events.publish("tool.started", {"tool": f"maintenance:{item.id}"},
                                  source="health-panel")
        result = run_maintenance(item.id, cwd=Path.cwd())
        with self._command_lock:
            self._command_results[item.id] = result
        self.agent.events.publish(
            "tool.finished" if result["ok"] else "tool.error",
            {"tool": f"maintenance:{item.id}", "ok": result["ok"],
             "returncode": result["returncode"]}, source="health-panel",
        )
        return result

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
        kullanim = dict(getattr(self.agent.llm, "son_kullanim", {}) or {})
        return {
            # A snapshot: a later turn must not mutate metadata already queued
            # for an SSE client.
            "llm_kullanim": kullanim,
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
            "screenshot": self.screenshot.available,
            "multi_agent": self.agent.supervisor.enabled,
            "active_agent_role": (
                self.agent.active_delegation.role.value
                if self.agent.active_delegation is not None else None
            ),
            "last_agent_role": (
                self.agent.last_delegation.role.value
                if self.agent.last_delegation is not None else None
            ),
            **self._rag_meta(),
            # Vision understanding is still staged; guided diagnostics is live.
            "vision": False,
            "diagnostic_engine": self.diagnostics is not None,
        }

    def _rag_meta(self) -> dict[str, Any]:
        """Knowledge-base numbers, or an honest zero.

        An empty index and a broken one look the same from the panel, so the
        count is what decides whether the row reads as live — not the mere
        presence of a store.
        """
        kb = getattr(self.agent, "knowledge", None)
        if kb is None:
            with self._rag_sync_lock:
                sync = dict(self._rag_sync)
            return {"rag": False, "rag_parca": 0, "rag_belge": 0,
                    "rag_anlam": False, "rag_sync": sync}
        try:
            d = kb.stats()
        except Exception:
            with self._rag_sync_lock:
                sync = dict(self._rag_sync)
            return {"rag": False, "rag_parca": 0, "rag_belge": 0,
                    "rag_anlam": False, "rag_sync": sync}
        with self._rag_sync_lock:
            sync = dict(self._rag_sync)
        return {
            "rag": bool(d.get("parca")),
            "rag_parca": int(d.get("parca", 0)),
            "rag_belge": int(d.get("belge", 0)),
            "rag_anlam": bool(d.get("anlam_aramasi")),
            "rag_sync": sync,
        }

    def bilgi_ara(self, sorgu: str, limit: int = 5) -> dict[str, Any]:
        """Search indexed documents for the panel, with bounded output."""
        kb = getattr(self.agent, "knowledge", None)
        if kb is None:
            raise RuntimeError("Bilgi tabanı bağlı değil.")
        sorgu = (sorgu or "").strip()
        if not sorgu:
            raise ValueError("boş sorgu")
        if len(sorgu) > RAG_SORGU_KARAKTER:
            raise ValueError(f"sorgu çok uzun (en fazla {RAG_SORGU_KARAKTER} karakter)")
        try:
            sayi = max(1, min(int(limit), RAG_SONUC_LIMITI))
        except (TypeError, ValueError):
            sayi = 5
        basladi = time.time()
        hitler = kb.search(sorgu, limit=sayi)
        return {
            "sorgu": sorgu, "adet": len(hitler),
            "sure_ms": int((time.time() - basladi) * 1000),
            "sonuclar": [
                {**h.as_dict(), "metin": h.metin[:RAG_ONIZLEME_KARAKTER]}
                for h in hitler
            ],
        }

    def teshis_baslat(self, vaka_no: int, playbook: str) -> dict[str, Any]:
        if self.diagnostics is None:
            raise DiagnosticError("Teşhis motoru bağlı değil.")
        result = self.diagnostics.start(int(vaka_no), playbook)
        self.hub.publish("diagnostic", result, retain=False)
        return result

    def teshis_yanitla(self, oturum_no: int, secenek: str) -> dict[str, Any]:
        if self.diagnostics is None:
            raise DiagnosticError("Teşhis motoru bağlı değil.")
        result = self.diagnostics.answer(int(oturum_no), secenek)
        self.hub.publish("diagnostic", result, retain=False)
        return result

    def _rag_sync_loop(self) -> None:
        """Synchronise explicitly configured roots until the panel stops."""
        kb = getattr(self.agent, "knowledge", None)
        if kb is None or not self.rag_auto_paths:
            return
        while not self._stop.is_set():
            toplam = {"eklenen": 0, "guncellenen": 0, "silinen": 0}
            hatalar = []
            with self._rag_sync_lock:
                self._rag_sync["durum"] = "çalışıyor"
            for yol in self.rag_auto_paths:
                if self._stop.is_set():
                    return
                try:
                    rapor = kb.index_path(yol, silinenleri_unut=True)
                    for ad in toplam:
                        toplam[ad] += int(getattr(rapor, ad))
                except Exception as exc:
                    hatalar.append(f"{yol}: {exc}")
            with self._rag_sync_lock:
                self._rag_sync.update(toplam)
                self._rag_sync.update({
                    "durum": "hata" if hatalar else "hazır",
                    "son": time.time(), "hata": " · ".join(hatalar)[:500],
                })
            self.hub.publish("meta", self._meta())
            if self._stop.wait(self.rag_sync_interval):
                return

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
                "satirlar": [{"ad": f"#{v.id} {v.customer}",
                               "deger": f"{v.device} · {v.status}",
                               "aciklama": v.symptom}
                             for v in acik],
                "playbooklar": self.diagnostics.list_playbooks()
                if self.diagnostics is not None else [],
            }

        def bilgi() -> dict[str, Any]:
            kb = getattr(self.agent, "knowledge", None)
            if kb is None:
                return {"durum": "yok", "ozet": "bilgi tabanı bağlı değil", "satirlar": []}
            d = kb.stats()
            with self._rag_sync_lock:
                sync = dict(self._rag_sync)
            sync_degeri = ("kapalı" if not sync["yollar"] else
                            f"{sync['durum']} · {sync['yollar']} yol")
            sync_satirlari = [{"ad": "Otomatik eşitleme", "deger": sync_degeri}]
            if sync["hata"]:
                sync_satirlari.append({"ad": "Eşitleme hatası", "deger": sync["hata"]})
            if not d.get("parca"):
                return {"durum": "bos", "ozet": "boş — henüz belge eklenmedi",
                        "satirlar": [{"ad": "Eklemek için",
                                      "deger": "jarvis-bilgi ekle <klasör>"}]
                                    + sync_satirlari}
            belgeler = kb.documents(limit=8)
            return {
                "durum": "hazir",
                "ozet": f"{d['belge']} belge · {d['parca']} parça",
                "satirlar": [
                    {"ad": "Arama", "deger":
                     "anlam + kelime" if d["anlam_aramasi"] else "yalnızca kelime"},
                    {"ad": "Gömme modeli", "deger": d["model"] or "(yok)"},
                ] + sync_satirlari + [
                    {"ad": b["yol"].rsplit("/", 1)[-1], "deger": f"{b['parca']} parça"}
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
            satirlar = self.maintenance_rows() + panel_rows() + [
                {"ad": "Kişisel", "deger": item.phrase,
                 "aciklama": f"Öğretilen karşılık: {item.expansion}", "komut": item.phrase,
                 "kisisel": "1"}
                for item in self.custom_commands.all()
            ]
            return {
                "durum": "hazir",
                "ozet": f"{len(satirlar)} komut · {len(self.custom_commands.all())} kişisel",
                "satirlar": satirlar,
            }

        def kayitlar() -> dict[str, Any]:
            traces = list(self.agent.trace_log.entries[-12:])
            errors = sum(t.response_status != "ok" for t in traces)
            return {"durum": "hazir" if traces else "bos",
                    "ozet": f"{len(traces)} son işlem · {errors} hata",
                    "satirlar": [
                        {"ad": t.detected_intent,
                         "deger": f"{t.response_status} · {t.latency_ms:.0f} ms",
                         "aciklama": t.error or ", ".join(t.tools_used) or "araç kullanılmadı"}
                        for t in reversed(traces)]}

        def saglik() -> dict[str, Any]:
            report = self.health_report()
            return {
                "durum": ("hazir" if report["status"] == "OPERATIONAL" else
                           "uyari" if report["status"] == "DEGRADED" else "kritik"),
                "ozet": f"{report['score']} / 100 · {report['status']}",
                "score": report["score"], "status": report["status"],
                "checked_at": report["checked_at"],
                "categories": report["categories"],
                "satirlar": [{"ad": item["label"],
                               "deger": f"{item['value']} · {item['status'].upper()}",
                               "aciklama": item["category"]}
                              for item in report["checks"]],
            }

        def ajanda() -> dict[str, Any]:
            if self.agenda is None:
                return {"durum": "yok", "ozet": "ajanda bağlı değil", "satirlar": []}
            now = time.time()
            items = self.agenda.list("acik")
            promised = self.agent.cases.promised_cases(now + 86400) if self.agent.cases else []
            rows = [{"ad": f"#{x.id} {x.title}", "deger": x.kind,
                     "aciklama": time.strftime("%d.%m.%Y %H:%M", time.localtime(x.due_ts)),
                     "kayit_no": x.id, "gecikti": x.due_ts < now} for x in items]
            rows += [{"ad": f"Vaka #{x.id} · {x.customer}", "deger": "teslim",
                      "aciklama": time.strftime("%d.%m.%Y %H:%M", time.localtime(x.promised_ts))}
                     for x in promised]
            overdue = sum(x.due_ts < now for x in items)
            return {"durum": "uyari" if overdue else ("hazir" if rows else "bos"),
                    "ozet": f"{len(rows)} açık · {overdue} geciken" if rows else "henüz kayıt yok",
                    "satirlar": rows}

        def kabul() -> dict[str, Any]:
            if self.acceptance_report is None:
                return {"durum": "yok", "ozet": "kabul testi çalıştırılmadı", "satirlar": []}
            report = self.acceptance_report.as_dict()
            counts = report["counts"]
            return {
                "durum": report["status"],
                "ozet": f"{counts['hazir']} hazır · {counts['eksik']} eksik · {counts['arizali']} arızalı",
                "satirlar": [{"ad": x["name"], "deger": x["status"],
                               "aciklama": x["detail"] +
                               (f" · Çözüm: {x['fix']}" if x["fix"] and x["status"] != "hazir" else "")}
                              for x in report["checks"]],
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
            "kayitlar": guvenli(kayitlar, {"durum": "yok", "ozet": "log okunamadı", "satirlar": []}),
            "saglik": guvenli(saglik, {"durum": "yok", "ozet": "sağlık ölçülemedi", "satirlar": []}),
            "ajanda": guvenli(ajanda, {"durum": "yok", "ozet": "ajanda okunamadı", "satirlar": []}),
            "kabul": guvenli(kabul, {"durum": "yok", "ozet": "kabul raporu okunamadı", "satirlar": []}),
        }

    # ---------------- agent plumbing ----------------

    def _on_state(self, old: JarvisState, new: JarvisState) -> None:
        self.hub.publish("state", {"state": new.value, "label": new.label_tr})

    def _on_core_event(self, event: Event) -> None:
        """Bridge core events to SSE without coupling core modules to the GUI."""
        self.hub.publish(event.name, event.as_dict(), retain=False)

    def ask(self, text: str, *, speech: SpeechNormalization | None = None,
            approved_high: bool = False
            ) -> tuple[str, str | None]:
        """One agent turn, serialised — the agent holds mutable history.

        Returns the answer and, when speech is configured, an id the panel can
        stream audio from. The text is synthesised on request rather than here
        so the written answer appears immediately instead of waiting on audio.
        """
        self.hub.publish("transcript", {"role": "user", "text": text}, retain=False)
        resolved = self.custom_commands.resolve(text)
        agent_text = resolved or text
        with self._agent_lock:
            permissions = self.agent.tools.permissions
            previous_approver = permissions.approver
            if approved_high and speech is None:
                # Browser approval is deliberately valid for this one turn and
                # HIGH only. CRITICAL operations still require typed CLI approval.
                permissions.approver = lambda _tool, risk, _args, _prompt: risk == RiskLevel.HIGH
            try:
                if speech is None:
                    stream = self.agent.ask_stream(agent_text)
                    pieces: list[str] = []
                    for piece in stream:
                        pieces.append(piece)
                        self.hub.publish("parca", {"text": piece}, retain=False)
                    answer = "".join(pieces)
                else:
                    # Keep the structured speech contract on ``ask``.  The
                    # hands-free endpoint returns one combined audio response
                    # and existing callers monkeypatch/observe this boundary.
                    answer = self.agent.ask(
                        agent_text,
                        original_text=speech.original_text,
                        speech_confidence=speech.confidence,
                        speech_ambiguity=speech.ambiguity,
                    )
            finally:
                permissions.approver = previous_approver
        self.hub.publish("transcript", {"role": "assistant", "text": answer}, retain=False)

        return answer, self._speech_kaydet(answer)

    def _duyuruyu_seslendir(self, metin: str) -> None:
        """Sesli duyuruyu panele gönder.

        Sentez BURADA yapılmıyor. Olay otobüsü teslimatı senkron: yavaş
        bir abone bütün yayını bekletir (bkz. :mod:`jarvis.core.events`)
        ve ses üretimi saniyeler sürebilir — monitörün bir sonraki ölçüm
        turunu bekletirdi. Panel metnin kimliğini alıp sesi ``/speech/<id>``
        ucundan kendisi çekiyor; cevap sesiyle tamamen aynı yol.

        Ses kapalıysa sessizce çıkılıyor: bildirimin kendisi zaten
        ``system.alert`` olayıyla ekrana düşmüş oluyor.
        """
        speech_id = self._speech_kaydet(metin)
        if speech_id is None:
            return
        self.hub.publish("duyuru", {"text": metin, "speech_id": speech_id},
                         retain=False)

    def _speech_kaydet(self, metin: str) -> str | None:
        """Bir metni oynatılmak üzere kaydet, kimliğini döndür.

        Cevap sesi ve sesli duyuru aynı yolu kullanıyor. Ayrı yazılsalardı
        önbellek sınırı birinde düzeltilip diğerinde unutulurdu — bu
        depoda ``ask``/``ask_stream`` tam bu yüzden ortak yardımcılara
        bölünmüştü.
        """
        if not (self.tts.available and metin.strip()):
            return None
        speech_id = uuid.uuid4().hex[:16]
        with self._speech_lock:
            self._speech[speech_id] = metin
            # Keep the cache small; these are only needed for one playback.
            while len(self._speech) > 20:
                self._speech.pop(next(iter(self._speech)))
        return speech_id

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
        self.agent.events.publish(
            "voice.input", {"bytes": len(audio), "content_type": content_type},
            source="voice",
        )
        self.agent.events.publish("voice.listening", {"stt": self.stt.name},
                                  source="voice")
        try:
            raw = self.stt.transcribe(audio, content_type)
            preliminary = self.speech_normalizer.normalize(raw)
            risk = self.agent.intent_router.route(preliminary.normalized_text).risk
            result = self.speech_normalizer.normalize(raw, risk=risk)
        except Exception as exc:
            self.agent.events.publish(
                "voice.error", {"stage": "stt", "error_type": type(exc).__name__},
                source="voice",
            )
            raise
        self.agent.events.publish(
            "voice.finished",
            {"stage": "stt", "characters": len(result.normalized_text),
             "confidence": result.confidence},
            source="voice",
        )
        return result

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
                telemetry = collect_telemetry()
                self.hub.publish("telemetry", telemetry)
                now = time.monotonic()
                if (self.monitor.config.enabled
                        and now - self._last_resource_monitor
                        >= self.monitor.config.interval):
                    self.monitor.evaluate_telemetry(telemetry)
                    self._last_resource_monitor = now
            except Exception:
                pass  # a telemetry hiccup must never kill the server
            self._stop.wait(TELEMETRY_PERIOD_S)

    def _monitor_loop(self) -> None:
        """Run slower service/model probes independently from UI telemetry."""
        config = self.monitor.config
        if not config.enabled:
            return
        while not self._stop.is_set():
            try:
                self.monitor.evaluate_health(self.health_report(refresh=True))
                self.monitor.report_success("monitor.health")
            except Exception as exc:
                self.monitor.report_error(
                    "monitor.health", "Sağlık kontrolü tamamlanamadı",
                    error_type=type(exc).__name__,
                )
            if self._stop.wait(config.health_interval):
                return

    def _reminder_loop(self) -> None:
        while not self._stop.is_set():
            try:
                for event in self.reminders.run_once():
                    self.hub.publish("agenda", event, retain=False)
            except Exception:
                pass
            self._stop.wait(self.reminder_interval)

    # ---------------- lifecycle ----------------

    def _start_background(self, target, name: str) -> None:
        thread = threading.Thread(target=target, name=name, daemon=True)
        self._background_threads.append(thread)
        thread.start()

    def serve_forever(self) -> None:
        handler = _make_handler(self)
        self._httpd = _PanelHTTPServer((self.host, self.port), handler)
        self._httpd.daemon_threads = True
        self._start_background(self._telemetry_loop, "jarvis-telemetry")
        if self.monitor.config.enabled:
            self._start_background(self._monitor_loop, "jarvis-proactive-monitor")
        if self.reminders is not None:
            self._start_background(self._reminder_loop, "jarvis-reminders")
        if self.rag_auto_paths:
            self._start_background(self._rag_sync_loop, "jarvis-rag-sync")
        try:
            self._httpd.serve_forever()
        finally:
            self._stop.set()

    def shutdown(self) -> None:
        self._stop.set()
        self._state_unsubscribe()
        self._event_unsubscribe()
        if self._httpd is not None:
            self._httpd.shutdown()
        current = threading.current_thread()
        for thread in tuple(self._background_threads):
            if thread is not current:
                thread.join(timeout=25.0)
        self._background_threads = [t for t in self._background_threads if t.is_alive()]
        self.monitor.close()
        self.duyurucu.close()
        self.vision_pipeline.close()
        close_tts = getattr(self.tts, "close", None)
        if callable(close_tts):
            close_tts()


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
            if path == "/manifest.webmanifest":
                return self._serve_manifest()

            if not self._authorised():
                return self._reject()
            if path in ("/", "/index.html"):
                return self._serve_panel()
            if path == "/moduller":
                return self._json(200, server.modul_verisi())
            if path == "/system-health":
                return self._json(200, server.health_report())
            if path == "/maintenance-commands":
                return self._json(200, {"commands": server.maintenance_rows()})
            if path.startswith("/speak/"):
                return self._serve_speech(path.rsplit("/", 1)[-1])
            if path == "/events":
                return self._serve_events()
            self._json(404, {"error": "bulunamadı"})

        def do_POST(self) -> None:
            if not self._authorised():
                return self._reject()
            path = urllib.parse.urlparse(self.path).path
            if path == "/bilgi/ara":
                return self._handle_bilgi_ara()
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
            if path == "/vision/analyze":
                return self._handle_vision_analysis()
            if path == "/vision/screenshot":
                return self._handle_screenshot()
            if path == "/komut-ogret":
                return self._handle_custom_command()
            if path == "/komut-sil":
                return self._handle_custom_command(delete=True)
            if path == "/komut-analiz":
                return self._handle_command_analysis()
            if path == "/health/refresh":
                return self._json(200, server.health_report(refresh=True))
            if path == "/maintenance/run":
                return self._handle_maintenance_run()
            if path == "/teshis/baslat":
                return self._handle_diagnostic(start=True)
            if path == "/teshis/yanit":
                return self._handle_diagnostic(start=False)
            if path == "/ajanda/ekle":
                return self._handle_agenda("ekle")
            if path == "/ajanda/durum":
                return self._handle_agenda("durum")
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
                answer, speech_id = server.ask(
                    text, approved_high=bool(payload.get("approve_high", False)))
                return self._json(200, {"answer": answer, "speech_id": speech_id})
            except Exception as exc:
                return self._json(500, {"error": f"{type(exc).__name__}: {exc}"})

        def _handle_custom_command(self, *, delete: bool = False) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 4096:
                    return self._json(400, {"error": "geçersiz istek boyutu"})
                payload = json.loads(self.rfile.read(length))
                phrase = str(payload.get("phrase", "")).strip()
                if delete:
                    return self._json(200, {"deleted": server.custom_commands.delete(phrase)})
                item = server.custom_commands.teach(
                    phrase, str(payload.get("expansion", "")).strip())
                return self._json(200, {"saved": True, "phrase": item.phrase,
                                        "expansion": item.expansion})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc)})

        def _handle_maintenance_run(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 1024:
                    return self._json(400, {"error": "geçersiz istek boyutu"})
                payload = json.loads(self.rfile.read(length))
                command_id = str(payload.get("id", "")).strip()
                return self._json(200, server.run_maintenance(command_id))
            except PermissionError as exc:
                return self._json(403, {"error": str(exc)})
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc)})

        def _handle_command_analysis(self) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 4096:
                    return self._json(400, {"error": "geçersiz istek boyutu"})
                payload = json.loads(self.rfile.read(length))
                original = str(payload.get("text", "")).strip()
                if not original:
                    return self._json(400, {"error": "boş mesaj"})
                resolved = server.custom_commands.resolve(original) or original
                decision = server.agent.intent_router.route(resolved)
                return self._json(200, {
                    "intent": decision.intent.value,
                    "risk": decision.risk.label,
                    "needs_confirmation": decision.needs_confirmation,
                    "reason": decision.reason,
                    "resolved": resolved if resolved != original else "",
                })
            except (ValueError, TypeError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc)})

        def _handle_bilgi_ara(self) -> None:
            """Bounded, read-only knowledge search for the Bilgi tab."""
            try:
                length = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                return self._json(400, {"error": "geçersiz uzunluk"})
            if length <= 0 or length > 4096:
                return self._json(400 if length <= 0 else 413,
                                  {"error": "boş istek" if length <= 0 else
                                   "arama isteği çok büyük"})
            try:
                payload = json.loads(self.rfile.read(length))
                sorgu = str(payload.get("sorgu", ""))
                limit = payload.get("limit", 5)
                return self._json(200, server.bilgi_ara(sorgu, limit))
            except json.JSONDecodeError:
                return self._json(400, {"error": "geçersiz istek"})
            except (ValueError, RagError) as exc:
                return self._json(400, {"error": str(exc)})
            except Exception as exc:
                return self._json(500, {"error": f"Bilgi tabanı okunamadı: {exc}"})

        def _handle_diagnostic(self, *, start: bool) -> None:
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 4096:
                    return self._json(400 if length <= 0 else 413,
                                      {"error": "geçersiz istek boyutu"})
                payload = json.loads(self.rfile.read(length))
                if start:
                    result = server.teshis_baslat(
                        int(payload.get("vaka_no", 0)), str(payload.get("playbook", "")))
                else:
                    result = server.teshis_yanitla(
                        int(payload.get("oturum_no", 0)), str(payload.get("secenek", "")))
                return self._json(200, result)
            except (ValueError, TypeError, json.JSONDecodeError, DiagnosticError) as exc:
                return self._json(400, {"error": str(exc)})
            except Exception as exc:
                return self._json(500, {"error": f"Teşhis işlemi başarısız: {exc}"})

        def _handle_agenda(self, action: str) -> None:
            if server.agenda is None:
                return self._json(503, {"error": "ajanda bağlı değil"})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 8192:
                    return self._json(400 if length <= 0 else 413, {"error": "geçersiz istek boyutu"})
                p = json.loads(self.rfile.read(length))
                if action == "ekle":
                    item = server.agenda.create(str(p.get("baslik", "")), str(p.get("tur", "")),
                        p.get("son_tarih", ""), p.get("hatirlatma"), str(p.get("notlar", "")),
                        p.get("vaka_no"))
                else:
                    item = server.agenda.set_status(int(p.get("kayit_no", 0)),
                                                    str(p.get("durum", "")))
                server.hub.publish("agenda", {"action": action, "item": item.as_dict()}, retain=False)
                return self._json(200, {"ok": True, "kayit": item.as_dict()})
            except (AgendaError, ValueError, TypeError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc)})

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
                with server._agent_lock:
                    sonuc = server.vision_pipeline.submit(
                        kare, tasks=("faces",), source="camera"
                    ).result(timeout=120.0)
                yuzler = sonuc.analyses["faces"]
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
                                    "yuzler": yuzler,
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
                with server._agent_lock:
                    result = server.vision_pipeline.submit(
                        frame, tasks=("objects",), source="camera"
                    ).result(timeout=120.0)
                items = result.analyses["objects"]
                return self._json(200, {"nesneler": items})
            except Exception as exc:
                return self._json(502, {"error": str(exc)})

        def _handle_ocr(self) -> None:
            frame = self._frame_for(server.ocr)
            if frame is None: return
            try:
                with server._agent_lock:
                    result = server.vision_pipeline.submit(
                        frame, tasks=("ocr",), source="camera"
                    ).result(timeout=120.0)
                return self._json(200, result.analyses["ocr"])
            except Exception as exc:
                return self._json(502, {"error": str(exc)})

        def _handle_vision_analysis(self) -> None:
            frame = self._frame_for(server.vision_pipeline)
            if frame is None:
                return
            query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            tasks = tuple(x.strip() for x in query.get("tasks", ["faces"])[0].split(",") if x.strip())
            try:
                with server._agent_lock:
                    result = server.vision_pipeline.submit(
                        frame, tasks=tasks, source="upload"
                    ).result(timeout=120.0)
                return self._json(200, result.as_dict())
            except (VisionError, ValueError) as exc:
                return self._json(400, {"error": str(exc)})
            except Exception as exc:
                return self._json(502, {"error": str(exc)})

        def _handle_screenshot(self) -> None:
            if not server.screenshot.available:
                return self._json(503, {"error": getattr(
                    server.screenshot, "reason", "Ekran görüntüsü kapalı.")})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 4096:
                    return self._json(413, {"error": "istek çok büyük"})
                body = json.loads(self.rfile.read(length) or b"{}")
                tasks = body.get("tasks", ["ocr"])
                with server._agent_lock:
                    result = server.vision_pipeline.capture_and_submit(
                        tasks=tasks
                    ).result(timeout=120.0)
                return self._json(200, result.as_dict())
            except (VisionError, ValueError, TypeError, json.JSONDecodeError) as exc:
                return self._json(400, {"error": str(exc)})
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

        def _serve_manifest(self) -> None:
            """Serve public install metadata without embedding the panel token."""
            manifest = {
                "id": "/",
                "name": "J.A.R.V.I.S. Neural Core",
                "short_name": "J.A.R.V.I.S.",
                "description": "Yerel yapay zeka teknisyen asistanı",
                "lang": "tr",
                "start_url": "/",
                "scope": "/",
                "display": "standalone",
                "orientation": "any",
                "background_color": "#05090e",
                "theme_color": "#05090e",
                "icons": [{
                    "src": "/favicon.ico",
                    "sizes": "16x16 20x20 24x24 32x32 40x40 48x48 64x64 128x128 256x256",
                    "type": "image/x-icon",
                    "purpose": "any",
                }],
            }
            body = json.dumps(manifest, ensure_ascii=False).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/manifest+json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(body)

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
            server.agent.events.publish(
                "voice.output", {"stage": "tts", "provider": server.tts.name},
                source="voice",
            )
            audio, hata = b"", None
            try:
                audio = b"".join(server.tts.synthesize(text))
            except TTSError as exc:
                # Printed, not swallowed: the panel tells the user to look here.
                print(f"[ses] sentez başarısız: {exc}", flush=True)
                hata = (502, str(exc))
                server.agent.events.publish(
                    "voice.error", {"stage": "tts", "error_type": type(exc).__name__},
                    source="voice",
                )
            except Exception as exc:
                print(f"[ses] beklenmeyen hata: {type(exc).__name__}: {exc}", flush=True)
                hata = (500, f"{type(exc).__name__}: {exc}")
                server.agent.events.publish(
                    "voice.error", {"stage": "tts", "error_type": type(exc).__name__},
                    source="voice",
                )
            server.agent.state.transition(JarvisState.STANDBY)

            if hata is not None:
                return self._json(hata[0], {"error": hata[1]})

            if not audio:
                print("[ses] sentezleyici boş yanıt döndü", flush=True)
                server.agent.events.publish(
                    "voice.error", {"stage": "tts", "error_type": "EMPTY_AUDIO"},
                    source="voice",
                )
                return self._json(502, {"error": "ses üretilemedi (boş yanıt)"})
            server.agent.events.publish(
                "voice.finished", {"stage": "tts", "bytes": len(audio)},
                source="voice",
            )

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
