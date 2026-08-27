"""``jarvis-karsilastir`` — is the bigger model actually better, for your work?

Puts the same questions to two or more local models and writes a blind
comparison sheet plus a separate answer key. Read the sheet, pick a winner
per question, *then* open the key.

The point is to decide a hardware purchase on evidence. A model that needs a
card you do not own can still be judged here: it offloads to RAM and answers
slowly, but the answer is the one the bigger card would have produced.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from ..config import load_config
from ..core.persona import build_system_prompt
from ..llm.base import Message
from ..llm.ollama_provider import OllamaProvider
from ..memory.store import MemoryStore
from .compare import (
    TOOL_PROBLARI, load_questions, render_blind, render_key, render_tool_report,
    run_comparison, run_tool_check,
)

VARSAYILAN_SORULAR = Path(__file__).resolve().parents[2] / "docs" / "karsilastirma-sorulari.txt"


def _build_asker(host: str, timeout: float, system_prompt: str):
    """Return an ``ask(model, question) -> text`` bound to one Ollama server."""
    def ask(model: str, question: str) -> str:
        provider = OllamaProvider(host, model, timeout=timeout)
        mesajlar = [Message(role="system", content=system_prompt),
                    Message(role="user", content=question)]
        # No tools on purpose: this measures the model's own reasoning, and a
        # tool call would answer from the machine instead of from the model.
        return provider.chat(mesajlar).content
    return ask


def _build_tool_asker(host: str, timeout: float, system_prompt: str, registry):
    """Return ``ask(model, question) -> (tool names, text)`` with real schemas.

    The real registry is used rather than a toy schema: what matters is
    whether the model copes with the tools J.A.R.V.I.S. actually carries,
    including their Turkish descriptions and parameter names.
    """
    semalar = registry.schemas()

    def ask(model: str, question: str) -> tuple[list[str], str]:
        provider = OllamaProvider(host, model, timeout=timeout)
        yanit = provider.chat(
            [Message(role="system", content=system_prompt),
             Message(role="user", content=question)],
            tools=semalar,
        )
        return [c.name for c in yanit.tool_calls], yanit.content
    return ask


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis-karsilastir",
        description="İki veya daha fazla yerel modeli kör olarak karşılaştır.",
    )
    parser.add_argument("modeller", nargs="*",
                        help="Ollama model adları (en az iki tane)")
    parser.add_argument("--sorular", metavar="DOSYA",
                        help=f"Soru dosyası (varsayılan: {VARSAYILAN_SORULAR.name})")
    parser.add_argument("--cikti", metavar="KLASÖR", default="karsilastirma",
                        help="Sonuçların yazılacağı klasör (varsayılan: karsilastirma/)")
    parser.add_argument("--zaman-asimi", type=float, default=600.0, metavar="SN",
                        help="Cevap başına üst sınır (varsayılan 600 sn — "
                             "karta sığmayan model çok yavaşlar)")
    parser.add_argument("--kimliksiz", action="store_true",
                        help="Kişisel kimlik bilgisi olmadan sor (yalın karşılaştırma)")
    parser.add_argument("--araclar", action="store_true",
                        help="Yalnızca araç çağırma testi (hızlı) — prose karşılaştırması yapma")
    args = parser.parse_args(argv)

    if len(args.modeller) < 2:
        parser.error("en az iki model adı verin, örn: "
                     "jarvis-karsilastir qwen2.5:14b-instruct qwen2.5:32b-instruct")

    cfg = load_config()

    soru_yolu = Path(args.sorular) if args.sorular else VARSAYILAN_SORULAR
    if not soru_yolu.is_file():
        print(f"✗ Soru dosyası bulunamadı: {soru_yolu}")
        return 1
    sorular = load_questions(soru_yolu.read_text(encoding="utf-8"))
    if not sorular:
        print(f"✗ {soru_yolu} içinde soru yok.")
        return 1

    # Same persona both models see, so the comparison is of the models and
    # not of two different framings.
    if args.kimliksiz:
        sistem = build_system_prompt(None, "")
    else:
        store = MemoryStore(cfg.memory_db_path)
        sistem = build_system_prompt(store.get_owner(), "")

    # ── araç çağırma testi ──
    # Ayrı ve kısa tutuldu: bir modelin bu iş için uygun olup olmadığına dair
    # en hızlı elemeyi bu yapar. Uzun prose karşılaştırmasını çalıştırıp
    # sonunda modelin araç çağıramadığını öğrenmek saatlerin boşa gitmesidir.
    if args.araclar:
        from ..bootstrap import build_agent
        agent = build_agent(cfg, memory=MemoryStore(":memory:"))
        gecerli = [t.name for t in agent.registry.all()]

        print("=" * 58)
        print("  Araç çağırma testi")
        print(f"  Modeller : {', '.join(args.modeller)}")
        print(f"  Araç     : {len(gecerli)} tanımlı · {len(TOOL_PROBLARI)} deneme/model")
        print("=" * 58)
        print()

        def arac_ilerleme(model: str, i: int, n: int) -> None:
            print(f"  {model} · {i}/{n}", flush=True)

        raporlar = run_tool_check(
            args.modeller,
            _build_tool_asker(cfg.ollama_host, args.zaman_asimi, sistem, agent.registry),
            gecerli_adlar=gecerli, on_progress=arac_ilerleme,
        )
        klasor = Path(args.cikti)
        klasor.mkdir(parents=True, exist_ok=True)
        yol = klasor / "arac-testi.md"
        metin = render_tool_report(raporlar)
        yol.write_text(metin, encoding="utf-8")
        print()
        print(metin)
        print(f"  ✓ Yazıldı: {yol}")
        return 0

    toplam = len(sorular) * len(args.modeller)
    print("=" * 58)
    print("  Kör model karşılaştırması")
    print(f"  Modeller  : {', '.join(args.modeller)}")
    print(f"  Soru      : {len(sorular)}")
    print(f"  Toplam    : {toplam} cevap")
    print(f"  Sunucu    : {cfg.ollama_host}")
    print("=" * 58)
    print()
    print("  Karta sığmayan bir model RAM'e taşar ve cevap başına dakikalar")
    print("  sürebilir. Bu normaldir — ölçtüğümüz şey hız değil, kalite.")
    print()

    sayac = {"n": 0}

    def ilerleme(soru_no: int, soru_toplam: int, model: str) -> None:
        sayac["n"] += 1
        print(f"  [{sayac['n']:>3}/{toplam}] soru {soru_no}/{soru_toplam} · {model}",
              flush=True)

    turlar = run_comparison(
        args.modeller, sorular,
        _build_asker(cfg.ollama_host, args.zaman_asimi, sistem),
        on_progress=ilerleme,
    )

    hatalar = [c for t in turlar for c in t.answers if not c.ok]
    klasor = Path(args.cikti)
    klasor.mkdir(parents=True, exist_ok=True)
    kor = klasor / "kor-karsilastirma.md"
    anahtar = klasor / "cevap-anahtari.md"
    kor.write_text(render_blind(turlar), encoding="utf-8")
    anahtar.write_text(render_key(turlar), encoding="utf-8")

    print()
    if hatalar:
        print(f"  ! {len(hatalar)} cevap alınamadı:")
        for c in hatalar[:5]:
            print(f"      {c.model}: {c.error}")
        if len(hatalar) > 5:
            print(f"      … ve {len(hatalar) - 5} tane daha")
        print("    Model inmemişse:  ollama pull <model>")
        print()

    print(f"  ✓ Kör sayfa      : {kor}")
    print(f"  ✓ Cevap anahtarı : {anahtar}")
    print()
    print("  ÖNCE kör sayfayı okuyup her soruda bir tercih yapın.")
    print("  Anahtara sonra bakın — hangisinin büyük model olduğunu bilmek,")
    print("  cevabı okuma biçiminizi değiştirir.")
    print()
    return 1 if len(hatalar) == len(turlar) * len(args.modeller) else 0


if __name__ == "__main__":
    sys.exit(main())
