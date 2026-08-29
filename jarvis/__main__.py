"""Terminal entry point:  python -m jarvis

A minimal REPL that shows the state transitions in the prompt. With
``--sesli`` the reply is spoken through the configured local/cloud provider.
"""
from __future__ import annotations

import argparse
import atexit
import sys

from .bootstrap import build_agent
from .config import load_config
from .core.state import JarvisState
from .core.asistan import asistan_bul
from .voice.tts import TTSError, play_stream, tts_from_config


def _banner(provider: str, voice: str, asistan=None) -> None:
    asistan = asistan or asistan_bul()
    print("=" * 52)
    print(f"  {asistan.ad}  ·  Neural Core (terminal · V1)")
    print(f"  LLM: {provider}   |   Ses: {voice}")
    print("  çıkış: 'exit' / Ctrl-D")
    print("=" * 52)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog=asistan_bul().kod,
        description=f"{asistan_bul().ad} terminal asistanı")
    parser.add_argument("--sesli", action="store_true", help="Yanıtları yapılandırılmış sesle oku")
    parser.add_argument("--sessiz", action="store_true", help="Sesi kapat (.env'de açık olsa bile)")
    args = parser.parse_args(argv)

    cfg = load_config()
    asistan = asistan_bul()
    # Terminaldeki satir basi. Uzun ve noktali ad her satirda
    # okumayi zorlastiriyor; buyuk harfli sade ad yeterli.
    etiket = asistan.sade_ad.upper()
    agent = build_agent(cfg)

    speak = (args.sesli or cfg.voice_enabled) and not args.sessiz
    tts = tts_from_config(cfg)
    close_tts = getattr(tts, "close", None)
    if callable(close_tts):
        atexit.register(close_tts)
    if (speak and getattr(tts, "name", "") == "xtts"
            and getattr(cfg, "xtts_ready_before_listen", True)):
        print("· Craig sesi hazırlanıyor…", flush=True)
        try:
            tts.wait_ready()
        except TTSError as exc:
            print(f"! Craig sesi hazırlanamadı: {exc}")
            speak = False
    if speak and not tts.available:
        print("! Ses istendi ama yapılandırılmamış. Kontrol için: jarvis-ses --kontrol\n")
        speak = False

    # Reflect state changes live in the terminal (stand-in for the panel).
    agent.state.subscribe(lambda old, new: print(f"   · durum: {new.label_tr}", flush=True))

    _banner(cfg.llm_provider, tts.name if speak else "kapalı", asistan)
    agent.state.transition(JarvisState.STANDBY)

    while True:
        try:
            text = input("\nsen › ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{etiket} › Görüşürüz.")
            return 0
        if not text:
            continue
        if text.lower() in {"exit", "quit", "çık", "kapan"}:
            print(f"{etiket} › Görüşürüz.")
            return 0

        answer = agent.ask(text)
        print(f"{etiket} › {answer}")

        if speak:
            try:
                agent.state.transition(JarvisState.SPEAKING)
                if not play_stream(tts.synthesize(answer)):
                    print("   (ses oynatıcı yok — 'sudo apt install ffmpeg')")
                    speak = False
            except TTSError as exc:
                # A voice failure must not end the conversation.
                print(f"   (ses hatası: {exc})")
                speak = False
            finally:
                agent.state.transition(JarvisState.STANDBY)


if __name__ == "__main__":
    sys.exit(main())
