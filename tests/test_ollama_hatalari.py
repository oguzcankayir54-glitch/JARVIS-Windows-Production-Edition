"""Ollama erişilemediğinde ne söyleniyor.

Bu dosyanın sebebi somut bir kullanıcı hatası. Windows kurulumundan sonra
ilk soruda şu geldi:

    RuntimeError: Ollama'ya ulaşılamadı (http://localhost:11434):
    <urlopen error [WinError 10061] Hedef makine etkin olarak reddettiğinden
    bağlantı kurulamadı>

Doğru ama işe yaramaz. Hatayı okuyan kişi Ollama'nın ayrı bir program
olduğunu, kurulup çalıştırılması gerektiğini ve modelin indirilmesi
gerektiğini bu cümleden çıkaramıyor.

İkinci ve daha önemli mesele: bu hata **konuşmanın ortasında** çıkıyordu.
Bu projede aynı ders üç kez alındı — kamera (OpenCV 5), Piper ve Edge —
ve her seferinde çözüm aynıydı: yeteneği AÇILIŞTA yokla.
"""
import urllib.error

import pytest

from jarvis.llm.base import Message
from jarvis.llm.ollama_provider import OllamaProvider, ollama_hazir


def _saglayici(model: str = "qwen2.5:14b-instruct") -> OllamaProvider:
    return OllamaProvider("http://localhost:11434", model, timeout=5.0)


# ---------------- bağlantı hataları ----------------

@pytest.mark.parametrize("ham", [
    # Kullanicinin ALDIGI hatanin birebir kendisi.
    "<urlopen error [WinError 10061] Hedef makine etkin olarak "
    "reddettiğinden bağlantı kurulamadı>",
    "<urlopen error [Errno 111] Connection refused>",
    "Connection refused",
])
def test_a_refused_connection_says_ollama_is_not_running(ham):
    """"Ulaşılamadı" değil: çalışmıyor, ve başlatmanın yolu şu."""
    mesaj = _saglayici()._baglanti_acikla(OSError(ham))
    assert "Ollama çalışmıyor" in mesaj
    assert "ollama serve" in mesaj
    assert "winget install Ollama.Ollama" in mesaj


def test_a_refused_connection_names_the_model_to_pull():
    mesaj = _saglayici("qwen2.5:14b-instruct")._baglanti_acikla(
        OSError("[WinError 10061] reddedildiğinden"))
    assert "ollama pull qwen2.5:14b-instruct" in mesaj


def test_a_refused_connection_offers_the_way_to_keep_working():
    """Model kurmak istemeyene de bir çıkış lazım."""
    mesaj = _saglayici()._baglanti_acikla(OSError("connection refused"))
    assert "JARVIS_LLM_PROVIDER=mock" in mesaj


def test_a_timeout_is_not_reported_as_not_running():
    """Zaman aşımı ile reddedilme farklı şeyler ve farklı çözümleri var."""
    mesaj = _saglayici()._baglanti_acikla(TimeoutError("timed out"))
    assert "cevap vermedi" in mesaj
    assert "Ollama çalışmıyor" not in mesaj
    assert "JARVIS_OLLAMA_MODEL" in mesaj, "daha küçük model önerilmeli"


def test_an_unresolvable_host_points_at_the_host_setting():
    mesaj = _saglayici()._baglanti_acikla(
        OSError("[Errno -2] Name or service not known"))
    assert "JARVIS_OLLAMA_HOST" in mesaj


def test_an_unrecognised_failure_still_carries_its_message():
    """Tanınmayan bir hata yutulmamalı."""
    assert "tuhaf bir şey" in _saglayici()._baglanti_acikla(OSError("tuhaf bir şey"))


# ---------------- sunucu cevap verdi ama reddetti ----------------

class _SahteHTTPHatasi(urllib.error.HTTPError):
    def __init__(self, kod: int, govde: bytes = b""):
        self._govde = govde
        super().__init__("http://x", kod, "hata", {}, None)

    def read(self):  # noqa: D102
        return self._govde


def test_a_missing_model_is_not_reported_as_unreachable():
    """404 = sunucu AYAKTA, model yok. "Ulaşılamadı" yanlış yöne baktırıyordu."""
    mesaj = _saglayici("qwen2.5:14b-instruct")._http_acikla(
        _SahteHTTPHatasi(404, b'{"error":"model not found"}'))
    assert "bulamadı" in mesaj
    assert "ollama pull qwen2.5:14b-instruct" in mesaj
    assert "ulaşılamadı" not in mesaj.lower()


def test_another_http_error_keeps_its_code():
    mesaj = _saglayici()._http_acikla(_SahteHTTPHatasi(500, b"ic hata"))
    assert "500" in mesaj


def test_an_unreadable_body_does_not_hide_the_error():
    """Gövde okunamazsa da bir mesaj çıkmalı."""
    class _Okunamaz(_SahteHTTPHatasi):
        def read(self):
            raise OSError("gövde okunamadı")

    assert "500" in _saglayici()._http_acikla(_Okunamaz(500))


# ---------------- açılış yoklaması ----------------
# Asıl düzeltme bu: hata konuşmanın ortasında değil, açılışta çıkmalı.

def test_an_unreachable_ollama_is_reported_at_startup(monkeypatch):
    """Reddedilen bağlantı her işletim sisteminde aynı çözümü göstermeli."""
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(
                            urllib.error.URLError("connection refused")))
    eksik = ollama_hazir("http://127.0.0.1:1", "qwen2.5:14b-instruct", timeout=1.0)
    assert eksik
    assert "ollama serve" in eksik


def test_the_check_names_a_missing_model(monkeypatch):
    import jarvis.llm.ollama_provider as modul

    class _Cevap:
        def read(self):
            return b'{"models":[{"name":"llama3:8b"}]}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(modul._req if hasattr(modul, "_req") else __import__("urllib.request", fromlist=["x"]),
                        "urlopen", lambda *a, **k: _Cevap())
    eksik = ollama_hazir("http://localhost:11434", "qwen2.5:14b-instruct")
    assert "indirilmemiş" in eksik
    assert "llama3:8b" in eksik, "kurulu olanlar da gösterilmeli"


def test_a_present_model_reports_ready(monkeypatch):
    import urllib.request

    class _Cevap:
        def read(self):
            return b'{"models":[{"name":"qwen2.5:14b-instruct"}]}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Cevap())
    assert ollama_hazir("http://localhost:11434", "qwen2.5:14b-instruct") == ""


def test_the_latest_suffix_still_counts_as_present(monkeypatch):
    """Ollama bazen ':latest' ekliyor; bunu "yok" saymak yanlış olurdu."""
    import urllib.request

    class _Cevap:
        def read(self):
            return b'{"models":[{"name":"qwen2.5:3b-instruct:latest"}]}'
        def __enter__(self):
            return self
        def __exit__(self, *a):
            return False

    monkeypatch.setattr(urllib.request, "urlopen", lambda *a, **k: _Cevap())
    assert ollama_hazir("http://localhost:11434", "qwen2.5:3b-instruct") == ""


def test_a_slow_server_does_not_block_startup(monkeypatch):
    """Ayakta ama meşgul bir Ollama yüzünden açılışı engellemek yanlış olurdu."""
    import urllib.request

    def _yavas(*a, **k):
        raise TimeoutError("timed out")

    monkeypatch.setattr(urllib.request, "urlopen", _yavas)
    assert ollama_hazir("http://localhost:11434", "x") == ""


# ---------------- panele ulaşması ----------------

def test_the_panel_carries_the_warning():
    from jarvis.bootstrap import build_agent
    from jarvis.config import Config
    from jarvis.memory.store import MemoryStore
    from jarvis.web.server import PanelServer

    ajan = build_agent(Config(llm_provider="mock", non_interactive=True),
                       memory=MemoryStore(":memory:"))
    meta = PanelServer(ajan, port=0, llm_uyari="Ollama çalışmıyor.")._meta()
    assert meta["llm_uyari"] == "Ollama çalışmıyor."
    assert PanelServer(ajan, port=0)._meta()["llm_uyari"] == ""


def test_the_panel_shows_the_warning():
    """Sessiz bir alan, kullanıcının hatayı ilk soruda öğrenmesi demekti."""
    yol = __import__("pathlib").Path("docs/mockups/jarvis-panel.html")
    kaynak = yol.read_text(encoding="utf-8")
    assert "m.llm_uyari" in kaynak
    assert "__llmUyarisi" in kaynak


def test_the_panel_cli_checks_before_it_builds_the_server():
    """Yoklama sunucudan SONRA yapılırsa uyarı sunucuya hiç ulaşmaz.

    İlk denemede tam olarak bu oldu ve panel UnboundLocalError ile açılmadı;
    testler yakalamamıştı çünkü main() uçtan uca çalıştırılmıyor. Sıralamayı
    burada kayıt altına alıyoruz.
    """
    import inspect

    from jarvis.web import cli
    kaynak = inspect.getsource(cli.main)
    yoklama = kaynak.index("ollama_hazir(")
    kurulum = kaynak.index("PanelServer(")
    assert yoklama < kurulum, "yoklama sunucudan önce yapılmalı"
    assert "llm_uyari=_llm_eksik" in kaynak
