"""Anlatımı üret ve her sahnenin gerçek süresini ölç.

Ses projenin KENDİ seslendirme katmanından çıkıyor. Ayrı bir spiker kaydı
olsaydı tanıtım, ürünün yapamadığı bir şeyi göstermiş olurdu.

Süreler burada ölçülüyor çünkü sahne uzunlukları buradan geliyor: sabit
sayılar yazılsaydı ses ile görüntü kayardı.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

BURASI = Path(__file__).resolve().parent
sys.path.insert(0, str(BURASI))

from anlatim import SAHNELER  # noqa: E402


def sure_olc(yol: Path) -> float:
    """Bir ses dosyasının saniyesi."""
    from faster_whisper.audio import decode_audio
    return len(decode_audio(str(yol))) / 16000


def main(argv: list[str] | None = None) -> int:
    from jarvis.config import load_config
    from jarvis.voice.edge import EdgeTTS, edge_hazir

    eksik = edge_hazir()
    if eksik:
        print(f"✗ {eksik}")
        return 1

    cfg = load_config()
    hedef = Path(argv[0]) if argv else BURASI / "cikti"
    hedef.mkdir(parents=True, exist_ok=True)

    ses = EdgeTTS(cfg.edge_voice, speed=cfg.elevenlabs_speed, ca_bundle=cfg.edge_ca)

    bilgi = []
    for sahne in SAHNELER:
        yol = hedef / f"{sahne.ad}.mp3"
        yol.write_bytes(b"".join(ses.synthesize(sahne.metin)))
        sn = sure_olc(yol)
        # Sahne, sesten bir saniye uzun: cümle bitince görüntü hemen
        # değişirse kesik hissi veriyor.
        bilgi.append({
            "ad": sahne.ad,
            "dosya": yol.name,
            "ses_sure": round(sn, 2),
            "sahne_sure": round(max(sn + 1.0, sahne.en_az_sure), 2),
        })
        print(f"  {sahne.ad:10} ses {sn:5.2f}s → sahne {bilgi[-1]['sahne_sure']:5.2f}s")

    (hedef / "zamanlama.json").write_text(
        json.dumps(bilgi, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n✓ toplam {sum(b['sahne_sure'] for b in bilgi):.1f} saniye → {hedef}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
