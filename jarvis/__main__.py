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
from .voice.tts import TTSError, play_stream_kesilebilir, tts_from_config


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
    if cfg.ollama_preload and hasattr(agent.llm, "warmup"):
        print("· Qwen modeli ısıtılıyor…", flush=True)
        try:
            agent.llm.warmup()
            print("· Qwen hazır; ilk mesaj beklemeyecek.", flush=True)
        except Exception as exc:
            print(f"! Qwen ön yükleme başarısız: {type(exc).__name__}", flush=True)

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

    #: Süren seslendirme. JARVIS konuşurken de yazabilmek için oynatma
    #: artık bloklamıyor; bir sonraki tur başladığında kesiliyor.
    oynatim = None

    while True:
        try:
            text = input("\nsen › ").strip()
        except (EOFError, KeyboardInterrupt):
            if oynatim is not None:
                oynatim.kes()
            print(f"\n{etiket} › Görüşürüz.")
            return 0

        # Sözünü kesme. Kullanıcı bir şey yazdıysa JARVIS'in söyleyeceği
        # şeyin geri kalanı artık geçersiz: yanlış anlaşılmış bir cevabı
        # sonuna kadar dinlemek zorunda kalmanın tek sebebi, oynatmanın
        # bloklamasıydı.
        if oynatim is not None:
            if oynatim.calisiyor:
                oynatim.kes()
                print("   (ses kesildi)")
            if oynatim.hata is not None:
                print(f"   (ses hatası: {oynatim.hata})")
                speak = False
            oynatim = None
            agent.state.transition(JarvisState.STANDBY)

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
                # Beklemeden dönüyor: konuşma sürerken istem geri geliyor.
                # Sentezleyici hatası artık besleme parçacığında doğduğu
                # için burada değil, bir sonraki turun başında görülüyor —
                # oradaki ``oynatim.hata`` denetimi bunun karşılığı.
                oynatim = play_stream_kesilebilir(tts.synthesize(answer))
                if oynatim is None:
                    print("   (ses oynatıcı yok — 'sudo apt install ffmpeg')")
                    speak = False
                    agent.state.transition(JarvisState.STANDBY)
            except TTSError as exc:
                # A voice failure must not end the conversation.
                print(f"   (ses hatası: {exc})")
                speak = False
                agent.state.transition(JarvisState.STANDBY)


if __name__ == "__main__":
    sys.exit(main())
