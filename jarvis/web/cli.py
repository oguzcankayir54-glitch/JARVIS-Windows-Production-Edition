"""``jarvis-panel`` — run the live Neural Core panel.

Starts the agent, serves the panel, and streams real state to it. Open the
printed URL in a browser: the Neural Core reacts to what the agent is
actually doing, and the telemetry is read from this machine.
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import webbrowser

from ..bootstrap import build_agent
from ..core.asistan import asistan_bul
from ..security.permissions import panel_approver
from ..config import load_config
from ..vision.detect import build_vision
from ..vision.objects import build_object_vision
from ..vision.ocr import build_ocr
from ..vision.identity import build_face_recognizer
from ..voice.stt import build_stt
from ..voice.tts import tts_from_config
from .server import PanelServer, sesli_taban


def _wsl_mi() -> bool:
    try:
        return "microsoft" in Path("/proc/version").read_text().lower()
    except OSError:
        return False


def _yerel_ip() -> str:
    """This machine's address on the local network.

    Uses a UDP socket's chosen source address rather than a hostname lookup,
    which is unreliable on machines with no resolvable hostname.
    """
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("192.168.1.1", 9))   # nothing is sent
            return sock.getsockname()[0]
    except OSError:
        return ""


def _windows_lan_ip() -> str:
    """The Windows host's address on the home network, asked of Windows itself.

    Under WSL2 the panel cannot see this address: its own interfaces are on
    the virtual 172.x network, and the phone has to reach the *Windows* side,
    which forwards inward. WSL can ask Windows directly through interop, and
    getting the answer here saves the one manual step people most often get
    wrong — pasting the WSL address into a phone that can never reach it.

    Entirely best-effort: interop can be disabled and PowerShell is slow to
    start, so a failure or a timeout just means the caller prints its usual
    instructions instead.
    """
    betik = (
        "(Get-NetIPAddress -AddressFamily IPv4 | "
        "Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '172.*' -and "
        "$_.IPAddress -notlike '169.254.*' } | Select-Object -First 1).IPAddress"
    )
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", betik],
            capture_output=True, text=True, timeout=6,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    aday = out.stdout.strip().splitlines()[0].strip() if out.stdout.strip() else ""
    # Validated rather than trusted: interop returns whatever Windows printed,
    # and a warning line would otherwise end up in the URL shown to the user.
    parcalar = aday.split(".")
    if len(parcalar) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parcalar):
        return aday
    return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis-panel", description="Canlı J.A.R.V.I.S. panelini başlat."
    )
    parser.add_argument("--port", type=int, default=8765, help="Port (varsayılan 8765)")
    parser.add_argument(
        "--host", default="127.0.0.1",
        help="Dinlenecek adres. Varsayılan 127.0.0.1 — yalnızca bu makine.",
    )
    parser.add_argument("--ac", action="store_true", help="Tarayıcıyı otomatik aç")
    parser.add_argument("--sessiz", action="store_true", help="Sesi kapat")
    parser.add_argument("--mikrofonsuz", action="store_true", help="Mikrofonu kapat")
    parser.add_argument("--kamera", action="store_true",
                        help="Kamerayı aç (varsayılan kapalı)")
    parser.add_argument("--jeton", help="Erişim jetonu (verilmezse ağa açıkken üretilir)")
    parser.add_argument("--jetonsuz", action="store_true",
                        help="Jeton kontrolünü kapat — YALNIZCA yerel kullanımda")
    args = parser.parse_args(argv)

    cfg = load_config()
    asistan = asistan_bul()
    # Panel bir istek iş parçacığında çalışıyor: varsayılan onaylayıcı stdin'den
    # okuduğu için HIGH/CRITICAL bir işlem tarayıcıyı sonsuza kadar bekletirdi.
    agent = build_agent(cfg, approver=panel_approver)
    tts = tts_from_config(cfg)
    if args.sessiz:
        from ..voice.tts import NullTTS
        tts = NullTTS()
    stt = build_stt(
        enabled=cfg.stt_enabled and not args.mikrofonsuz,
        model_size=cfg.stt_model, device=cfg.stt_device,
        compute_type=cfg.stt_compute_type, language=cfg.stt_language,
        beam_size=cfg.stt_beam_size,
        vad_min_silence_ms=cfg.stt_vad_min_silence_ms,
        vad_speech_pad_ms=cfg.stt_vad_speech_pad_ms,
        condition_on_previous_text=cfg.stt_condition_previous,
        hotwords=cfg.stt_hotwords,
        initial_prompt=cfg.stt_initial_prompt,
    )
    vision = build_vision(enabled=cfg.vision_enabled or args.kamera)
    object_vision = build_object_vision(enabled=cfg.object_vision_enabled)
    ocr = build_ocr(enabled=cfg.ocr_enabled)
    face_recognizer = build_face_recognizer(
        enabled=cfg.face_recognition_enabled,
        path=cfg.data_dir / "face_templates.json",
    )
    # The panel can run terminal commands, so anything beyond this machine
    # needs a token. Generated automatically rather than left to be forgotten.
    yerel = args.host in ("127.0.0.1", "localhost")
    if args.jetonsuz:
        token = ""
    elif args.jeton:
        token = args.jeton
    elif not yerel:
        token = os.getenv("JARVIS_PANEL_TOKEN") or secrets.token_urlsafe(12)
    else:
        token = os.getenv("JARVIS_PANEL_TOKEN", "")

    # LLM yoklamasi sunucu KURULMADAN once: sonuc hem acilis banner'ina
    # hem de panele gidiyor. Bu proje ayni dersi uc kez aldi (kamera, Piper,
    # Edge): kurulu olmayan bir seyin "hazir" gorunmesi, hatanin konusmanin
    # ORTASINDA cikmasi demek.
    _llm_eksik = ""
    if cfg.llm_provider == "ollama":
        from ..llm.ollama_provider import ollama_hazir
        _llm_eksik = ollama_hazir(cfg.ollama_host, cfg.ollama_model)

    server = PanelServer(agent, host=args.host, port=args.port, tts=tts,
                         token=token, stt=stt, vision=vision,
                         object_vision=object_vision, ocr=ocr,
                         face_recognizer=face_recognizer,
                         sesli_onay_tabani=sesli_taban(cfg.sesli_taban),
                         llm_uyari=_llm_eksik)

    url = f"http://{'localhost' if args.host in ('127.0.0.1', '0.0.0.0') else args.host}:{args.port}"
    print("=" * 58)
    print(f"  {asistan.ad}  ·  Canlı Panel")
    print(f"  Adres    : {url}")
    print(f"  LLM      : {cfg.llm_provider}"
          + ("  ← SAHTE MODEL" if cfg.llm_provider == "mock" else f"  ({cfg.ollama_model})"))
    print(f"  Ses      : {tts.name if tts.available else 'kapalı'}"
          + ("  (ücretsiz · yerel)" if tts.name == "piper" else ""))
    if stt.available:
        print(f"  Mikrofon : {stt.name} · {stt.model_size} · {stt.device}")
    else:
        print("  Mikrofon : kapalı")
    print(f"  Kamera   : {vision.name if vision.available else 'kapalı'}")
    print("  Durdurmak için: Ctrl-C")
    print("=" * 58)

    # Ollama seciliyse ACILISTA yokla. Bu proje ayni dersi uc kez aldi
    # (kamera, Piper, Edge): kurulu olmayan bir seyin "hazir" gorunmesi,
    # hatanin konusmanin ORTASINDA cikmasi demek.
    if _llm_eksik:
        print()
        print("  " + "!" * 54)
        for _satir in _llm_eksik.splitlines():
            print(f"  !  {_satir}")
        print("  " + "!" * 54)

    if cfg.llm_provider == "mock":
        # Bu satir bir uyari kutusu, cunku sessiz bir satir olarak fark
        # edilmedi: "beni tanimiyor", "soyledigim hicbir seyi algilamiyor"
        # ve "Turkce yerine Ingilizce cevap veriyor" sikayetlerinin ucu de
        # bu duruma isaret ediyordu. Mock bir anahtar kelime esleyicisi;
        # sistem istemini, kimligi ve baglami HIC okumuyor.
        print()
        print("  " + "!" * 54)
        print("  !  DIKKAT: Gercek bir dil modeli YOK.")
        print("  !")
        print("  !  Su an 'mock' saglayici calisiyor: anahtar kelime esleyen")
        print("  !  sahte bir model. Sizi TANIMAZ, soylediginizi ANLAMAZ,")
        print("  !  yalnizca birkac kalip cevap dondurur. Panelde gordugunuz")
        print("  !  'algilamiyor' davranisinin sebebi budur.")
        print("  !")
        print("  !  Gercek modele gecmek icin .env dosyaniza:")
        print("  !      JARVIS_LLM_PROVIDER=ollama")
        print("  !      JARVIS_OLLAMA_MODEL=qwen2.5:14b-instruct")
        print("  !  ve Ollama kurulu olmali:  https://ollama.com/download")
        print("  " + "!" * 54)

    if not stt.available and cfg.stt_enabled and not args.mikrofonsuz:
        # Only worth saying when the user has not switched it off themselves.
        print()
        print(f"  ℹ {getattr(stt, 'reason', '')}")

    if token:
        adres = f"{url}/?token={token}"
        print()
        print("  Bu adresi kullanın (jeton dahil):")
        print(f"    {adres}")
        if not yerel:
            ip = _yerel_ip()
            if _wsl_mi():
                # WSL has its own virtual network; a phone cannot reach this
                # address. It must go to the Windows host, which forwards here.
                print()
                print(f"  WSL2 · bu adres WSL'in kendi ağı ({ip or 'bilinmiyor'}) —")
                print("  telefon buraya ULAŞAMAZ, Windows üzerinden geçmeli.")
                win = _windows_lan_ip()
                if win:
                    print()
                    print("  TELEFONDAN:")
                    print(f"    http://{win}:{args.port}/?token={token}")
                print()
                print("  Yönlendirme WSL her yeniden başladığında yenilenmeli.")
                print("  PowerShell'i yönetici açıp:")
                print("      powershell -ExecutionPolicy Bypass -File \\\\wsl$\\Ubuntu"
                      f"\\home\\{os.getenv('USER', 'kullanici')}\\jarvis\\scripts"
                      "\\windows-yonlendirme.ps1")
            elif ip:
                print(f"    http://{ip}:{args.port}/?token={token}")
        print()
        print("  Jetonu paylaşmayın; bu adres makineye komut çalıştırabilir.")
        print()

    if not yerel:
        print("  ⚠  Panel bu makine dışına açıldı. Yalnızca güvendiğiniz bir ağda")
        print("     kullanın; jetonu bilen herkes bu makinede komut çalıştırabilir.")
        if not token:
            print("  ⚠  JETON KAPALI — bu ağdaki herkes panele erişebilir.")
        print()

    if args.ac:
        try:
            webbrowser.open(url)
        except Exception:
            pass

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nPanel kapatıldı.")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
