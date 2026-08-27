"""Tanıtım anlatımı — J.A.R.V.I.S.'in kendi sesiyle.

Anlatımı projenin kendi seslendirme katmanı üretiyor (Edge sağlayıcısı,
tr-TR-AhmetNeural). Bu tanıtımın en dürüst yanı: duyduğunuz ses, ürünün
gerçekten çıkardığı ses. Ayrı bir spiker kaydı olsaydı tanıtım, ürünün
yapamadığı bir şeyi gösteriyor olurdu.

Her sahnenin metni ve süresi burada; video yakalayıcı aynı süreleri
kullanıyor, böylece ses ile görüntü kaymıyor.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Sahne:
    ad: str
    metin: str
    #: Bu sahnenin ekranda kalacağı en az süre (saniye). Ses daha uzun
    #: sürerse video onu bekliyor — konuşma yarıda kesilmemeli.
    en_az_sure: float


SAHNELER: tuple[Sahne, ...] = (
    Sahne("giris", (
        "J.A.R.V.I.S. Kişisel bir teknik asistan. "
        "Bilgisayar teknik servisi için tasarlandı ve geliştirildi."
    ), 13.0),

    Sahne("panel", (
        "Açılıştaki her satır gerçek. Model, araç sayısı, bilgi tabanı ve "
        "ses sağlayıcısı, uydurma bir yükleme çubuğu değil, "
        "sistemin o anki durumu."
    ), 9.0),

    Sahne("telemetri", (
        "Panel sürekli ölçüyor. İşlemci, bellek, disk ve sıcaklık "
        "değerleri makineden okunuyor. Okunamayan bir değer boş kalıyor; "
        "tahmin edilmiş bir sayı gösterilmiyor."
    ), 10.0),

    Sahne("moduller", (
        "Dokuz modül. Hafıza, bilgi tabanı, ses, mikrofon, kamera, "
        "internet ve güvenlik. Her sekme kendi gerçek durumunu bildiriyor."
    ), 9.0),

    Sahne("soru", (
        "Soru yazıyorsunuz, cevap veriyor ve sesli okuyor. "
        "Cevap Türkçe. Kaynak İngilizce olsa bile Türkçe."
    ), 8.0),

    Sahne("mikrofon", (
        "Mikrofon düğmesine bir kez dokunun ve konuşun. "
        "Sustuğunuzda cevap gelir. Yazı kutusuna hiçbir şey yazılmaz, "
        "tuşa basmak gerekmez."
    ), 10.0),

    Sahne("guvenlik", (
        "Her araç bir risk seviyesi taşıyor. Okuyan araçlar serbest, "
        "sistemi değiştirenler onay istiyor, geri dönüşü olmayanlar "
        "yazılı onay istiyor. Bir web sayfası ya da belge asla komut veremez; "
        "onlar veridir, talimat değil."
    ), 13.0),

    Sahne("kapanis", (
        "J.A.R.V.I.S. Tasarlayan ve geliştiren: Oğuz Kayır."
    ), 6.0),
)
