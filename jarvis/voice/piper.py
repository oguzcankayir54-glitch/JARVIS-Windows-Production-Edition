"""Piper — speech that costs nothing and never leaves the machine.

ElevenLabs sounds excellent and bills per character, which turns every long
answer into a decision about money. Piper removes that decision: a 63 MB
neural voice runs on the CPU, faster than real time, with no quota, no key,
and no network. The same trade the microphone already makes — Whisper runs
locally for exactly this reason.

The cost is quality. Piper's Turkish voice is clearly synthetic next to
ElevenLabs. For a workshop assistant reading a diagnosis aloud that is a fair
exchange; for anything meant to sound human it is not, and ElevenLabs stays
one setting away.

Audio comes back as WAV rather than MP3. Nothing downstream cares as long as
it is told — which is why every provider now declares its own ``mime``.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Iterator

from .tts import TTSError, normalize_for_speech

#: Varsayilan Turkce ses. Piper'in tr_TR altinda su an tek ailesi bu.
VARSAYILAN_SES = "tr_TR-dfki-medium"

#: Ses modellerinin arandigi klasor.
def ses_klasoru(data_dir: Path | str = "~/.jarvis") -> Path:
    return Path(data_dir).expanduser() / "sesler"


#: Modelin indirilecegi yer. Piper seslerinin resmi deposu.
INDIRME_KOKU = "https://huggingface.co/rhasspy/piper-voices/resolve/main"

#: Ses adindan indirme yoluna: tr_TR-dfki-medium -> tr/tr_TR/dfki/medium
def indirme_yolu(ses: str) -> str:
    try:
        dil_ulke, konusmaci, kalite = ses.split("-", 2)
        dil = dil_ulke.split("_")[0]
    except ValueError as exc:
        raise TTSError(f"Ses adı çözümlenemedi: {ses}") from exc
    return f"{INDIRME_KOKU}/{dil}/{dil_ulke}/{konusmaci}/{kalite}"


#: Bir cevabin uretimi icin ust sinir. Piper gercek zamandan hizli, ama
#: bozuk bir model sonsuza kadar bekletebilir.
ZAMAN_ASIMI = 120.0

#: Tek seferde okunacak bayt. Panel butun sesi bekliyor, ama parcali okumak
#: terminalde oynatmayi konusma baslamadan baslatiyor.
PARCA = 8192


def _binary_yolu(binary: str) -> str | None:
    """Find Piper on PATH or next to the active virtualenv's Python.

    Windows launcher and direct ``.venv/bin/jarvis-*`` invocations do not
    necessarily activate the virtual environment first.  In that case the
    console script installed by ``piper-tts`` is beside ``sys.executable``
    but absent from PATH.
    """
    bulunan = shutil.which(binary)
    if bulunan:
        return bulunan

    ham = Path(binary).expanduser()
    if ham.is_absolute() or ham.parent != Path("."):
        return None

    # Do not resolve the venv Python symlink: its target is the base Python,
    # while console scripts live beside the symlink inside the venv.
    kok = Path(sys.executable).expanduser().parent
    adaylar = (kok / ham.name, kok / f"{ham.name}.exe")
    for aday in adaylar:
        if aday.is_file():
            return str(aday)
    return None


class PiperTTS:
    """Local neural speech through the ``piper`` binary."""

    name = "piper"
    mime = "audio/wav"

    def __init__(self, model: Path | str, binary: str = "piper",
                 speed: float = 1.0, cuda: bool = False) -> None:
        self.model = Path(model).expanduser()
        self.binary = binary
        # Piper'in olcusu ters: length_scale buyudukce ses YAVASLIYOR.
        # Disariya donuk ayar her yerde "hiz" oldugu icin burada cevriliyor.
        self.speed = min(2.0, max(0.5, float(speed) or 1.0))
        self.cuda = cuda
        self.available = True

    # ---------------- hazirlik ----------------

    def _denetle(self) -> None:
        # Önce model/config hatasını göster. Böylece temiz bir makinede Piper
        # binary'si de eksik olsa kullanıcı ilk önce gerçekten gereken ses
        # paketini nasıl kuracağını öğrenir; testler de deterministik kalır.
        if not self.model.is_file():
            raise TTSError(
                f"Ses modeli yok: {self.model}\n"
                "    jarvis-ses --piper-kur   ile indirebilirsiniz."
            )
        yapilandirma = Path(str(self.model) + ".json")
        if not yapilandirma.is_file():
            raise TTSError(
                f"Modelin yapılandırma dosyası eksik: {yapilandirma}\n"
                "    Modeli .onnx.json dosyasıyla birlikte indirin."
            )
        if _binary_yolu(self.binary) is None:
            raise TTSError(
                f"'{self.binary}' bulunamadı. Kurmak için:\n"
                "    pip install piper-tts"
            )

    def _komut(self, output: str = "-") -> list[str]:
        komut = [_binary_yolu(self.binary) or self.binary,
                 "-m", str(self.model), "-f", output,
                 "--length-scale", f"{1.0 / self.speed:.3f}"]
        if self.cuda:
            komut.append("--cuda")
        return komut

    # ---------------- uretim ----------------

    def synthesize(self, text: str) -> Iterator[bytes]:
        """Yield WAV bytes for ``text``."""
        text = normalize_for_speech(text)
        if not text:
            raise TTSError("Seslendirilecek metin boş.")
        self._denetle()

        # Piper 1.7'nin ``-f -`` yolu boş WAV üretebiliyor. Adlandırılmış
        # geçici dosya hem eski hem yeni CLI ile çalışır; çıktı daha sonra
        # panelin beklediği bayt akışına çevrilir.
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as gecici:
            cikti = Path(gecici.name)
        try:
            try:
                surec = subprocess.Popen(
                    self._komut(str(cikti)),
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                )
            except OSError as exc:
                raise TTSError(f"Piper başlatılamadı: {exc}") from exc

            try:
                # Metin kucuk (bir cevap), boru tamponuna sigiyor; yazip
                # kapatmak kilitlenmeye yol acmiyor.
                ses, hata = surec.communicate(text.encode("utf-8"),
                                              timeout=ZAMAN_ASIMI)
            except subprocess.TimeoutExpired as exc:
                surec.kill()
                surec.communicate()
                raise TTSError(
                    f"Piper {ZAMAN_ASIMI:.0f} saniyede bitiremedi."
                ) from exc

            # Test sağlayıcıları ve eski CLI stdout döndürebilir; yeni CLI
            # ise adlandırılmış dosyaya yazar.
            if not ses and cikti.is_file():
                ses = cikti.read_bytes()
        finally:
            cikti.unlink(missing_ok=True)

        # piper-tts 1.7.0'ın stdout WAV yolu bazı sistemlerde başarılı kodla
        # fakat sıfır baytla dönüyor. Dosya çıktısı aynı sürümde sağlam;
        # yalnızca bu özgül durumda bir kez ona düş.
        if surec.returncode == 0 and not ses:
            with tempfile.NamedTemporaryFile(suffix=".wav") as gecici:
                tekrar = subprocess.Popen(
                    self._komut(gecici.name), stdin=subprocess.PIPE,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                try:
                    _, ikinci_hata = tekrar.communicate(
                        text.encode("utf-8"), timeout=ZAMAN_ASIMI
                    )
                except subprocess.TimeoutExpired as exc:
                    tekrar.kill()
                    tekrar.communicate()
                    raise TTSError(
                        f"Piper {ZAMAN_ASIMI:.0f} saniyede bitiremedi."
                    ) from exc
                if tekrar.returncode == 0:
                    gecici.seek(0)
                    ses = gecici.read()
                if ikinci_hata:
                    hata = ikinci_hata

        if surec.returncode != 0 or not ses:
            mesaj = (hata or b"").decode("utf-8", errors="replace").strip()
            son = mesaj.splitlines()[-1] if mesaj else "sebep bildirilmedi"
            raise TTSError(f"Piper ses üretemedi: {son}")
        if not ses.startswith(b"RIFF"):
            raise TTSError("Piper beklenen WAV çıktısını vermedi.")

        for bas in range(0, len(ses), PARCA):
            yield ses[bas:bas + PARCA]


def piper_hazir(model: Path | str, binary: str = "piper") -> str:
    """Empty string when Piper can speak; otherwise why it cannot.

    Checked when the provider is built, not at the first sentence. The camera
    layer learned this the hard way: a provider that reports ``available``
    and then fails on use makes the panel offer a button that does nothing,
    and the failure surfaces mid-conversation instead of at start-up where it
    can be acted on.
    """
    if _binary_yolu(binary) is None:
        return ("Piper kurulu değil.\n"
                "    pip install piper-tts")
    yol = Path(model).expanduser()
    if not yol.is_file():
        return (f"Piper ses modeli yok: {yol}\n"
                "    jarvis-ses --piper-kur")
    if not Path(str(yol) + ".json").is_file():
        return (f"Modelin .onnx.json dosyası eksik: {yol}.json\n"
                "    jarvis-ses --piper-kur")
    return ""


def piper_modeli(ses: str = VARSAYILAN_SES,
                 data_dir: Path | str = "~/.jarvis") -> Path:
    """Where a voice by that name is expected to live.

    A bare name is looked up in the voices folder; anything that looks like a
    path is taken as given, so a voice downloaded elsewhere still works.
    """
    ham = str(ses).strip()
    if not ham:
        ham = VARSAYILAN_SES
    if "/" in ham or ham.endswith(".onnx"):
        return Path(ham).expanduser()
    return ses_klasoru(data_dir) / f"{ham}.onnx"
