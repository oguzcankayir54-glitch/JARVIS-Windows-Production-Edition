"""Edge — ücretsiz, anahtarsız, nöral Türkçe ses.

Piper yerelliği kazanıyordu, konuşmayı kaybediyordu. Ölçüm açık: aynı teknik
cümle sentezlenip Whisper ile geri yazıya döküldüğünde Piper'in Türkçe sesi
0.65 anlaşılırlık veriyor, Edge'in ``tr-TR-AhmetNeural`` sesi 0.82. Fark
kulakla da duyuluyor — Piper "Efendim"i bile "Esend'in" diye çıkarıyordu.

**Bedeli: bu ses yerel değil.** Metin Microsoft'un konuşma servisine gidiyor.
J.A.R.V.I.S.'in kuralı "ham ses ve görüntü makineden çıkmaz, cevaplar buluta
gidebilir" idi; seslendirilen şey zaten modele gitmiş olan cevap, dolayısıyla
yeni bir sızıntı sınıfı açılmıyor. Ama YEREL bir model kullanıyorsanız açılır:
o durumda ``JARVIS_TTS_PROVIDER=piper`` tek ayarla her şeyi makinede tutuyor.

İkinci bedel: bu resmî bir API değil, Edge tarayıcısının kullandığı uç. Kota
yok, anahtar yok, ama Microsoft'un bir garantisi de yok. Kesilirse Piper ve
ElevenLabs olduğu yerde duruyor — sağlayıcı seçimi tek satır.

Kütüphane isteğe bağlı: kurulu değilse burası sessizce devre dışı kalıyor,
``build_tts`` bir sonrakine geçiyor.
"""
from __future__ import annotations

import asyncio
import queue
import ssl
import threading
from typing import Iterator

from .tts import TTSError, normalize_for_speech

#: Ölçümde en iyi çıkan ses. Emel de aynı kalitede; erkek/kadın tercihi.
VARSAYILAN_SES = "tr-TR-AhmetNeural"

#: Bilinen Türkçe sesler — ``jarvis-ses --edge-sesler`` bunu listeliyor.
TURKCE_SESLER = ("tr-TR-AhmetNeural", "tr-TR-EmelNeural")

#: Bir cevabın sentezi için üst sınır.
ZAMAN_ASIMI = 60.0

#: Üreticiden tüketiciye parça kuyruğunun sınırı. Sınırsız bırakmak uzun bir
#: cevabın tamamını belleğe alırdı; akış zaten parça parça tüketiliyor.
KUYRUK_SINIRI = 64

_BITTI = object()


def _yuzde(speed: float) -> str:
    """Dışarıdaki "hız" ayarını Edge'in beklediği yüzdeye çevir.

    1.0 → ``+0%``. Ölçümde +12% anlaşılırlığı 0.82'den 0.76'ya düşürdü, o
    yüzden varsayılan hızlandırma yok: hız kazanmak kelime kaybettiriyor.
    """
    try:
        oran = float(speed) or 1.0
    except (TypeError, ValueError):
        oran = 1.0
    oran = min(1.5, max(0.6, oran))
    return f"{round((oran - 1.0) * 100):+d}%"


def edge_hazir() -> str:
    """Boş dize: Edge konuşabilir. Değilse neden konuşamadığı.

    Yetenek sağlayıcı KURULURKEN denetleniyor, ilk cümlede değil — kamera ve
    Piper katmanlarında aynı hata iki kez yapıldı: kurulu olmayan bir şeyin
    ``available`` demesi panele çalışmayan bir düğme koyuyor ve hata
    konuşmanın ortasında çıkıyor.

    Ağın o an ayakta olduğu burada denetlenemez (denetlemek her açılışa bir
    istek eklerdi); ağ hatası sentezde açık bir mesajla çıkıyor.
    """
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        return ("Edge sesi için kütüphane kurulu değil.\n"
                "    pip install edge-tts")
    return ""


class EdgeTTS:
    """Microsoft Edge'in nöral seslerinden konuşma."""

    name = "edge"
    mime = "audio/mpeg"

    def __init__(self, voice: str = VARSAYILAN_SES, speed: float = 1.0,
                 ca_bundle: str = "") -> None:
        # Kırpma ÖNCE: yalnızca boşluktan ibaret bir ayar ("JARVIS_EDGE_VOICE= ")
        # aksi halde boş bir ses adı olarak geçip servise gidiyordu.
        self.voice = (voice or "").strip() or VARSAYILAN_SES
        self.rate = _yuzde(speed)
        # Kurumsal ağlarda TLS'i kendi sertifikasıyla açan bir vekil olabiliyor;
        # edge-tts kendi CA paketini kullandığı için bunu ayrıca söylemek
        # gerekiyor. Boşsa kütüphanenin varsayılanı geçerli.
        self.ca_bundle = ca_bundle
        self.available = True

    def _ssl_baglami(self) -> ssl.SSLContext | None:
        if not self.ca_bundle:
            return None
        try:
            return ssl.create_default_context(cafile=self.ca_bundle)
        except (OSError, ssl.SSLError):
            return None

    def synthesize(self, text: str) -> Iterator[bytes]:
        """MP3 parçalarını geldikçe ver.

        edge-tts asyncio ile çalışıyor, buranın sözleşmesi ise senkron bir
        üreteç. Arada bir iş parçacığı ve sınırlı bir kuyruk var: böylece
        oynatma ilk parçada başlıyor, son parçayı beklemiyor.
        """
        text = normalize_for_speech(text)
        if not text:
            raise TTSError("Seslendirilecek metin boş.")

        eksik = edge_hazir()
        if eksik:
            raise TTSError(eksik)

        kutu: queue.Queue = queue.Queue(maxsize=KUYRUK_SINIRI)

        def calis() -> None:
            try:
                asyncio.run(self._akit(text, kutu))
            except Exception as exc:  # noqa: BLE001 - tüketiciye taşınıyor
                kutu.put(exc)
            finally:
                kutu.put(_BITTI)

        is_parcasi = threading.Thread(target=calis, daemon=True)
        is_parcasi.start()

        alindi = False
        while True:
            try:
                parca = kutu.get(timeout=ZAMAN_ASIMI)
            except queue.Empty:
                raise TTSError(
                    f"Edge sesi {ZAMAN_ASIMI:.0f} saniyede cevap vermedi."
                ) from None
            if parca is _BITTI:
                break
            if isinstance(parca, Exception):
                raise TTSError(self._acikla(parca)) from parca
            alindi = True
            yield parca

        if not alindi:
            raise TTSError("Edge sesi ses üretmedi.")

    async def _akit(self, text: str, kutu: queue.Queue) -> None:
        import edge_tts
        import edge_tts.communicate as iletisim

        baglam = self._ssl_baglami()
        if baglam is not None:
            iletisim._SSL_CTX = baglam  # noqa: SLF001 - kütüphanede başka yol yok

        iletisimci = edge_tts.Communicate(text, self.voice, rate=self.rate)
        async for olay in iletisimci.stream():
            if olay.get("type") == "audio" and olay.get("data"):
                kutu.put(olay["data"])

    @staticmethod
    def _acikla(exc: Exception) -> str:
        """Kütüphanenin hatasını kullanıcının bir şey yapabileceği bir cümleye."""
        mesaj = str(exc).strip() or exc.__class__.__name__
        dusuk = mesaj.lower()
        if "certificate" in dusuk or "ssl" in dusuk:
            return ("Edge sesine güvenli bağlantı kurulamadı. Ağınızda TLS'i "
                    "açan bir vekil varsa JARVIS_EDGE_CA ile sertifika "
                    f"paketini gösterin. ({mesaj})")
        if "nodename" in dusuk or "getaddrinfo" in dusuk or "connect" in dusuk:
            return ("Edge sesine ulaşılamadı — internet bağlantısı yok gibi "
                    "görünüyor. Çevrimdışı ses için: "
                    f"JARVIS_TTS_PROVIDER=piper ({mesaj})")
        if "403" in mesaj or "401" in mesaj:
            return ("Microsoft konuşma servisi isteği reddetti. Genellikle "
                    "edge-tts sürümü eskidiğinde olur:\n"
                    f"    pip install -U edge-tts ({mesaj})")
        return f"Edge sesi başarısız: {mesaj}"


async def _sesleri_getir() -> list[dict[str, str]]:
    import edge_tts
    return await edge_tts.list_voices()


def sesler(dil: str = "tr") -> list[tuple[str, str]]:
    """(ad, cinsiyet) çiftleri — bir sesi seçebilmek için."""
    if edge_hazir():
        return []
    try:
        hepsi = asyncio.run(_sesleri_getir())
    except Exception:  # noqa: BLE001 - liste bir kolaylık, hata değil
        return [(ad, "") for ad in TURKCE_SESLER]
    return [(v.get("ShortName", ""), v.get("Gender", ""))
            for v in hepsi if v.get("Locale", "").startswith(dil)]
