"""Manual acceptance test for the real Ollama/Qwen execution path.

The ordinary test suite deliberately uses deterministic providers.  This
module exercises the production agent, router and tools with the real model,
then asks the operator to judge the meaning of each answer.  Structural
invariants (for example, never searching an empty RAG index) are checked in
code; natural-language quality is not reduced to a brittle keyword assert.
"""
from __future__ import annotations

import argparse
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path

from ..bootstrap import build_agent
from ..config import load_config


PRODUCTION_MODEL = "qwen2.5:14b-instruct"


@dataclass(frozen=True)
class ModelAcceptanceCase:
    id: str
    prompt: str
    expected: str
    forbidden_tools: frozenset[str] = frozenset()
    required_tools: frozenset[str] = frozenset()
    allowed_tools: frozenset[str] | None = None


CASES = (
    ModelAcceptanceCase(
        "owner_statement",
        "Ben senin geliştiricinim.",
        "İfadeyi kimlik bağlamında onaylamalı; komut satırı veya RAG kurulum komutu okumamalı.",
        forbidden_tools=frozenset({"run_terminal_command", "bilgi_ara", "bilgi_durum"}),
    ),
    ModelAcceptanceCase(
        "ordinary_chat",
        "Nasılsın?",
        "Kısa ve doğal bir sohbet cevabı vermeli; araç çalıştırmamalı.",
        allowed_tools=frozenset(),
    ),
    ModelAcceptanceCase(
        "rag_definition",
        "RAG ne?",
        "RAG terimini açıklamalı; boş bilgi tabanında arama yapmamalı.",
        forbidden_tools=frozenset({"bilgi_ara"}),
    ),
    ModelAcceptanceCase(
        "cpu_temperature",
        "CPU sıcaklığı kaç?",
        "get_cpu_temperature sonucunu aktarmalı; sensör yoksa bunu dürüstçe söylemeli, sayı uydurmamalı.",
        required_tools=frozenset({"get_cpu_temperature"}),
    ),
)


@dataclass(frozen=True)
class ModelAcceptanceObservation:
    case: ModelAcceptanceCase
    answer: str
    tools: tuple[str, ...]
    structural_ok: bool
    detail: str


def run_model_path_acceptance(agent) -> tuple[ModelAcceptanceObservation, ...]:
    """Run the four real-model turns and check observable routing invariants."""
    observations: list[ModelAcceptanceObservation] = []
    for case in CASES:
        answer = agent.ask(case.prompt)
        trace = agent.last_trace
        tools = tuple(trace.tools_used) if trace is not None else ()
        used = set(tools)
        forbidden = sorted(used & case.forbidden_tools)
        missing = sorted(case.required_tools - used)
        unexpected = (
            sorted(used - case.allowed_tools)
            if case.allowed_tools is not None else []
        )
        reasons: list[str] = []
        if forbidden:
            reasons.append("yasak araç çağrıldı: " + ", ".join(forbidden))
        if missing:
            reasons.append("zorunlu araç çağrılmadı: " + ", ".join(missing))
        if unexpected:
            reasons.append("gereksiz araç çağrıldı: " + ", ".join(unexpected))
        if not answer.strip():
            reasons.append("yanıt boş")
        observations.append(ModelAcceptanceObservation(
            case=case,
            answer=answer,
            tools=tools,
            structural_ok=not reasons,
            detail="; ".join(reasons) if reasons else "yönlendirme kuralları sağlandı",
        ))
    return tuple(observations)


def review_observations(
    observations: tuple[ModelAcceptanceObservation, ...],
    *,
    input_fn: Callable[[str], str] = input,
    output: Callable[[str], None] = print,
) -> bool:
    """Show expected behaviour and require an explicit human verdict."""
    accepted = True
    for index, observation in enumerate(observations, 1):
        case = observation.case
        output(f"\n[{index}/{len(observations)}] İSTEM: {case.prompt}")
        output(f"BEKLENEN: {case.expected}")
        output(f"ARAÇLAR: {', '.join(observation.tools) if observation.tools else '(yok)'}")
        output(f"YAPISAL: {'PASS' if observation.structural_ok else 'FAIL'} — {observation.detail}")
        output(f"YANIT: {observation.answer}")
        human_ok = input_fn("Beklenen davranış sağlandı mı? [e/H] ").strip().lower() in {
            "e", "evet", "y", "yes",
        }
        accepted = accepted and observation.structural_ok and human_ok
    return accepted


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis-kabul-model",
        description="Gerçek Qwen 2.5:14B yolu için etkileşimli kabul testi.",
    )
    parser.parse_args(argv)
    cfg = load_config()
    if cfg.llm_provider != "ollama" or cfg.ollama_model != PRODUCTION_MODEL:
        print(
            "FAIL: Bu test yalnızca JARVIS_LLM_PROVIDER=ollama ve "
            f"JARVIS_OLLAMA_MODEL={PRODUCTION_MODEL} ile çalışır."
        )
        return 2

    # Kabul konuşması gerçek kullanıcı belleğine veya bilgi tabanına yazılmaz.
    # Boş ve geçici indeks, RAG sızıntısı senaryosunu her çalıştırmada aynı yapar.
    with tempfile.TemporaryDirectory(prefix="jarvis-model-kabul-") as temp_dir:
        acceptance_cfg = replace(
            cfg,
            data_dir=Path(temp_dir),
            ollama_fallback_model="",
            non_interactive=True,
            rag_embed_enabled=False,
        )
        observations = run_model_path_acceptance(build_agent(acceptance_cfg))
        accepted = review_observations(observations)

    print("\nSONUÇ: " + ("PASS" if accepted else "FAIL"))
    return 0 if accepted else 1


if __name__ == "__main__":
    raise SystemExit(main())
