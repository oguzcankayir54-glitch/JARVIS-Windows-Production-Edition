"""File tools — read, write and list, with secrets held out of reach.

Reading is normally harmless, with one important exception: an assistant that
will happily read ``~/.ssh/id_rsa`` and paste it into an answer is an
exfiltration path, and the request to do so can arrive from a document rather
than from the user. So secret-looking paths are refused outright, for reads as
well as writes.

Writing is MEDIUM in the user's own space and HIGH under system directories,
where a bad write can break the machine.
"""
from __future__ import annotations

import fnmatch
from pathlib import Path
from typing import Any

from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry

#: Never readable or writable through a tool, whoever asks.
_SECRET_PATTERNS = (
    "*.pem", "*.key", "*id_rsa*", "*id_ed25519*", "*id_ecdsa*", "*.p12", "*.pfx",
    ".env", "*.env", "*credentials*", "*secrets*", "shadow", "gshadow", "*.kdbx",
    "*token*", "*.keystore",
)

#: Writing here can break the system, so it needs explicit approval.
_SYSTEM_PREFIXES = ("/etc", "/usr", "/bin", "/sbin", "/boot", "/lib", "/lib64",
                    "/sys", "/proc", "/dev", "/var/lib", "/opt")

_MAX_READ_BYTES = 200_000


def _resolve(path: str) -> Path:
    return Path(path).expanduser().resolve()


def is_secret_path(p: Path) -> bool:
    """Whether this path may hold a secret and must stay out of reach.

    Public because the knowledge-base indexer needs exactly the same answer:
    a key that must not be *read* into an answer must not be *embedded* into a
    search index either, and two blocklists would drift apart.
    """
    name = p.name.lower()
    full = str(p).lower()
    if any(fnmatch.fnmatch(name, pat) for pat in _SECRET_PATTERNS):
        return True
    # .ssh/ and .gnupg/ contents are sensitive regardless of file name.
    return "/.ssh/" in full or "/.gnupg/" in full or "/.aws/" in full


#: Eski ad; modül içinde kullanılıyor.
_is_secret = is_secret_path


def _is_system_path(p: Path) -> bool:
    return str(p).startswith(_SYSTEM_PREFIXES)


def _guard(p: Path) -> None:
    if _is_secret(p):
        raise PermissionError(
            f"'{p.name}' gizli bilgi içerebilecek bir dosya; güvenlik gereği erişilmiyor."
        )


def read_file(path: str) -> dict[str, Any]:
    p = _resolve(path)
    _guard(p)
    if not p.exists():
        raise FileNotFoundError(f"Dosya yok: {p}")
    if p.is_dir():
        raise IsADirectoryError(f"'{p}' bir dizin. 'list_directory' kullanın.")
    size = p.stat().st_size
    if size > _MAX_READ_BYTES:
        raise ValueError(f"Dosya çok büyük ({size} bayt, sınır {_MAX_READ_BYTES}).")
    return {"path": str(p), "boyut": size, "icerik": p.read_text(encoding="utf-8", errors="replace")}


def write_file(path: str, content: str, append: bool = False) -> dict[str, Any]:
    p = _resolve(path)
    _guard(p)
    if p.is_dir():
        raise IsADirectoryError(f"'{p}' bir dizin.")
    p.parent.mkdir(parents=True, exist_ok=True)
    existed = p.exists()
    with p.open("a" if append else "w", encoding="utf-8") as fh:
        fh.write(content)
    return {"yazildi": True, "path": str(p), "mod": "ekle" if append else "üzerine yaz",
            "onceden_vardi": existed, "bayt": len(content.encode("utf-8"))}


def list_directory(path: str = ".") -> dict[str, Any]:
    p = _resolve(path)
    if not p.exists():
        raise FileNotFoundError(f"Dizin yok: {p}")
    if not p.is_dir():
        raise NotADirectoryError(f"'{p}' bir dizin değil.")
    entries = []
    for child in sorted(p.iterdir())[:200]:
        try:
            entries.append({
                "ad": child.name,
                "tur": "dizin" if child.is_dir() else "dosya",
                "boyut": child.stat().st_size if child.is_file() else None,
            })
        except OSError:
            continue
    return {"path": str(p), "adet": len(entries), "icerik": entries}


def _precheck_path(args: dict[str, Any]) -> str | None:
    """Secret files are off limits outright — approval cannot unlock them."""
    raw = str(args.get("path", ""))
    if not raw:
        return None
    try:
        target = _resolve(raw)
    except (OSError, ValueError):
        return None
    if _is_secret(target):
        return f"'{target.name}' gizli bilgi içerebilir; bu dosyaya erişilmiyor."
    return None


def _risk_for_write(args: dict[str, Any]) -> RiskLevel:
    """Writing under a system directory is a HIGH-risk change."""
    try:
        target = _resolve(str(args.get("path", "")))
    except (OSError, ValueError):
        return RiskLevel.HIGH
    return RiskLevel.HIGH if _is_system_path(target) else RiskLevel.MEDIUM


def register_file_tools(registry: ToolRegistry) -> ToolRegistry:
    registry.register(Tool(
        name="read_file", description="Bir metin dosyasının içeriğini oku.",
        risk=RiskLevel.LOW, func=read_file, precheck=_precheck_path,
        params=[Param("path", "string", "Dosya yolu", required=True)]))

    registry.register(Tool(
        name="list_directory", description="Bir dizindeki dosya ve klasörleri listele.",
        risk=RiskLevel.LOW, func=list_directory,
        params=[Param("path", "string", "Dizin yolu (varsayılan: bulunulan dizin)")]))

    registry.register(Tool(
        name="write_file", description="Bir dosyaya yaz (üzerine yaz veya sonuna ekle).",
        risk=RiskLevel.MEDIUM, func=write_file, risk_for=_risk_for_write,
        precheck=_precheck_path,
        params=[
            Param("path", "string", "Dosya yolu", required=True),
            Param("content", "string", "Yazılacak içerik", required=True),
            Param("append", "boolean", "True ise dosyanın sonuna ekler"),
        ]))
    return registry
