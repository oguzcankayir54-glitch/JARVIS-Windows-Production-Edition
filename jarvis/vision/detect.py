"""Camera understanding, run locally — the first layer: is anyone there?

Stage one of vision. This finds faces in a frame; it does not yet say *whose*
face, and it deliberately does not keep the frame.

Two decisions frame everything that follows.

**Frames are not stored.** A camera in a workshop sees customers, couriers and
whoever walks past the bench, none of whom agreed to anything. A frame is
decoded, measured, and dropped; only the measurement (how many faces, where,
how big) travels onward. When recognition arrives it will store one face —
the owner's, by an explicit act — and nothing else.

**Nothing leaves the machine**, for the same reason the microphone does not:
a camera feed is the most identifying signal in the system.

OpenCV is an optional dependency. Without it J.A.R.V.I.S. runs exactly as
before and the camera tab says what to install, the same way the microphone
does.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

#: Kare boyutu üst sınırı. Panel ağa açılabildiği için karşı tarafın
#: gönderdiği veriyi sınırsız belleğe almak kabul edilebilir değil.
MAX_FRAME_BYTES = 8 * 1024 * 1024

#: OpenCV 5, kaskad sınıflandırıcıyı ve birlikte gelen yüz modellerini ana
#: tekerlekten çıkardı: `cv2.CascadeClassifier` yok, `cv2/data/` boş. 4.x
#: serisi ikisini de getiriyor ve indirme gerektirmiyor — sürüm bu yüzden
#: sabitli, "kurulu ama çalışmıyor" durumundan kurtulmak için.
_KURULUM_NOTU = (
    "Kamera için OpenCV 4 gerekli:\n"
    '    pip install "opencv-python-headless<5"'
)

_SURUM_NOTU = (
    "OpenCV {surum} yüz kaskadını içermiyor (5.x ile kaldırıldı).\n"
    '    pip install "opencv-python-headless<5"'
)


class VisionError(RuntimeError):
    """Raised with a human-readable Turkish message the panel can show as-is."""


@dataclass
class Face:
    """One detected face, in fractions of the frame rather than pixels.

    Fractions travel: the panel draws the box over a preview whose size it
    chose, and pixel coordinates from a different resolution would land in the
    wrong place.
    """
    x: float
    y: float
    w: float
    h: float

    @property
    def area(self) -> float:
        return self.w * self.h

    def as_dict(self) -> dict[str, float]:
        return {"x": round(self.x, 4), "y": round(self.y, 4),
                "w": round(self.w, 4), "h": round(self.h, 4)}


class VisionProvider(Protocol):
    name: str
    available: bool

    def detect(self, frame: bytes) -> list[Face]:
        ...


class NullVision:
    """Used when OpenCV is absent: the camera tab stays off and says why."""

    name = "yok"
    available = False

    def __init__(self, reason: str = "") -> None:
        self.reason = reason or _KURULUM_NOTU

    def detect(self, frame: bytes) -> list[Face]:
        raise VisionError(self.reason)


class HaarVision:
    """Face detection with OpenCV's bundled cascade.

    A cascade rather than a neural detector on purpose: it ships inside the
    OpenCV 4 wheel, needs no download, runs on the CPU in a few milliseconds
    and leaves the GPU entirely to the language model. It is less accurate at
    odd angles — which is the right trade for "is someone sitting at the
    bench", and can be revisited when recognition needs tighter crops.

    OpenCV 5 dropped both the class and the bundled models, so the wheel is
    pinned below 5 and :func:`build_vision` refuses rather than pretending.
    """

    name = "opencv-haar"

    #: Kareye göre bundan küçük yüzler gürültü sayılır; eski bir web
    #: kamerasında arka plandaki desenler kolayca yanlış pozitif üretir.
    EN_KUCUK_ORAN = 0.06

    def __init__(self) -> None:
        self.available = True
        self._cascade = None
        self._lock = threading.Lock()

    def _load(self):
        if self._cascade is not None:
            return self._cascade
        try:
            import cv2
        except ImportError as exc:
            raise VisionError(_KURULUM_NOTU) from exc

        if not _kaskad_var(cv2):
            raise VisionError(_SURUM_NOTU.format(surum=cv2.__version__))

        yol = cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
        cascade = cv2.CascadeClassifier(yol)
        if cascade.empty():
            raise VisionError(f"Yüz modeli yüklenemedi: {yol}")
        self._cascade = cascade
        return cascade

    def detect(self, frame: bytes) -> list[Face]:
        if not frame:
            raise VisionError("Kare boş.")
        if len(frame) > MAX_FRAME_BYTES:
            raise VisionError(
                f"Kare çok büyük ({len(frame) // (1024 * 1024)} MB); "
                f"sınır {MAX_FRAME_BYTES // (1024 * 1024)} MB."
            )

        try:
            import cv2
            import numpy as np
        except ModuleNotFoundError as exc:
            raise VisionError(
                "Kamera analizi hazır değil: opencv-python-headless kurulu değil. "
                "Kurmak için: pip install -e '.[kamera]'"
            ) from exc

        with self._lock:
            cascade = self._load()
            dizi = np.frombuffer(frame, dtype=np.uint8)
            görüntü = cv2.imdecode(dizi, cv2.IMREAD_COLOR)
            if görüntü is None:
                raise VisionError("Kare çözümlenemedi (bozuk veya desteklenmeyen biçim).")

            yükseklik, genişlik = görüntü.shape[:2]
            gri = cv2.cvtColor(görüntü, cv2.COLOR_BGR2GRAY)
            # Histogram eşitleme: eski web kameralarının zayıf pozlaması
            # kontrastı düşürüyor ve kaskad kontrasta duyarlı.
            gri = cv2.equalizeHist(gri)

            asgari = int(min(genişlik, yükseklik) * self.EN_KUCUK_ORAN)
            kutular = cascade.detectMultiScale(
                gri, scaleFactor=1.1, minNeighbors=5,
                minSize=(max(asgari, 24), max(asgari, 24)),
            )

        return [
            Face(x=x / genişlik, y=y / yükseklik, w=w / genişlik, h=h / yükseklik)
            for (x, y, w, h) in kutular
        ]


def _kaskad_var(cv2) -> bool:
    """Whether this OpenCV build can actually run a Haar cascade.

    Both halves are needed and OpenCV 5 removed both, so an import that
    succeeds proves nothing.
    """
    if not hasattr(cv2, "CascadeClassifier"):
        return False
    klasor = getattr(getattr(cv2, "data", None), "haarcascades", "")
    return bool(klasor) and Path(klasor, "haarcascade_frontalface_default.xml").is_file()


def build_vision(enabled: bool = True) -> VisionProvider:
    """Return a working provider, or :class:`NullVision` explaining why not.

    The capability is checked here rather than at the first frame: the panel
    asks once at start-up whether it has a camera, and a button that appears
    and then fails is worse than one that never appears.
    """
    if not enabled:
        return NullVision("Kamera kapalı (JARVIS_VISION_ENABLED=false).")
    try:
        import cv2
    except ImportError:
        return NullVision()
    if not _kaskad_var(cv2):
        return NullVision(_SURUM_NOTU.format(surum=cv2.__version__))
    return HaarVision()
