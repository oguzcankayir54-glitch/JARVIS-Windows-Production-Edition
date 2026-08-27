"""Turning text into vectors, locally.

Embeddings go through the Ollama server that already runs the language model:
no new service, no new dependency, and — the point — **no text leaves the
machine.** A project's source code is exactly the kind of thing that must not
be posted to an embedding API.

The model matters more than usual here. The default is ``bge-m3``: it is
genuinely multilingual, and an English-trained embedder scores Turkish
questions against Turkish notes badly enough to make retrieval feel broken.

Like the microphone and the camera, this degrades rather than fails. Without
an embedder the knowledge base still indexes and still searches — on keywords
alone. That is worse, and it says so, but it is not nothing.
"""
from __future__ import annotations

import json
import math
import urllib.error
import urllib.request
from typing import Protocol

#: Tek istekte kaç metin. Ollama tamamını belleğe alıyor; büyük yığın
#: indekslemeyi hızlandırıyor ama bellek tepesini de yükseltiyor.
YIGIN = 16

#: Gömülecek metnin üst sınırı (karakter). Parçalayıcı zaten bunun altında
#: tutuyor; bu, elle çağıran birine karşı son duvar.
EN_FAZLA_KARAKTER = 8000


class EmbedError(RuntimeError):
    """Raised with a Turkish message the CLI and panel can show as-is."""


class Embedder(Protocol):
    name: str
    model: str
    available: bool

    def embed(self, texts: list[str]) -> list[list[float]]:
        ...


def normalize(vec: list[float]) -> list[float]:
    """Scale to unit length so cosine similarity is a plain dot product.

    Done once at write time rather than on every comparison: the search path
    runs this against thousands of vectors per query, the indexer runs it once
    per chunk.
    """
    uzunluk = math.sqrt(sum(x * x for x in vec))
    if uzunluk == 0.0:
        return vec
    return [x / uzunluk for x in vec]


class NullEmbedder:
    """Used when embeddings are unavailable: search falls back to keywords."""

    name = "yok"
    model = ""
    available = False
    dim = 0

    def __init__(self, reason: str = "") -> None:
        self.reason = reason or (
            "Anlam araması için bir gömme modeli gerekli:\n"
            "    ollama pull bge-m3"
        )

    def embed(self, texts: list[str]) -> list[list[float]]:
        raise EmbedError(self.reason)


class OllamaEmbedder:
    """Embeddings from a local Ollama server."""

    name = "ollama"

    def __init__(self, host: str, model: str = "bge-m3", timeout: float = 120.0) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.available = True
        self.dim = 0
        # Ollama /api/embed'i sonradan ekledi; eski sunucularda yalnızca
        # /api/embeddings var ve tek metin alıyor. Hangisinin çalıştığını ilk
        # istekte öğrenip aklımızda tutuyoruz.
        self._toplu: bool | None = None

    # ---------------- HTTP ----------------

    def _cagir(self, yol: str, govde: dict) -> dict:
        veri = json.dumps(govde).encode("utf-8")
        istek = urllib.request.Request(
            f"{self.host}{yol}", data=veri,
            headers={"Content-Type": "application/json"},
        )
        try:
            with urllib.request.urlopen(istek, timeout=self.timeout) as cevap:
                return json.loads(cevap.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            govde_metni = ""
            try:
                govde_metni = exc.read().decode("utf-8", errors="replace")[:300]
            except Exception:
                pass
            if exc.code == 404 and "model" in govde_metni.lower():
                raise EmbedError(
                    f"'{self.model}' modeli Ollama'da yok. Kurmak için:\n"
                    f"    ollama pull {self.model}"
                ) from exc
            raise EmbedError(f"Gömme başarısız (HTTP {exc.code}): {govde_metni}") from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            raise EmbedError(f"Ollama'ya ulaşılamadı ({self.host}): {exc}") from exc

    def _toplu_dene(self, texts: list[str]) -> list[list[float]] | None:
        cevap = self._cagir("/api/embed", {"model": self.model, "input": texts})
        vektorler = cevap.get("embeddings")
        if not isinstance(vektorler, list) or len(vektorler) != len(texts):
            return None
        return vektorler

    def _tek_tek(self, texts: list[str]) -> list[list[float]]:
        cikti = []
        for metin in texts:
            cevap = self._cagir("/api/embeddings", {"model": self.model, "prompt": metin})
            vektor = cevap.get("embedding")
            if not isinstance(vektor, list) or not vektor:
                raise EmbedError("Ollama boş bir gömme döndürdü.")
            cikti.append(vektor)
        return cikti

    # ---------------- API ----------------

    def embed(self, texts: list[str]) -> list[list[float]]:
        """Embed a list of texts, returning unit-length vectors in order."""
        if not texts:
            return []
        kirpilmis = [t[:EN_FAZLA_KARAKTER] for t in texts]

        cikti: list[list[float]] = []
        for i in range(0, len(kirpilmis), YIGIN):
            dilim = kirpilmis[i:i + YIGIN]
            vektorler: list[list[float]] | None = None
            if self._toplu is not False:
                try:
                    vektorler = self._toplu_dene(dilim)
                    self._toplu = vektorler is not None
                except EmbedError:
                    # Modelin yokluğu gibi gerçek hatalar tekrar denemede de
                    # aynı çıkar; yalnızca "bu uç nokta yok" durumunda eski
                    # yola düşmek istiyoruz, o yüzden bir kez deneyip karar ver.
                    if self._toplu is True:
                        raise
                    self._toplu = False
            if vektorler is None:
                vektorler = self._tek_tek(dilim)
            cikti.extend(vektorler)

        if cikti:
            self.dim = len(cikti[0])
        return [normalize(v) for v in cikti]


def build_embedder(host: str, model: str = "bge-m3", enabled: bool = True) -> Embedder:
    """Return an embedder, or :class:`NullEmbedder` explaining why not.

    Deliberately does not reach out to Ollama to check: start-up must not
    block on a server that may be down, and a knowledge base is still usable
    on keywords while the model is being pulled.
    """
    if not enabled:
        return NullEmbedder("Anlam araması kapalı (JARVIS_RAG_EMBED_ENABLED=false).")
    if not model.strip():
        return NullEmbedder("Gömme modeli belirtilmemiş (JARVIS_RAG_EMBED_MODEL).")
    return OllamaEmbedder(host, model)
