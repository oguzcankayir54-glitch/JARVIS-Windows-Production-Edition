"""Wire the components together into a ready-to-use :class:`Agent`.

Keeping assembly in one place means the CLI, tests, and a future server all
build J.A.R.V.I.S. the same way.
"""
from __future__ import annotations

from .config import Config, load_config
from .core.agent import Agent
from .core.observability import RequestTraceLog
from .core.state import StateMachine
from .llm.base import LLMProvider
from .llm.mock_provider import MockProvider
from .memory.cases import CaseStore
from .memory.store import MemoryStore
from .internet.arama import build_arama
from .rag.embed import build_embedder
from .rag.index import KnowledgeBase
from .security.audit import AuditLog
from .core.asistan import asistan_bul
from .core.kimlik_tohumu import kimligi_tohumla
from .security.permissions import Approver, PermissionManager
from .tools.base import ToolRegistry
from .tools.case_tools import register_case_tools
from .tools.file_tools import register_file_tools
from .tools.git_tools import register_git_tools
from .tools.manager import ToolManager
from .tools.memory_tools import register_memory_tools
from .tools.app_tools import register_app_tools
from .tools.rag_tools import register_rag_tools
from .tools.web_tools import register_web_tools
from .tools.shell_tools import register_shell_tools
from .tools.system_tools import get_gpu_temperature, get_system_info, register_system_tools
from .tools.windows_tools import register_windows_tools


def build_llm(cfg: Config) -> LLMProvider:
    if cfg.llm_provider == "ollama":
        from .llm.ollama_provider import OllamaProvider  # local import: optional path
        def provider(model: str) -> OllamaProvider:
            return OllamaProvider(
                cfg.ollama_host, model,
                temperature=cfg.temperature, top_p=cfg.top_p,
                repeat_penalty=cfg.repeat_penalty,
                num_ctx=cfg.ollama_num_ctx,
                think=cfg.ollama_think,
                num_predict=cfg.ollama_num_predict,
                keep_alive=cfg.ollama_keep_alive,
            )

        primary = provider(cfg.ollama_model)
        fallback_model = cfg.ollama_fallback_model.strip()
        if fallback_model and fallback_model != cfg.ollama_model:
            from .llm.fallback_provider import FallbackProvider
            return FallbackProvider(
                primary, provider(fallback_model),
                max_retries=cfg.ollama_max_retries,
                circuit_cooldown=cfg.ollama_circuit_cooldown,
                same_server=True,
            )
        return primary
    return MockProvider()


def describe_machine() -> str:
    """One-line summary of the host, read once at startup.

    Gives J.A.R.V.I.S. context about where it lives without spending a tool
    call on it every time the subject comes up.
    """
    try:
        info = get_system_info()
        parts = [f"CPU: {info['cpu_cores']} çekirdek / {info['cpu_threads']} iş parçacığı",
                 f"RAM: {info['ram_total_gb']} GB"]
        gpu = get_gpu_temperature()
        parts.append(f"GPU: {gpu['name']} ({gpu['vram_total_mb'] / 1024:.0f} GB VRAM)"
                     if gpu.get("available") else "GPU: yok (veya erişilemiyor)")
        return " · ".join(parts)
    except Exception:
        return ""


def build_agent(
    cfg: Config | None = None,
    approver: Approver | None = None,
    memory: MemoryStore | None = None,
    cases: CaseStore | None = None,
    knowledge: KnowledgeBase | None = None,
) -> Agent:
    cfg = cfg or load_config()

    audit = AuditLog(cfg.audit_log_path, max_bytes=cfg.log_max_bytes,
                     backup_count=cfg.log_backup_count)
    trace_log = RequestTraceLog(
        cfg.request_trace_log_path, include_user_text=cfg.trace_user_text,
        max_bytes=cfg.log_max_bytes, backup_count=cfg.log_backup_count,
    )
    permissions = PermissionManager(audit=audit, approver=approver, non_interactive=cfg.non_interactive)

    store = memory if memory is not None else MemoryStore(cfg.memory_db_path)
    # Kimlik BOŞSA dosyadan doldur. "Beni tanımıyor" üç kez geri geldi ve her
    # seferinde sebep aynıydı: kimliği yazan komut hiç çalıştırılmamıştı.
    # Bir adımın hatırlanmasını beklemek tasarım değil.
    kimligi_tohumla(store, cfg.data_dir)
    # Cases share the memory store's database file but keep their own module:
    # facts are about the owner, cases are about other people's machines.
    # Following the store's path rather than the config keeps an in-memory
    # memory store from quietly dragging a real file onto disk beside it.
    case_store = cases if cases is not None else CaseStore(store.db_path)

    # The knowledge base is the one store that is rebuildable, so it gets its
    # own file: deleting and re-indexing must never put memory at risk.
    if knowledge is not None:
        kb = knowledge
    else:
        kb = KnowledgeBase(
            ":memory:" if store.db_path == ":memory:" else cfg.knowledge_db_path,
            embedder=build_embedder(cfg.ollama_host, cfg.rag_embed_model,
                                    enabled=cfg.rag_embed_enabled),
        )

    registry = ToolRegistry()
    register_system_tools(registry)
    register_windows_tools(registry)
    register_memory_tools(registry, store)
    register_file_tools(registry)
    register_git_tools(registry)
    register_shell_tools(registry)
    register_case_tools(registry, case_store)
    register_rag_tools(registry, kb)
    register_web_tools(registry, build_arama(
        enabled=cfg.web_enabled, brave_key=cfg.brave_api_key))
    register_app_tools(registry, data_dir=str(cfg.data_dir))

    tools = ToolManager(registry, permissions)
    llm = build_llm(cfg)
    return Agent(
        llm=llm, tools=tools, registry=registry, state=StateMachine(),
        max_steps=cfg.max_agent_steps, arac_siniri=cfg.arac_siniri,
        history_max_messages=cfg.history_max_messages,
        context_max_chars=cfg.context_max_chars,
        tool_result_max_chars=cfg.tool_result_max_chars,
        asistan=asistan_bul(), memory=store, cases=case_store, knowledge=kb,
        machine=describe_machine(), trace_log=trace_log,
    )
