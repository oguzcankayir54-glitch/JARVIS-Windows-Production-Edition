"""Read-only Git repository tools for the GITHUB intent.

Repository inspection must not fall back to arbitrary shell execution.  These
tools call ``git`` directly with argv (no shell), are LOW risk, and redact
credential-shaped text before it can reach the model.
"""
from __future__ import annotations

from pathlib import Path
import re
import subprocess
from typing import Any

from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry


_SECRET = (
    re.compile(r"\bsk-[A-Za-z0-9_-]{12,}\b"),
    re.compile(r"(?i)(token|password|api[_-]?key)=([^\s&]+)"),
    re.compile(r"(https?://)([^/@\s:]+):([^/@\s]+)@"),
)


def _redact(text: str) -> str:
    out = _SECRET[0].sub("[SECRET]", text or "")
    out = _SECRET[1].sub(lambda m: f"{m.group(1)}=[SECRET]", out)
    out = _SECRET[2].sub(r"\1[REDACTED]@", out)
    return out


def _repo(path: str) -> Path:
    p = Path(path or ".").expanduser().resolve()
    if not p.exists() or not p.is_dir():
        raise FileNotFoundError(f"Repo dizini bulunamadı: {p}")
    probe = subprocess.run(
        ["git", "-C", str(p), "rev-parse", "--show-toplevel"],
        capture_output=True, text=True, timeout=5, check=False,
    )
    if probe.returncode != 0:
        raise ValueError(f"Git deposu değil: {p}")
    return Path(probe.stdout.strip()).resolve()


def _git(path: str, args: list[str], timeout: float = 8.0) -> str:
    root = _repo(path)
    proc = subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True,
        timeout=timeout, check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(_redact((proc.stderr or proc.stdout).strip()) or "git işlemi başarısız")
    return _redact(proc.stdout.strip())


def git_status(path: str = ".") -> dict[str, Any]:
    root = _repo(path)
    branch = _git(str(root), ["branch", "--show-current"])
    porcelain = _git(str(root), ["status", "--short", "--branch"])
    return {"repo": str(root), "branch": branch or "(detached)", "status": porcelain or "temiz"}


def git_log(path: str = ".", limit: int = 10) -> dict[str, Any]:
    limit = max(1, min(int(limit), 50))
    root = _repo(path)
    raw = _git(str(root), ["log", f"-{limit}", "--date=iso-strict",
                           "--pretty=format:%h%x09%ad%x09%an%x09%s"])
    commits = []
    for line in raw.splitlines():
        parts = line.split("\t", 3)
        if len(parts) == 4:
            commits.append({"hash": parts[0], "date": parts[1],
                            "author": parts[2], "subject": parts[3]})
    return {"repo": str(root), "commits": commits}


def git_diff(path: str = ".", ref: str = "") -> dict[str, Any]:
    root = _repo(path)
    args = ["diff", "--no-ext-diff", "--unified=3"]
    if ref.strip():
        # Treat ref as one argv token; shell syntax is never evaluated.
        args.append(ref.strip())
    raw = _git(str(root), args)
    max_chars = 30000
    if len(raw) > max_chars:
        raw = raw[:max_chars] + f"\n… ({len(raw) - max_chars} karakter kısaltıldı)"
    return {"repo": str(root), "diff": raw or "değişiklik yok"}


def git_remote(path: str = ".") -> dict[str, Any]:
    root = _repo(path)
    raw = _git(str(root), ["remote", "-v"])
    return {"repo": str(root), "remotes": raw or "remote yok"}


def register_git_tools(registry: ToolRegistry) -> ToolRegistry:
    registry.register(Tool(
        name="git_status", description="Yerel Git reposunun branch ve çalışma ağacı durumunu oku.",
        risk=RiskLevel.LOW, func=git_status,
        params=[Param("path", "string", "Repo klasörü; varsayılan mevcut klasör")]))
    registry.register(Tool(
        name="git_log", description="Yerel Git reposunun son commitlerini oku.",
        risk=RiskLevel.LOW, func=git_log,
        params=[Param("path", "string", "Repo klasörü"),
                Param("limit", "integer", "Commit sayısı; 1-50")]))
    registry.register(Tool(
        name="git_diff", description="Yerel Git reposundaki diff'i salt okunur olarak incele.",
        risk=RiskLevel.LOW, func=git_diff,
        params=[Param("path", "string", "Repo klasörü"),
                Param("ref", "string", "İsteğe bağlı Git ref")]))
    registry.register(Tool(
        name="git_remote", description="Yerel Git reposunun remote adreslerini oku; kimlik bilgileri maskelenir.",
        risk=RiskLevel.LOW, func=git_remote,
        params=[Param("path", "string", "Repo klasörü")]))
    return registry
