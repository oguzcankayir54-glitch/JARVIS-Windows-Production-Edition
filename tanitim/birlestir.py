"""Anlatımı sahne sırasına dizip videoyla birleştir.

Her anlatım parçasının arkasına, o sahnenin kalan süresi kadar sessizlik
ekleniyor. Böylece ses akışı ile görüntü akışı aynı zaman çizgisinde
kalıyor ve sahneler kaymadan ilerliyor.

``--muzik`` verilirse altına bir müzik yatağı seriliyor. İki aşamalı
kısılıyor:

1. Sabit bir zayıflatma (``--muzik-db``, varsayılan -21 dB).
2. **Yan zincir sıkıştırma**: anlatım konuşurken müzik ayrıca kısılıyor,
   sustuğunda kendiliğinden geri geliyor.

İkincisi olmadan tek bir seviye bulmak imkânsız: konuşmanın üstünde
duyulmayacak kadar kısık bir müzik, aralarda da duyulmuyor. Yan zincir,
"sesi boğmadan" isteğinin teknik karşılığı.

Telifli bir parçayı kendiniz veriyorsanız lisansı sizde olmalı.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BURASI = Path(__file__).resolve().parent


def ffmpeg_yolu() -> str:
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        return "ffmpeg"


#: Müziğin anlatıma göre sabit zayıflatması (dB).
#:
#: Ölçülerek seçildi, kulaktan dolma değil. Yan zincirli karışımda müziğin
#: anlatım seviyesine oranı:
#:
#:     dB     boşlukta   konuşurken
#:     -21         6%          1%     (neredeyse duyulmuyor)
#:     -14        14%          3%
#:      -9        24%          5%     <- seçilen
#:      -7        30%          6%
#:
#: -21 dB ilk denemeydi ve müzik boşluklarda bile duyulmuyordu; müzik
#: koymanın anlamı kalmıyordu. -9 dB'de boşluklarda gerçekten var, konuşma
#: sırasında ise sesin yirmide biri — "boğmadan" istenen şey bu.
VARSAYILAN_MUZIK_DB = -9.0


def _ayikla(argv: list[str]) -> tuple[list[str], str, float]:
    """``--muzik YOL`` ve ``--muzik-db N`` bayraklarını konumsal argümanlardan ayır."""
    kalan: list[str] = []
    muzik, db = "", VARSAYILAN_MUZIK_DB
    i = 0
    while i < len(argv):
        if argv[i] == "--muzik" and i + 1 < len(argv):
            muzik = argv[i + 1]; i += 2
        elif argv[i] == "--muzik-db" and i + 1 < len(argv):
            db = float(argv[i + 1]); i += 2
        else:
            kalan.append(argv[i]); i += 1
    return kalan, muzik, db


def main(argv: list[str] | None = None) -> int:
    argv, muzik, muzik_db = _ayikla(argv or [])
    klasor = Path(argv[0]) if argv else BURASI / "cikti"
    zaman_yolu = klasor / "zamanlama.json"
    video = klasor / "panel.webm"

    for gereken in (zaman_yolu, video):
        if not gereken.is_file():
            print(f"✗ {gereken} yok. Önce anlatim_uret.py ve video_cek.py.")
            return 1

    ff = ffmpeg_yolu()
    zaman = json.loads(zaman_yolu.read_text(encoding="utf-8"))

    girdiler: list[str] = []
    parcalar: list[str] = []
    for i, s in enumerate(zaman):
        girdiler += ["-i", str(klasor / s["dosya"])]
        bosluk = max(0.0, s["sahne_sure"] - s["ses_sure"])
        parcalar.append(f"[{i}:a]apad=pad_dur={bosluk:.3f}[a{i}]")

    filtre = (";".join(parcalar) + ";"
              + "".join(f"[a{i}]" for i in range(len(zaman)))
              + f"concat=n={len(zaman)}:v=0:a=1[out]")

    anlatim = klasor / "anlatim.wav"
    subprocess.run([ff, "-y", *girdiler, "-filter_complex", filtre,
                    "-map", "[out]", "-c:a", "pcm_s16le", str(anlatim)],
                   check=True, capture_output=True)

    ses_yolu = anlatim
    if muzik:
        if not Path(muzik).is_file():
            print(f"✗ müzik dosyası yok: {muzik}")
            return 1
        ses_yolu = klasor / "karisim.wav"
        toplam = sum(s["sahne_sure"] for s in zaman)
        kazanc = 10 ** (muzik_db / 20.0)
        # [1] muzik: videonun boyuna kirp, kenarlarini yumusat, zayiflat.
        # sidechaincompress: anahtar anlatim; konusurken muzik geriye
        # cekiliyor, susunca geri geliyor.
        karisim = (
            f"[1:a]atrim=0:{toplam:.3f},asetpts=N/SR/TB,"
            f"afade=t=in:st=0:d=2,afade=t=out:st={max(0.0, toplam - 3):.3f}:d=3,"
            f"volume={kazanc:.4f}[muz];"
            f"[0:a]asplit=2[anlt][anahtar];"
            f"[muz][anahtar]sidechaincompress="
            f"threshold=0.03:ratio=8:attack=8:release=420[duck];"
            f"[anlt][duck]amix=inputs=2:duration=first:normalize=0,"
            f"alimiter=limit=0.95[son]"
        )
        subprocess.run([ff, "-y", "-i", str(anlatim), "-i", muzik,
                        "-filter_complex", karisim, "-map", "[son]",
                        "-c:a", "pcm_s16le", str(ses_yolu)],
                       check=True, capture_output=True)
        print(f"  müzik: {Path(muzik).name} @ {muzik_db:.0f} dB, yan zincirli")

    # H.264 + AAC: telefonda da, tarayicida da, sunum programinda da oynar.
    son = klasor / "JARVIS-tanitim.mp4"
    subprocess.run([ff, "-y", "-i", str(video), "-i", str(ses_yolu),
                    "-c:v", "libx264", "-preset", "medium", "-crf", "21",
                    "-pix_fmt", "yuv420p", "-r", "30",
                    "-c:a", "aac", "-b:a", "192k", "-shortest", str(son)],
                   check=True, capture_output=True)

    print(f"✓ {son}  ({son.stat().st_size / 1024 / 1024:.1f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
