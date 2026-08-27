"""``jarvis-bilgi`` — build and query the knowledge base from the terminal.

Indexing is a deliberate act with a visible result, not something that
happens quietly in the background: you point it at a directory, it tells you
what it took, what it skipped and why.
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from ..config import load_config
from .embed import build_embedder
from .index import KnowledgeBase, RagError

CIZGI = "─" * 62


def _kb(cfg, gomme: bool = True) -> KnowledgeBase:
    embedder = build_embedder(
        cfg.ollama_host, cfg.rag_embed_model,
        enabled=cfg.rag_embed_enabled and gomme,
    )
    return KnowledgeBase(cfg.knowledge_db_path, embedder=embedder)


def _ekle(kb: KnowledgeBase, yollar: list[str], sessiz: bool) -> int:
    for yol in yollar:
        print(f"İndeksleniyor: {yol}")
        sayac = {"n": 0}

        def ilerleme(dosya: str, parca: int) -> None:
            sayac["n"] += 1
            if not sessiz:
                kisa = dosya if len(dosya) < 58 else "…" + dosya[-57:]
                print(f"  · {kisa}  ({parca} parça)")

        try:
            rapor = kb.index_path(yol, ilerleme=ilerleme)
        except RagError as exc:
            print(f"  ! {exc}")
            return 1

        print(CIZGI)
        print("  " + rapor.ozet())
        if rapor.aday_disi:
            print(f"  {rapor.aday_disi} dosya metin değil (resim, ikili, üretilmiş)")
        if rapor.sebepler:
            ayrinti = " · ".join(f"{k}: {v}" for k, v in sorted(rapor.sebepler.items()))
            print(f"  Atlananlar → {ayrinti}")
        if rapor.gomme_notu:
            print()
            print("  ⚠ Anlam araması kapalı; yalnızca kelime araması çalışacak.")
            for satir in rapor.gomme_notu.splitlines():
                print(f"    {satir}")
        elif rapor.gomulen:
            print(f"  {rapor.gomulen} parça gömüldü ({kb.embedder.model})")
        print()
    return 0


def _ara(kb: KnowledgeBase, sorgu: str, limit: int, tam: bool) -> int:
    basladi = time.time()
    try:
        sonuclar = kb.search(sorgu, limit=limit)
    except RagError as exc:
        print(f"! {exc}")
        return 1
    gecen = int((time.time() - basladi) * 1000)

    durum = kb.stats()
    kip = "anlam + kelime" if durum["anlam_aramasi"] else "yalnızca kelime"
    print(CIZGI)
    print(f"  “{sorgu}”")
    print(f"  {len(sonuclar)} sonuç · {kip} · {gecen} ms")
    print(CIZGI)
    if not sonuclar:
        print("  Bulunamadı.")
        if not durum["parca"]:
            print("  Bilgi tabanı boş — önce: jarvis-bilgi ekle <klasör>")
        return 0

    for i, h in enumerate(sonuclar, start=1):
        print()
        print(f"  {i}. {h.kaynak}   [{h.neden}]  {h.puan:.4f}")
        if h.baslik:
            print(f"     {h.baslik}")
        govde = h.metin if tam else h.metin[:400]
        for satir in govde.splitlines():
            print(f"     │ {satir}")
        if not tam and len(h.metin) > 400:
            print("     │ …")
    print()
    return 0


def _durum(kb: KnowledgeBase) -> int:
    d = kb.stats()
    print(CIZGI)
    print("  J.A.R.V.I.S.  ·  Bilgi Tabanı")
    print(CIZGI)
    print(f"  Belge        : {d['belge']}")
    print(f"  Parça        : {d['parca']}")
    print(f"  Vektörlü     : {d['vektorlu']}"
          + (f" ({d['boyut']} boyut)" if d["boyut"] else ""))
    print(f"  Gömme modeli : {d['model'] or '(yok)'}")
    print(f"  Arama        : {'anlam + kelime' if d['anlam_aramasi'] else 'yalnızca kelime'}")
    if not d["anlam_aramasi"] and d["parca"]:
        print()
        print("  ⚠ Anlam araması kapalı. Açmak için:")
        print(f"      ollama pull {d['model'] or 'bge-m3'}")
        print("      jarvis-bilgi ekle <klasör>      # yeniden gömer")
    belgeler = kb.documents(limit=15)
    if belgeler:
        print()
        print("  Son eklenenler:")
        for b in belgeler:
            kisa = b["yol"] if len(b["yol"]) < 48 else "…" + b["yol"][-47:]
            print(f"    {b['parca']:>4} parça  {b['tur']:<6} {kisa}")
    print()
    return 0


def main(argv: list[str] | None = None) -> int:
    ayrıştırıcı = argparse.ArgumentParser(
        prog="jarvis-bilgi",
        description="J.A.R.V.I.S. bilgi tabanı: belge ve kod indeksle, ara.",
    )
    alt = ayrıştırıcı.add_subparsers(dest="komut")

    p_ekle = alt.add_parser("ekle", help="Klasör veya dosya indeksle")
    p_ekle.add_argument("yol", nargs="+", help="İndekslenecek klasör/dosya")
    p_ekle.add_argument("--sessiz", action="store_true", help="Dosya dosya yazma")
    p_ekle.add_argument("--gommesiz", action="store_true",
                        help="Yalnızca kelime indeksi kur (gömme yapma)")

    p_ara = alt.add_parser("ara", help="Bilgi tabanında ara")
    p_ara.add_argument("sorgu", nargs="+", help="Aranacak soru")
    p_ara.add_argument("-n", type=int, default=5, help="Sonuç sayısı (varsayılan 5)")
    p_ara.add_argument("--tam", action="store_true", help="Parçaları kısaltmadan göster")

    alt.add_parser("durum", help="Bilgi tabanının durumu")

    p_unut = alt.add_parser("unut", help="Bir belgeyi indeksten çıkar")
    p_unut.add_argument("yol", help="Belgenin indeksteki yolu")

    p_sifirla = alt.add_parser("sifirla", help="Bilgi tabanını tamamen boşalt")
    p_sifirla.add_argument("--evet", action="store_true", help="Onay sorma")

    args = ayrıştırıcı.parse_args(argv)
    if not args.komut:
        ayrıştırıcı.print_help()
        return 0

    cfg = load_config()

    if args.komut == "ekle":
        kb = _kb(cfg, gomme=not args.gommesiz)
        return _ekle(kb, args.yol, args.sessiz)
    if args.komut == "ara":
        kb = _kb(cfg)
        return _ara(kb, " ".join(args.sorgu), args.n, args.tam)
    if args.komut == "durum":
        return _durum(_kb(cfg))
    if args.komut == "unut":
        kb = _kb(cfg)
        # Kullanıcı göreli yol yazmış olabilir; indekste mutlak yol duruyor.
        hedef = args.yol
        if not kb.forget_document(hedef):
            hedef = str(Path(hedef).expanduser().resolve())
            if not kb.forget_document(hedef):
                print(f"! İndekste böyle bir belge yok: {args.yol}")
                return 1
        print(f"Unutuldu: {hedef}")
        return 0
    if args.komut == "sifirla":
        kb = _kb(cfg)
        d = kb.stats()
        if not args.evet:
            print(f"{d['belge']} belge, {d['parca']} parça silinecek.")
            cevap = input("Emin misiniz? (evet/hayır): ").strip().lower()
            if cevap not in ("evet", "e", "yes", "y"):
                print("Vazgeçildi.")
                return 0
        kb.clear()
        print("Bilgi tabanı boşaltıldı.")
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
