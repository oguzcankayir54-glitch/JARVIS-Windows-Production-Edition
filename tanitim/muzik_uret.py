"""Tanıtım için müzik yatağı üret.

**Neden üretiliyor, hazır bir parça kullanılmıyor?**

İstenen parça AC/DC — Back In Black'ti. Telifli ticari bir kayıt: indirip
bir videoya gömmek ne yapılabilir ne de yapılmalı. Kendi lisanslı kopyanız
varsa ``birlestir.py --muzik`` ile onu koyabilirsiniz; karışım ayarları
zaten hazır. Bu dosya, o kopya yokken videonun müziksiz kalmaması için var.

**Ne üretiyor?**

Mi minörde, 94 vuruş, sürükleyici ama sade bir enstrümantal: kick, trampet,
hi-hat, bas ve hafif doyurulmuş güç akorları. Back In Black'in tempo ve
tonalitesine yakın, ama riff özgün.

**Sınırı açıkça:** bu dosyayı yazan taraf sonucu DİNLEYEMİYOR. Sayısal
olarak doğruluğu denetleniyor (tepe seviye, kırpma, süre, sessizlik yok),
ama "kulağa hoş geliyor mu" sorusunun cevabı dinleyene ait. Beğenmezseniz
karışımdan çıkarmak tek bayrak.
"""
from __future__ import annotations

import math
import struct
import sys
import wave
from pathlib import Path

ORNEK_HIZI = 44100
TEMPO = 94.0            # vuruş/dakika
VURUS = 60.0 / TEMPO    # bir vuruşun saniyesi

#: Mi minör pentatonik — riff bunun üstünde.
MI = 82.41              # E2


def _bos(saniye: float) -> list[float]:
    return [0.0] * int(saniye * ORNEK_HIZI)


def _kat(hedef: list[float], parca: list[float], baslangic: float,
         kazanc: float = 1.0) -> None:
    """Bir sesi zaman çizgisine ekle. Taşan kısım kırpılıyor, hata değil."""
    bas = int(baslangic * ORNEK_HIZI)
    for i, ornek in enumerate(parca):
        j = bas + i
        if 0 <= j < len(hedef):
            hedef[j] += ornek * kazanc


def _zarf(n: int, atak: float, sonme: float) -> list[float]:
    """Basit atak/sönme zarfı — tık sesini engelleyen şey bu."""
    a = max(1, int(atak * ORNEK_HIZI))
    cikti = []
    for i in range(n):
        if i < a:
            cikti.append(i / a)
        else:
            cikti.append(math.exp(-(i - a) / (sonme * ORNEK_HIZI)))
    return cikti


def kick(sure: float = 0.28) -> list[float]:
    """Alçalan bir sinüs: davulun gövdesi frekans süpürmesinden geliyor."""
    n = int(sure * ORNEK_HIZI)
    zarf = _zarf(n, 0.001, 0.055)
    faz, cikti = 0.0, []
    for i in range(n):
        frek = 110.0 * math.exp(-i / (0.02 * ORNEK_HIZI)) + 42.0
        faz += 2 * math.pi * frek / ORNEK_HIZI
        cikti.append(math.sin(faz) * zarf[i])
    return cikti


def _gurultu(n: int, tohum: int = 1) -> list[float]:
    """Yeniden üretilebilir gürültü: aynı tohum aynı sesi veriyor."""
    x, cikti = tohum, []
    for _ in range(n):
        x = (1103515245 * x + 12345) & 0x7FFFFFFF
        cikti.append((x / 0x3FFFFFFF) - 1.0)
    return cikti


def trampet(sure: float = 0.20) -> list[float]:
    n = int(sure * ORNEK_HIZI)
    zarf = _zarf(n, 0.001, 0.045)
    gur = _gurultu(n, 7)
    faz, cikti = 0.0, []
    for i in range(n):
        faz += 2 * math.pi * 185.0 / ORNEK_HIZI
        cikti.append((gur[i] * 0.75 + math.sin(faz) * 0.35) * zarf[i])
    return cikti


def hihat(sure: float = 0.06, tohum: int = 3) -> list[float]:
    n = int(sure * ORNEK_HIZI)
    zarf = _zarf(n, 0.0005, 0.012)
    gur = _gurultu(n, tohum)
    # Kaba yüksek geçiren: ardışık farkı almak bası siliyor.
    cikti = [0.0]
    for i in range(1, n):
        cikti.append((gur[i] - gur[i - 1]) * 0.5 * zarf[i])
    return cikti


def bas(frek: float, sure: float) -> list[float]:
    """Testere + sinüs karışımı, yumuşak doyurma ile."""
    n = int(sure * ORNEK_HIZI)
    zarf = _zarf(n, 0.004, sure * 0.55)
    faz, cikti = 0.0, []
    for i in range(n):
        faz += frek / ORNEK_HIZI
        testere = 2.0 * (faz % 1.0) - 1.0
        sinus = math.sin(2 * math.pi * faz)
        ham = testere * 0.45 + sinus * 0.55
        cikti.append(math.tanh(ham * 1.6) * zarf[i])
    return cikti


def guc_akoru(frek: float, sure: float) -> list[float]:
    """Kök + beşli, doyurulmuş. Rock gitarın en tanıdık sesi bu aralık."""
    n = int(sure * ORNEK_HIZI)
    zarf = _zarf(n, 0.006, sure * 0.5)
    f1, f2 = frek * 2, frek * 3          # oktav ve beşli
    p1 = p2 = 0.0
    cikti = []
    for i in range(n):
        p1 += f1 / ORNEK_HIZI
        p2 += f2 / ORNEK_HIZI
        ham = (2.0 * (p1 % 1.0) - 1.0) * 0.5 + (2.0 * (p2 % 1.0) - 1.0) * 0.5
        cikti.append(math.tanh(ham * 2.4) * 0.5 * zarf[i])
    return cikti


#: Riff: her eleman (yarım-ton kaydırma, vuruş cinsinden süre).
#: Mi minör pentatonik üstünde sade ve tekrar eden bir dizi.
RIFF = ((0, 1.0), (0, 0.5), (3, 0.5), (0, 1.0), (5, 0.5), (3, 0.5))


def _perde(yarim_ton: int) -> float:
    return MI * (2 ** (yarim_ton / 12.0))


def parca_uret(saniye: float) -> list[float]:
    """İstenen uzunlukta müzik. Girişte hafif, ortada dolu, sonda sönüyor."""
    zaman_cizgisi = _bos(saniye + 1.0)

    olcu = 4 * VURUS
    olcu_sayisi = int(saniye / olcu) + 1

    for o in range(olcu_sayisi):
        t0 = o * olcu
        if t0 > saniye:
            break
        # Ilk iki olcu sadece davul: giris nefes alsin.
        dolu = o >= 2

        # Davullar
        for v in range(4):
            t = t0 + v * VURUS
            if v in (0, 2):
                _kat(zaman_cizgisi, kick(), t, 0.9)
            if v in (1, 3):
                _kat(zaman_cizgisi, trampet(), t, 0.5)
            for yarim in (0.0, 0.5):
                _kat(zaman_cizgisi, hihat(tohum=3 + v), t + yarim * VURUS, 0.22)

        if not dolu:
            continue

        # Bas ve akorlar riff uzerinde
        t = t0
        for kaydirma, uzunluk in RIFF:
            sure = uzunluk * VURUS
            if t > saniye:
                break
            _kat(zaman_cizgisi, bas(_perde(kaydirma), sure), t, 0.55)
            _kat(zaman_cizgisi, guc_akoru(_perde(kaydirma), sure), t, 0.28)
            t += sure

    return zaman_cizgisi[:int(saniye * ORNEK_HIZI)]


def _kenarlari_yumusat(ses: list[float], sure: float = 2.0) -> None:
    n = min(int(sure * ORNEK_HIZI), len(ses) // 2)
    for i in range(n):
        k = i / n
        ses[i] *= k
        ses[-1 - i] *= k


def yaz(yol: Path, ses: list[float]) -> None:
    """16-bit mono WAV. Tepe -3 dBFS'e normalleniyor: kırpma yok."""
    tepe = max((abs(x) for x in ses), default=0.0) or 1.0
    olcek = 0.707 / tepe
    with wave.open(str(yol), "wb") as d:
        d.setnchannels(1)
        d.setsampwidth(2)
        d.setframerate(ORNEK_HIZI)
        d.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, x * olcek)) * 32767))
            for x in ses))


def main(argv: list[str] | None = None) -> int:
    argv = argv or []
    saniye = float(argv[0]) if argv else 100.0
    hedef = Path(argv[1]) if len(argv) > 1 else Path("muzik.wav")

    ses = parca_uret(saniye)
    _kenarlari_yumusat(ses)
    yaz(hedef, ses)

    tepe = max(abs(x) for x in ses)
    ortalama = sum(abs(x) for x in ses) / len(ses)
    print(f"✓ {hedef}  {len(ses) / ORNEK_HIZI:.1f}s  "
          f"tepe {tepe:.3f}  ortalama {ortalama:.3f}")
    if ortalama < 0.01:
        print("! Ses neredeyse sessiz — üretimde bir şey ters gitmiş.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
