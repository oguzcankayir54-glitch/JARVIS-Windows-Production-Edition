"""Intent-driven tool exposure for J.A.R.V.I.S. 2.0 (Phase 6).

This router never executes a tool.  It only decides which schemas the LLM may
see for the current intent.  Execution still goes through ToolManager and the
PermissionManager, preserving the security boundary.
"""
from __future__ import annotations

from dataclasses import dataclass

from .intent_router import Intent, IntentDecision
from .metin import katla


@dataclass(frozen=True)
class ToolRoute:
    intent: Intent
    tool_names: tuple[str, ...]


class ToolRouter:
    SYSTEM_TOOLS = frozenset({
        "get_system_info", "get_cpu_temperature", "get_gpu_temperature",
        "get_ram_usage", "get_disk_health",
        "windows_system", "windows_process", "windows_network", "windows_service",
    })
    CASE_TOOLS = frozenset({
        "vaka_ac", "vaka_notu_ekle", "vaka_kapat", "vaka_ara",
        "acik_vakalar", "vaka_detay",
    })

    BASE_ALLOWLIST: dict[Intent, frozenset[str]] = {
        Intent.CHAT: frozenset(),
        Intent.MEMORY_SAVE: frozenset({"remember_fact", "recall_facts"}),
        Intent.MEMORY_RECALL: frozenset({"recall_facts"}),
        Intent.MEMORY_UPDATE: frozenset({"remember_fact", "recall_facts"}),
        Intent.MEMORY_DELETE: frozenset({"forget_fact", "recall_facts"}),
        Intent.TRAINING: frozenset({"remember_fact", "recall_facts"}),
        Intent.RAG_QUERY: frozenset({"bilgi_ara", "bilgi_durum"}),
        Intent.WEB_RESEARCH: frozenset({"web_ara", "web_oku"}),
        # No generic shell fallback for GitHub. A dedicated GitHub service is
        # safer than turning every repo question into an arbitrary command.
        Intent.GITHUB: frozenset({"git_status", "git_log", "git_diff", "git_remote"}),
        Intent.TERMINAL: frozenset({"run_terminal_command"}),
        Intent.COMPUTER_CONTROL: frozenset({
            "uygulama_ac", "uygulama_listesi", "tarayici_ac", "arama_ac",
            "windows_window", "windows_audio", "windows_input",
        }),
        Intent.SYSTEM_MONITOR: SYSTEM_TOOLS,
        Intent.TASK: frozenset(),
        Intent.AUTONOMOUS: frozenset(),
        Intent.VOICE: frozenset(),
        Intent.UNKNOWN: frozenset(),
    }

    @staticmethod
    def _schema_name(schema: dict) -> str:
        return (schema.get("function") or {}).get("name", "")

    def names_for(self, decision: IntentDecision, user_text: str) -> set[str]:
        if decision.intent is Intent.CODING:
            allowed = {"read_file", "list_directory"}
            text = katla(user_text)
            if any(k in text for k in (
                "duzelt", "degistir", "yaz", "olustur", "ekle", "refactor", "uygula"
            )):
                allowed.add("write_file")
            if any(k in text for k in (
                "testleri calistir", "komutu calistir", "terminalde calistir"
            )):
                allowed.add("run_terminal_command")
            return allowed

        if decision.intent is Intent.TASK and decision.subtype == "SERVICE_CASE":
            return set(self.CASE_TOOLS)

        return set(self.BASE_ALLOWLIST.get(decision.intent, frozenset()))

    def select(self, schemas: list[dict], decision: IntentDecision,
               user_text: str, *, limit: int = 8) -> list[dict]:
        allowed = self.names_for(decision, user_text)
        selected = [s for s in schemas if self._schema_name(s) in allowed]
        if limit and limit > 0:
            selected = selected[:limit]
        return selected

    def route(self, schemas: list[dict], decision: IntentDecision,
              user_text: str, *, limit: int = 8) -> ToolRoute:
        selected = self.select(schemas, decision, user_text, limit=limit)
        return ToolRoute(decision.intent, tuple(self._schema_name(s) for s in selected))
