"""Blind model comparison.

The property that matters most here is that the sheet stays blind: if a model
name leaks into it, the comparison stops measuring answer quality and starts
measuring expectation. Several tests exist only to guard that.
"""
import random

import pytest

from jarvis.eval.compare import (
    Answer,
    Round,
    load_questions,
    render_blind,
    render_key,
    run_comparison,
)


def _ask_echo(model: str, question: str) -> str:
    return f"{model} diyor ki: {question}"


# ---------------- running ----------------

def test_every_model_answers_every_question():
    turlar = run_comparison(["kucuk", "buyuk"], ["soru bir", "soru iki"], _ask_echo)
    assert len(turlar) == 2
    for tur in turlar:
        assert {c.model for c in tur.answers} == {"kucuk", "buyuk"}


def test_a_failing_model_does_not_lose_the_other_answers():
    """A partial comparison is still worth reading."""
    def ask(model, question):
        if model == "yok":
            raise RuntimeError("model inmemiş")
        return "cevap"

    turlar = run_comparison(["var", "yok"], ["soru"], ask)
    cevaplar = {c.model: c for c in turlar[0].answers}
    assert cevaplar["var"].ok and cevaplar["var"].text == "cevap"
    assert not cevaplar["yok"].ok and "inmemiş" in cevaplar["yok"].error


def test_timing_is_recorded_per_answer():
    turlar = run_comparison(["a", "b"], ["soru"], _ask_echo)
    assert all(c.seconds >= 0 for c in turlar[0].answers)


def test_progress_is_reported_for_each_call():
    görülen = []
    run_comparison(["a", "b"], ["s1", "s2"], _ask_echo,
                   on_progress=lambda i, n, m: görülen.append((i, n, m)))
    assert görülen == [(1, 2, "a"), (1, 2, "b"), (2, 2, "a"), (2, 2, "b")]


# ---------------- blindness ----------------

def test_presentation_order_is_shuffled_per_question():
    """A fixed order would let the reader learn which letter is which."""
    turlar = run_comparison(["a", "b"], [f"soru {i}" for i in range(40)],
                            _ask_echo, rng=random.Random(7))
    siralar = {tuple(t.order) for t in turlar}
    assert siralar == {(0, 1), (1, 0)}, "her iki sıra da görülmeli"


def test_blind_sheet_never_names_a_model():
    turlar = run_comparison(["qwen2.5:14b", "qwen2.5:32b"], ["soru"],
                            lambda m, q: "sade cevap")
    sayfa = render_blind(turlar)
    assert "14b" not in sayfa and "32b" not in sayfa and "qwen" not in sayfa.lower()


def test_blind_sheet_does_not_leak_timing():
    """Timing would identify the offloaded model instantly."""
    turlar = run_comparison(["a", "b"], ["soru"], _ask_echo)
    assert "sn" not in render_blind(turlar).replace("Sizin", "")


def test_blind_sheet_shows_every_answer():
    turlar = run_comparison(["a", "b"], ["soru"],
                            lambda m, q: f"{m.upper()}-METNI")
    sayfa = render_blind(turlar)
    assert "Cevap A" in sayfa and "Cevap B" in sayfa
    assert "A-METNI" in sayfa and "B-METNI" in sayfa


def test_failed_answer_is_shown_as_missing_not_blank():
    def ask(model, question):
        if model == "yok":
            raise RuntimeError("bağlanılamadı")
        return "cevap"

    sayfa = render_blind(run_comparison(["var", "yok"], ["soru"], ask))
    assert "cevap alınamadı" in sayfa
    assert "yok" not in sayfa.replace("cevap alınamadı", "")


# ---------------- answer key ----------------

def test_key_maps_letters_back_to_models():
    turlar = run_comparison(["kucuk", "buyuk"], ["soru"], _ask_echo)
    anahtar = render_key(turlar)
    for harf, cevap in turlar[0].presented():
        assert f"**{harf}** = `{cevap.model}`" in anahtar


def test_key_reports_average_time_per_model():
    turlar = run_comparison(["a", "b"], ["s1", "s2"], _ask_echo)
    anahtar = render_key(turlar)
    assert "ortalama" in anahtar
    assert anahtar.count("ortalama") == 2


def test_key_warns_against_reading_speed_as_quality():
    """The whole comparison fails if slowness is read as being worse."""
    anahtar = render_key(run_comparison(["a", "b"], ["soru"], _ask_echo))
    assert "Kaliteyi bununla karıştırmayın" in anahtar


def test_key_handles_a_model_that_answered_nothing():
    def ask(model, question):
        if model == "yok":
            raise RuntimeError("hata")
        return "cevap"

    anahtar = render_key(run_comparison(["var", "yok"], ["soru"], ask))
    assert "hata" in anahtar          # süre tablosunda işaretli
    assert "var" in anahtar


# ---------------- question loading ----------------

def test_comments_and_blank_lines_are_skipped():
    metin = "# başlık\n\nilk soru\n   \n# ara yorum\nikinci soru\n"
    assert load_questions(metin) == ["ilk soru", "ikinci soru"]


def test_questions_are_trimmed():
    assert load_questions("   boşluklu soru   \n") == ["boşluklu soru"]


def test_empty_file_yields_no_questions():
    assert load_questions("# yalnızca yorum\n\n") == []


def test_shipped_question_file_is_usable():
    """The default set must load and be substantial enough to discriminate."""
    from jarvis.eval.cli import VARSAYILAN_SORULAR
    sorular = load_questions(VARSAYILAN_SORULAR.read_text(encoding="utf-8"))
    assert len(sorular) >= 10
    assert all(s.endswith("?") or len(s) > 40 for s in sorular)


# ---------------- presentation helper ----------------

def test_presented_follows_the_shuffled_order():
    tur = Round(question="s",
                answers=[Answer("ilk", "1", 0.0), Answer("ikinci", "2", 0.0)],
                order=[1, 0])
    assert [(h, c.model) for h, c in tur.presented()] == [("A", "ikinci"), ("B", "ilk")]


def test_three_models_get_three_letters():
    turlar = run_comparison(["a", "b", "c"], ["soru"], _ask_echo)
    assert [h for h, _ in turlar[0].presented()] == ["A", "B", "C"]


# ---------------- tool calling ----------------
#
# Prose quality is only half of choosing a model here. J.A.R.V.I.S. reads
# telemetry, runs commands and keeps the service log through tool calls, so a
# model with lovely Turkish that cannot emit one is a downgrade, not an
# upgrade — it would talk well and do nothing.

from jarvis.eval.compare import TOOL_PROBLARI, run_tool_check, render_tool_report

_ARACLAR = ["get_cpu_temperature", "get_ram_usage", "acik_vakalar", "vaka_ac"]


def _sabit_asker(esleme):
    """esleme: model -> her probe için dönecek araç adı listesi."""
    sayac = {}
    def ask(model, question):
        i = sayac.get(model, 0)
        sayac[model] = i + 1
        adlar = esleme[model]
        return (adlar[i] if i < len(adlar) else []), ""
    return ask


def test_a_model_that_always_calls_scores_full():
    ask = _sabit_asker({"iyi": [[a] for a in _ARACLAR]})
    rapor, = run_tool_check(["iyi"], ask, gecerli_adlar=_ARACLAR)
    assert rapor.cagirdi == rapor.denenen == len(TOOL_PROBLARI)
    assert rapor.oran == 1.0


def test_a_model_that_never_calls_scores_zero():
    """This is the case that would silently break every tool-backed feature."""
    ask = _sabit_asker({"konuskan": [[], [], [], []]})
    rapor, = run_tool_check(["konuskan"], ask, gecerli_adlar=_ARACLAR)
    assert rapor.cagirdi == 0 and rapor.oran == 0.0


def test_an_invented_tool_name_does_not_count_as_success():
    """Worse than silence: the agent dispatches it, fails, and burns a step."""
    ask = _sabit_asker({"uyduran": [["sicaklik_oku"], ["get_ram_usage"], [], []]})
    rapor, = run_tool_check(["uyduran"], ask, gecerli_adlar=_ARACLAR)
    assert rapor.cagirdi == 1
    assert "sicaklik_oku" in rapor.tanimsiz


def test_a_failing_model_stops_and_records_why():
    def ask(model, question):
        raise RuntimeError("model inmemiş")
    rapor, = run_tool_check(["yok"], ask, gecerli_adlar=_ARACLAR)
    assert "inmemiş" in rapor.hata and rapor.cagirdi == 0


def test_every_model_is_reported():
    ask = _sabit_asker({"a": [[x] for x in _ARACLAR], "b": [[], [], [], []]})
    raporlar = run_tool_check(["a", "b"], ask, gecerli_adlar=_ARACLAR)
    assert [r.model for r in raporlar] == ["a", "b"]


def test_report_names_the_unusable_model_plainly():
    ask = _sabit_asker({"iyi": [[x] for x in _ARACLAR], "kotu": [[], [], [], []]})
    metin = render_tool_report(run_tool_check(["iyi", "kotu"], ask, gecerli_adlar=_ARACLAR))
    assert "kullanılamaz" in metin and "güvenilir" in metin
    assert "gerileme" in metin, "neden önemli olduğu yazılmalı"


def test_report_is_not_blinded():
    """Unlike the prose sheet, this is measurement — hiding names helps nobody."""
    ask = _sabit_asker({"qwen2.5:14b": [[x] for x in _ARACLAR]})
    assert "qwen2.5:14b" in render_tool_report(
        run_tool_check(["qwen2.5:14b"], ask, gecerli_adlar=_ARACLAR))


def test_probes_need_a_tool_to_answer():
    """A probe answerable from memory would measure nothing."""
    assert len(TOOL_PROBLARI) >= 3
    assert any("vaka" in p.lower() for p in TOOL_PROBLARI)
    assert any("sıcaklık" in p.lower() or "ram" in p.lower() for p in TOOL_PROBLARI)
