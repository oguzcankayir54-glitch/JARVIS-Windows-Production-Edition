"""Blind side-by-side comparison of two or more local models.

Built to answer one question with evidence instead of opinion: is a bigger
model worth the hardware it needs? The honest way to find out is to put the
same questions to both and read the answers without knowing which is which.

Two design choices carry the whole point:

**Blind.** Answers are labelled A/B in an order reshuffled for every
question. Knowing that an answer came from the larger model is enough to make
it read as better — that bias is well documented and it is exactly what would
justify an unnecessary purchase.

**Speed is reported but kept separate.** A model too large for the card
offloads to RAM and crawls. That slowness is an artefact of today's hardware,
not of the model: the answer it produces is identical to the one it would
produce on a card that fits it. So timing is recorded for information and
deliberately left out of the blind sheet.
"""
from __future__ import annotations

import random
import time
from dataclasses import dataclass, field
from typing import Callable, Iterable, Sequence

#: Bir cevabı üreten çağrı: (model, soru) -> metin
Asker = Callable[[str, str], str]


@dataclass
class Answer:
    model: str
    text: str
    seconds: float
    error: str = ""

    @property
    def ok(self) -> bool:
        return not self.error


@dataclass
class Round:
    """One question put to every model, plus the shuffled presentation order."""
    question: str
    answers: list[Answer] = field(default_factory=list)
    #: Sunum sırası: order[i] = i'inci harfin (A, B, …) hangi cevap olduğu.
    order: list[int] = field(default_factory=list)

    def presented(self) -> list[tuple[str, Answer]]:
        return [(chr(ord("A") + i), self.answers[j]) for i, j in enumerate(self.order)]


def run_comparison(
    models: Sequence[str],
    questions: Iterable[str],
    ask: Asker,
    *,
    rng: random.Random | None = None,
    on_progress: Callable[[int, int, str], None] | None = None,
) -> list[Round]:
    """Put every question to every model, timing each answer.

    ``ask`` is injected so the comparison logic can be tested without a model
    server, and so a cloud provider could be dropped in later unchanged.
    """
    rng = rng or random.Random()
    sorular = list(questions)
    rounds: list[Round] = []

    for soru_no, question in enumerate(sorular, 1):
        tur = Round(question=question)
        for model in models:
            if on_progress:
                on_progress(soru_no, len(sorular), model)
            basla = time.monotonic()
            try:
                text = ask(model, question)
                tur.answers.append(Answer(model, text.strip(), time.monotonic() - basla))
            except Exception as exc:
                # One model failing must not throw away the answers already
                # collected — a partial comparison is still worth reading.
                tur.answers.append(
                    Answer(model, "", time.monotonic() - basla, f"{type(exc).__name__}: {exc}")
                )
        tur.order = list(range(len(tur.answers)))
        rng.shuffle(tur.order)
        rounds.append(tur)

    return rounds


@dataclass
class ToolReport:
    """How reliably one model asked for the tools it needed."""
    model: str
    denenen: int = 0
    cagirdi: int = 0            # geçerli bir araç adı üretti
    tanimsiz: list[str] = field(default_factory=list)   # olmayan araç uydurdu
    hata: str = ""

    @property
    def oran(self) -> float:
        return self.cagirdi / self.denenen if self.denenen else 0.0


#: Aracı çağırmadan cevaplanamayacak istekler. Modelin bilgisini değil,
#: "bunu ben bilemem, araca sormalıyım" diyebilmesini ölçüyor.
TOOL_PROBLARI = (
    "Bu makinenin CPU sıcaklığı şu an kaç derece?",
    "Bu makinede ne kadar RAM var ve ne kadarı dolu?",
    "Serviste kaç açık vaka var, listele.",
    "Kerem Aslan'ın masaüstü bilgisayarı geldi, açılıyor ama görüntü yok. Vaka kaydı aç.",
)


def run_tool_check(
    models: Sequence[str],
    ask_tools: Callable[[str, str], tuple[list[str], str]],
    probes: Sequence[str] = TOOL_PROBLARI,
    gecerli_adlar: Sequence[str] = (),
    on_progress: Callable[[str, int, int], None] | None = None,
) -> list[ToolReport]:
    """Check whether each model actually asks for tools when it needs them.

    Prose quality is only half of choosing a model here. J.A.R.V.I.S. reads
    telemetry, runs commands and keeps the service log through tool calls, so
    a model with lovely Turkish that cannot emit a tool call is a downgrade,
    not an upgrade — it would talk well and do nothing.

    ``ask_tools`` returns the tool names a model asked for, so this stays
    testable without a model server.
    """
    gecerli = set(gecerli_adlar)
    raporlar: list[ToolReport] = []

    for model in models:
        rapor = ToolReport(model=model)
        for i, probe in enumerate(probes, 1):
            if on_progress:
                on_progress(model, i, len(probes))
            rapor.denenen += 1
            try:
                adlar, _ = ask_tools(model, probe)
            except Exception as exc:
                rapor.hata = f"{type(exc).__name__}: {exc}"
                break
            if not adlar:
                continue
            # A name the registry does not have is worse than silence: the
            # agent would dispatch it, fail, and burn a step.
            uydurma = [a for a in adlar if gecerli and a not in gecerli]
            if uydurma:
                rapor.tanimsiz.extend(uydurma)
            else:
                rapor.cagirdi += 1
        raporlar.append(rapor)
    return raporlar


def render_tool_report(raporlar: Sequence[ToolReport]) -> str:
    """A plain verdict — this is measurement, not a judgement call, so it is
    not blinded the way the prose sheet is."""
    out = ["# Araç çağırma testi", "",
           "J.A.R.V.I.S. telemetriyi, terminali ve servis defterini araç çağırarak",
           "kullanır. Araç çağıramayan bir model, Türkçesi ne kadar güzel olursa",
           "olsun bu iş için **gerileme** demektir: güzel konuşur, hiçbir şey yapamaz.",
           "", "---", "",
           "| Model | Çağırdı | Oran | Uydurma araç | Not |",
           "|---|---|---|---|---|"]
    for r in raporlar:
        uyd = ", ".join(sorted(set(r.tanimsiz))[:3]) if r.tanimsiz else "—"
        not_ = r.hata or ("✓ güvenilir" if r.oran >= 0.75
                          else "! değişken" if r.oran >= 0.4 else "✗ kullanılamaz")
        out.append(f"| `{r.model}` | {r.cagirdi}/{r.denenen} | %{r.oran * 100:.0f} | {uyd} | {not_} |")

    out += ["", "**Nasıl okunmalı:** %75'in altı, günlük kullanımda 'sistem durumu ne'",
            "sorusuna uydurma cevap gelmesi demektir. Uydurma araç adı sessizlikten",
            "de kötüdür — ajan onu çağırmayı dener, başarısız olur ve bir adım yakar.", ""]
    return "\n".join(out)


def load_questions(text: str) -> list[str]:
    """One question per line; blank lines and ``#`` comments ignored."""
    sorular = []
    for satir in text.splitlines():
        satir = satir.strip()
        if satir and not satir.startswith("#"):
            sorular.append(satir)
    return sorular


def render_blind(rounds: Sequence[Round]) -> str:
    """The sheet to read: answers only, no model names anywhere."""
    out = [
        "# Kör karşılaştırma",
        "",
        "Her soru için cevapları okuyun ve **hangisinin daha iyi olduğuna karar verin.**",
        "Hangi modelin hangi harf olduğu her soruda değişiyor; cevap anahtarı ayrı dosyada.",
        "",
        "Karar verirken sorun: *doğru mu, eksik bırakıyor mu, uydurma var mı,",
        "sıralama mantıklı mı?* Uzunluk kalite değildir.",
        "",
        "---",
        "",
    ]
    for i, tur in enumerate(rounds, 1):
        out.append(f"## Soru {i}")
        out.append("")
        out.append(f"> {tur.question}")
        out.append("")
        for harf, cevap in tur.presented():
            out.append(f"### Cevap {harf}")
            out.append("")
            out.append(cevap.text if cevap.ok else f"*(cevap alınamadı: {cevap.error})*")
            out.append("")
        out.append("**Sizin tercihiniz:** ______   ")
        out.append("**Neden:** ______________________________________________")
        out.append("")
        out.append("---")
        out.append("")
    return "\n".join(out)


def render_key(rounds: Sequence[Round]) -> str:
    """The answer key, plus the timing that the blind sheet leaves out."""
    out = [
        "# Cevap anahtarı",
        "",
        "**Kör sayfayı doldurmadan buraya bakmayın** — hangi modelin hangi harf",
        "olduğunu bilmek, cevabı okuma biçiminizi değiştirir.",
        "",
        "---",
        "",
        "## Hangi harf hangi model",
        "",
    ]
    for i, tur in enumerate(rounds, 1):
        esler = ", ".join(f"**{harf}** = `{c.model}`" for harf, c in tur.presented())
        out.append(f"- Soru {i}: {esler}")

    out += ["", "---", "", "## Süreler", "",
            "Yavaşlık bugünkü kartın yetmemesinden; kart yeterli olsaydı",
            "**aynı cevap** çok daha hızlı gelirdi. Kaliteyi bununla karıştırmayın.",
            ""]

    modeller = _models_in_order(rounds)
    out.append("| Soru | " + " | ".join(f"`{m}`" for m in modeller) + " |")
    out.append("|---" * (len(modeller) + 1) + "|")
    for i, tur in enumerate(rounds, 1):
        hucreler = []
        for m in modeller:
            cevap = next((c for c in tur.answers if c.model == m), None)
            hucreler.append("—" if cevap is None else
                            (f"{cevap.seconds:.1f} sn" if cevap.ok else "hata"))
        out.append(f"| {i} | " + " | ".join(hucreler) + " |")

    out.append("")
    for m in modeller:
        sureler = [c.seconds for tur in rounds for c in tur.answers if c.model == m and c.ok]
        if sureler:
            out.append(f"- `{m}` ortalama: **{sum(sureler) / len(sureler):.1f} sn**")
    return "\n".join(out)


def _models_in_order(rounds: Sequence[Round]) -> list[str]:
    """Model names as first seen — the order the caller asked for."""
    görülen: list[str] = []
    for tur in rounds:
        for cevap in tur.answers:
            if cevap.model not in görülen:
                görülen.append(cevap.model)
    return görülen
