"""Bounded tools for evidence-driven repository work.

The language model may decide *what* to inspect or change, but it cannot turn
that decision into an unverified success claim.  These tools return concrete
paths, hashes and process exit codes so the agent can distinguish source
inspection, an applied edit and a passing test run.
"""
from __future__ import annotations

import fnmatch
import hashlib
import os
import shutil
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry
from .file_tools import _precheck_path, _risk_for_write, is_secret_path


_IGNORED_DIRECTORIES = frozenset({
    ".git", ".hg", ".svn", ".venv", "venv", "node_modules", "dist",
    "build", "coverage", ".coverage", ".mypy_cache", ".pytest_cache",
    ".ruff_cache", "__pycache__", "target",
})
_MANIFESTS = frozenset({
    "pyproject.toml", "setup.py", "setup.cfg", "requirements.txt",
    "package.json", "Cargo.toml", "go.mod",
})
_CODE_EXTENSIONS = frozenset({
    ".py", ".pyi", ".js", ".jsx", ".ts", ".tsx", ".java", ".kt",
    ".go", ".rs", ".c", ".h", ".cpp", ".hpp", ".cs", ".php", ".rb",
    ".swift", ".scala", ".sh", ".ps1", ".html", ".css", ".scss",
    ".json", ".toml", ".yaml", ".yml", ".md",
})
_LANGUAGE_BY_EXTENSION = {
    ".py": "Python", ".pyi": "Python", ".js": "JavaScript",
    ".jsx": "JavaScript", ".ts": "TypeScript", ".tsx": "TypeScript",
    ".java": "Java", ".kt": "Kotlin", ".go": "Go", ".rs": "Rust",
    ".c": "C", ".h": "C/C++", ".cpp": "C++", ".hpp": "C++",
    ".cs": "C#", ".php": "PHP", ".rb": "Ruby", ".swift": "Swift",
    ".scala": "Scala", ".sh": "Shell", ".ps1": "PowerShell",
}
_MAX_SEARCH_FILE_BYTES = 1_000_000
_MAX_EDIT_FILE_BYTES = 500_000
_MAX_RESULTS = 100


def _resolve_directory(path: str) -> Path:
    root = Path(path or ".").expanduser().resolve()
    if not root.exists():
        raise FileNotFoundError(f"Proje yolu bulunamadı: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Proje yolu dizin değil: {root}")
    if is_secret_path(root):
        raise PermissionError("Gizli bilgi dizini kod aracıyla açılamaz.")
    return root


def _walk_files(root: Path, *, limit: int = 5000):
    count = 0
    for current, directories, files in os.walk(root, followlinks=False):
        directories[:] = sorted(
            name for name in directories
            if name not in _IGNORED_DIRECTORIES
            and not is_secret_path(Path(current) / name)
        )
        for name in sorted(files):
            path = Path(current) / name
            if is_secret_path(path) or path.is_symlink():
                continue
            yield path
            count += 1
            if count >= limit:
                return


def inspect_project(path: str = ".") -> dict[str, Any]:
    """Return a small, measured project map instead of guessing its stack."""
    root = _resolve_directory(path)
    manifests = []
    languages: Counter[str] = Counter()
    sample_files = []
    test_files = []
    total = 0
    for file_path in _walk_files(root):
        total += 1
        relative = file_path.relative_to(root).as_posix()
        if file_path.name in _MANIFESTS:
            manifests.append(relative)
        language = _LANGUAGE_BY_EXTENSION.get(file_path.suffix.casefold())
        if language:
            languages[language] += 1
            if len(sample_files) < 80:
                sample_files.append(relative)
        folded = relative.casefold()
        if ("test" in file_path.stem.casefold() or "/tests/" in f"/{folded}"):
            if len(test_files) < 30:
                test_files.append(relative)
    summary = ", ".join(
        f"{name}: {count}" for name, count in languages.most_common(8)
    ) or "tanınan kaynak dosyası yok"
    return {
        "root": str(root),
        "file_count": total,
        "manifests": manifests[:30],
        "languages": dict(languages),
        "sample_files": sample_files,
        "test_files": test_files,
        "user_message": (
            f"Proje gerçekten incelendi: {root}. {total} dosya; {summary}."
        ),
    }


def code_search(query: str, path: str = ".", file_pattern: str = "*") -> dict[str, Any]:
    """Literal, recursive source search with line-number evidence."""
    needle = str(query or "")
    if not needle.strip() or len(needle) > 200 or "\n" in needle or "\r" in needle:
        raise ValueError("Arama metni 1-200 karakterlik tek satır olmalı.")
    pattern = str(file_pattern or "*")
    if len(pattern) > 100 or any(part in pattern for part in ("/", "\\", "..")):
        raise ValueError("Dosya deseni yalnızca dosya adına uygulanabilir.")
    root = _resolve_directory(path)
    matches = []
    scanned = 0
    folded_needle = needle.casefold()
    for file_path in _walk_files(root):
        if not fnmatch.fnmatch(file_path.name, pattern):
            continue
        if file_path.suffix.casefold() not in _CODE_EXTENSIONS:
            continue
        try:
            if file_path.stat().st_size > _MAX_SEARCH_FILE_BYTES:
                continue
            text = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        scanned += 1
        for number, line in enumerate(text.splitlines(), 1):
            if folded_needle in line.casefold():
                matches.append({
                    "path": file_path.relative_to(root).as_posix(),
                    "line": number,
                    "text": line.strip()[:500],
                })
                if len(matches) >= _MAX_RESULTS:
                    break
        if len(matches) >= _MAX_RESULTS:
            break
    preview = "; ".join(
        f"{item['path']}:{item['line']} {item['text']}"
        for item in matches[:20]
    )
    message = (
        f"'{needle}' için {len(matches)} gerçek eşleşme bulundu: {preview}"
        if matches else
        f"'{needle}' için {scanned} kaynak dosyasında eşleşme bulunamadı."
    )
    return {
        "root": str(root), "query": needle, "scanned_files": scanned,
        "match_count": len(matches), "truncated": len(matches) >= _MAX_RESULTS,
        "matches": matches, "user_message": message,
    }


def edit_file(path: str, old_text: str, new_text: str) -> dict[str, Any]:
    """Replace one exact source fragment and verify the bytes written."""
    target = Path(path or "").expanduser().resolve()
    if is_secret_path(target):
        raise PermissionError(f"'{target.name}' gizli bilgi içerebilir; düzenlenemez.")
    if not target.exists():
        raise FileNotFoundError(f"Düzenlenecek dosya yok: {target}")
    if not target.is_file():
        raise IsADirectoryError(f"Düzenleme hedefi dosya değil: {target}")
    if target.stat().st_size > _MAX_EDIT_FILE_BYTES:
        raise ValueError("Dosya güvenli parça düzenleme sınırını aşıyor.")
    before = target.read_text(encoding="utf-8", errors="strict")
    old = str(old_text)
    replacement = str(new_text)
    if not old:
        raise ValueError("old_text boş olamaz; yeni dosya için write_file kullanın.")
    occurrences = before.count(old)
    if occurrences != 1:
        raise ValueError(
            f"old_text dosyada tam bir kez bulunmalı; bulunan: {occurrences}."
        )
    if old == replacement:
        raise ValueError("Eski ve yeni metin aynı; değişiklik uygulanmadı.")
    after = before.replace(old, replacement, 1)
    target.write_text(after, encoding="utf-8")
    persisted = target.read_text(encoding="utf-8", errors="strict")
    if persisted != after:
        raise OSError("Dosya yazıldıktan sonra içerik doğrulanamadı.")
    before_hash = hashlib.sha256(before.encode("utf-8")).hexdigest()
    after_hash = hashlib.sha256(after.encode("utf-8")).hexdigest()
    return {
        "edited": True,
        "path": str(target),
        "before_sha256": before_hash,
        "after_sha256": after_hash,
        "old_lines": old.count("\n") + 1,
        "new_lines": replacement.count("\n") + 1,
        "user_message": (
            f"Kod değişikliği dosyada doğrulandı: {target} "
            f"({before_hash[:8]} → {after_hash[:8]})."
        ),
    }


def _bounded_target(root: Path, target: str) -> str:
    value = str(target or "").strip()
    if not value:
        return ""
    if value.startswith("-") or any(ch in value for ch in ("\n", "\r", "\x00")):
        raise ValueError("Geçersiz test hedefi.")
    path_part = value.split("::", 1)[0]
    resolved = (root / path_part).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError("Test hedefi proje dizininin dışına çıkamaz.") from exc
    if not resolved.exists():
        raise FileNotFoundError(f"Test hedefi bulunamadı: {resolved}")
    return value


def _test_command(root: Path, framework: str, target: str) -> tuple[str, list[str]]:
    requested = (framework or "auto").strip().casefold()
    if requested == "auto":
        if any((root / name).exists() for name in (
            "pyproject.toml", "pytest.ini", "setup.cfg", "tests",
        )):
            requested = "pytest"
        elif (root / "package.json").is_file():
            requested = "npm"
        elif (root / "Cargo.toml").is_file():
            requested = "cargo"
        elif (root / "go.mod").is_file():
            requested = "go"
        else:
            raise ValueError("Desteklenen bir test altyapısı algılanamadı.")
    if requested == "pytest":
        project_python = next((candidate for candidate in (
            root / ".venv" / "Scripts" / "python.exe",
            root / ".venv" / "bin" / "python",
        ) if candidate.is_file()), Path(sys.executable))
        command = [str(project_python), "-m", "pytest", "-q"]
        bounded = _bounded_target(root, target)
        if bounded:
            command.append(bounded)
        return requested, command
    if target.strip():
        raise ValueError("Hedefli test şu anda yalnızca pytest için destekleniyor.")
    commands = {
        "npm": ["npm", "test", "--", "--runInBand"],
        "cargo": ["cargo", "test", "--quiet"],
        "go": ["go", "test", "./..."],
    }
    if requested not in commands:
        raise ValueError("framework: auto, pytest, npm, cargo veya go olmalı.")
    executable = shutil.which(commands[requested][0])
    if executable is None:
        raise FileNotFoundError(f"Test çalıştırıcısı bulunamadı: {commands[requested][0]}")
    return requested, [executable, *commands[requested][1:]]


def run_project_tests(path: str = ".", framework: str = "auto",
                      target: str = "", timeout: float = 180.0) -> dict[str, Any]:
    """Run one structured project test command and preserve its exit code."""
    root = _resolve_directory(path)
    kind, command = _test_command(root, framework, target)
    duration = max(5.0, min(float(timeout or 180.0), 600.0))
    try:
        completed = subprocess.run(
            command, cwd=root, capture_output=True, text=True, errors="replace",
            timeout=duration, check=False, shell=False,
        )
    except subprocess.TimeoutExpired as exc:
        return {
            "passed": False, "framework": kind, "exit_code": None,
            "timed_out": True,
            "stdout": str(exc.stdout or "")[-6000:],
            "stderr": str(exc.stderr or "")[-3000:],
        }
    stdout = (completed.stdout or "")[-12000:]
    stderr = (completed.stderr or "")[-4000:]
    passed = completed.returncode == 0
    return {
        "passed": passed,
        "framework": kind,
        "exit_code": completed.returncode,
        "timed_out": False,
        "command": command,
        "stdout": stdout,
        "stderr": stderr,
        "user_message": (
            f"{kind} testleri gerçekten geçti (çıkış kodu 0)."
            if passed else
            f"{kind} testleri başarısız oldu (çıkış kodu {completed.returncode})."
        ),
    }


def _tests_passed(data: Any) -> bool:
    return isinstance(data, dict) and data.get("passed") is True


def register_code_tools(registry: ToolRegistry) -> ToolRegistry:
    registry.register(Tool(
        "inspect_project", "Projenin dil, manifest, kaynak ve test haritasını gerçekten çıkar.",
        RiskLevel.LOW, inspect_project,
        params=[Param("path", "string", "Proje kök dizini")],
    ))
    registry.register(Tool(
        "code_search", "Kaynak dosyalarda sabit metni satır numaralarıyla ara.",
        RiskLevel.LOW, code_search,
        params=[
            Param("query", "string", "Aranacak sabit metin", required=True),
            Param("path", "string", "Proje kök dizini"),
            Param("file_pattern", "string", "Dosya adı deseni; ör. *.py"),
        ],
    ))
    registry.register(Tool(
        "edit_file", "Var olan dosyada tam bir eşleşmeyi güvenle değiştir ve hash ile doğrula.",
        RiskLevel.MEDIUM, edit_file, risk_for=_risk_for_write,
        precheck=_precheck_path,
        params=[
            Param("path", "string", "Düzenlenecek dosya", required=True),
            Param("old_text", "string", "Dosyada tam bir kez geçen eski metin", required=True),
            Param("new_text", "string", "Yerine yazılacak yeni metin", required=True),
        ],
    ))
    registry.register(Tool(
        "run_project_tests",
        "Projenin pytest/npm/cargo/go testlerini yapılandırılmış komutla gerçekten çalıştır.",
        RiskLevel.HIGH, run_project_tests, verifier=_tests_passed,
        params=[
            Param("path", "string", "Proje kök dizini"),
            Param("framework", "string", "auto | pytest | npm | cargo | go"),
            Param("target", "string", "İsteğe bağlı pytest dosyası veya node id"),
            Param("timeout", "number", "5-600 saniye"),
        ],
    ))
    return registry
