"""Camera layer: what it measures, what it refuses, and what it keeps.

These tests run without a camera, and most of them without OpenCV: the
guarantees that matter most (nothing oversized is read into memory,
coordinates are resolution-independent, an unusable install explains itself)
hold before any image library is touched. The few that decode a real frame
skip themselves when the installed OpenCV cannot run a cascade.
"""
import pytest

from jarvis.vision.detect import (
    MAX_FRAME_BYTES,
    Face,
    HaarVision,
    NullVision,
    VisionError,
    build_vision,
)


def _kaskad_ister():
    """Skip unless this OpenCV can actually run a cascade (4.x, not 5.x)."""
    cv2 = pytest.importorskip("cv2")
    from jarvis.vision.detect import _kaskad_var
    if not _kaskad_var(cv2):
        pytest.skip(f"OpenCV {cv2.__version__} yüz kaskadını içermiyor")
    return cv2


# ---------------- coordinates ----------------

def test_face_is_expressed_in_fractions_not_pixels():
    """The panel draws over a preview it sized itself; pixels would not fit."""
    yuz = Face(x=0.25, y=0.5, w=0.5, h=0.25)
    assert yuz.as_dict() == {"x": 0.25, "y": 0.5, "w": 0.5, "h": 0.25}
    assert all(0.0 <= v <= 1.0 for v in yuz.as_dict().values())


def test_face_area_is_the_fraction_of_the_frame_covered():
    assert Face(x=0.0, y=0.0, w=0.5, h=0.5).area == pytest.approx(0.25)


def test_as_dict_rounds_so_the_wire_stays_small():
    yuz = Face(x=1 / 3, y=1 / 3, w=1 / 3, h=1 / 3)
    assert yuz.as_dict()["x"] == 0.3333


# ---------------- refusals ----------------

def test_empty_frame_is_refused():
    with pytest.raises(VisionError):
        HaarVision().detect(b"")


def test_oversized_frame_is_refused_before_decoding():
    """The cap exists to bound memory, so it must not decode first."""
    with pytest.raises(VisionError) as exc:
        HaarVision().detect(b"x" * (MAX_FRAME_BYTES + 1))
    assert "büyük" in str(exc.value)


def test_a_frame_at_the_limit_is_not_refused_for_size():
    """The failure at exactly the cap must be "unreadable", never "too big"."""
    with pytest.raises(VisionError) as exc:
        HaarVision().detect(b"x" * MAX_FRAME_BYTES)
    assert "büyük" not in str(exc.value)


def test_garbage_is_reported_as_undecodable_not_as_an_empty_result():
    _kaskad_ister()
    with pytest.raises(VisionError) as exc:
        HaarVision().detect(b"bu bir JPEG degil")
    assert "çözümlenemedi" in str(exc.value)


# ---------------- the null provider ----------------

def test_null_vision_is_unavailable_and_says_why():
    yok = NullVision()
    assert yok.available is False
    assert "opencv" in yok.reason.lower()
    with pytest.raises(VisionError):
        yok.detect(b"kare")


def test_disabled_build_names_the_setting_rather_than_the_missing_package():
    """"Camera off" and "OpenCV missing" need different answers from the panel."""
    saglayici = build_vision(enabled=False)
    assert saglayici.available is False
    assert "JARVIS_VISION_ENABLED" in saglayici.reason


def test_camera_is_off_unless_asked_for():
    """A workshop camera sees customers; starting itself is not acceptable."""
    from jarvis.config import Config
    assert Config().vision_enabled is False


def test_enabled_build_is_ready_when_a_usable_opencv_is_present():
    _kaskad_ister()
    saglayici = build_vision(enabled=True)
    assert saglayici.available is True
    assert saglayici.name == "opencv-haar"


# ---------------- the OpenCV 5 trap ----------------
# An import that succeeds proves nothing: OpenCV 5 removed both the cascade
# class and the bundled models, so a plain `pip install
# opencv-python-headless` now yields a build that imports and then fails on
# the first frame. That must surface at start-up, not at the first face.

class _Cv2Besi:
    """A cv2 that imports cleanly but cannot run a cascade."""
    __version__ = "5.0.0"

    class data:
        haarcascades = "/nonexistent/"


def test_opencv_5_is_not_mistaken_for_a_working_camera():
    from jarvis.vision.detect import _kaskad_var
    assert _kaskad_var(_Cv2Besi()) is False


def test_a_missing_cascade_file_is_not_mistaken_for_a_working_camera():
    """4.x with a stripped data directory fails the same way, and should."""
    class Kirpik(_Cv2Besi):
        __version__ = "4.14.0"
        CascadeClassifier = object
    from jarvis.vision.detect import _kaskad_var
    assert _kaskad_var(Kirpik()) is False


def test_the_version_message_names_the_fix(monkeypatch):
    import jarvis.vision.detect as detect
    monkeypatch.setattr(detect, "_kaskad_var", lambda cv2: False)
    saglayici = build_vision(enabled=True)
    assert saglayici.available is False
    assert "<5" in saglayici.reason


# ---------------- detection ----------------

def _duz_kare(en: int = 320, boy: int = 240, ton: int = 128) -> bytes:
    cv2 = _kaskad_ister()
    np = pytest.importorskip("numpy")
    return cv2.imencode(".jpg", np.full((boy, en, 3), ton, dtype=np.uint8))[1].tobytes()


def test_a_flat_frame_produces_no_faces():
    """False positives on an empty bench would make the tracker useless."""
    assert HaarVision().detect(_duz_kare()) == []


def test_detection_does_not_keep_the_frame():
    """Nothing about a frame may survive the call that measured it."""
    saglayici = HaarVision()
    saglayici.detect(_duz_kare())
    saklanan = [v for v in vars(saglayici).values() if isinstance(v, (bytes, bytearray))]
    assert not saklanan
