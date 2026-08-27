#!/usr/bin/env python3
"""Windows'a taşınabilir, sırsız JARVIS ZIP paketi üret ve doğrula."""
from __future__ import annotations

import argparse
import hashlib
import json
import zipfile
from pathlib import Path, PurePosixPath


ROOT = Path(__file__).resolve().parent.parent
SKIP_PARTS = {
    ".git", ".venv", ".pytest_cache", ".jarvis", ".jarvis-lite-data",
    "__pycache__", "node_modules",
}
SKIP_SUFFIXES = {".pyc", ".pyo", ".sqlite", ".sqlite3", ".log"}
SKIP_NAMES = {".env", ".env.lite", "kimlik.json"}
MANIFEST = "WINDOWS-TRANSFER-MANIFEST.json"


def files(exclude: Path | None = None) -> list[Path]:
    result = []
    for path in ROOT.rglob("*"):
        rel = path.relative_to(ROOT)
        if (not path.is_file() or path.resolve() == exclude
                or any(part in SKIP_PARTS for part in rel.parts)):
            continue
        if (path.name in SKIP_NAMES or path.name.startswith(":memory:")
                or path.suffix.lower() in SKIP_SUFFIXES):
            continue
        result.append(path)
    return sorted(result, key=lambda p: p.relative_to(ROOT).as_posix())


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build(output: Path) -> None:
    entries: dict[str, str] = {}
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files(output.resolve()):
            rel = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            entries[rel] = digest(data)
            info = zipfile.ZipInfo(rel, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o755 if path.stat().st_mode & 0o111 else 0o644) << 16
            zf.writestr(info, data)
        body = json.dumps({"format": 1, "sha256": entries}, ensure_ascii=False,
                          indent=2, sort_keys=True).encode("utf-8") + b"\n"
        zf.writestr(MANIFEST, body)
    print(f"Paket hazır: {output} ({len(entries)} dosya)")


def verify(package: Path) -> None:
    with zipfile.ZipFile(package) as zf:
        names = zf.namelist()
        if MANIFEST not in names:
            raise SystemExit("Manifest yok; paket doğrulanamadı.")
        manifest = json.loads(zf.read(MANIFEST))["sha256"]
        forbidden = [n for n in names if PurePosixPath(n).name in SKIP_NAMES]
        if forbidden:
            raise SystemExit(f"Pakette yasaklı ayar dosyası var: {forbidden}")
        for name, expected in manifest.items():
            actual = digest(zf.read(name))
            if actual != expected:
                raise SystemExit(f"SHA-256 uyuşmuyor: {name}")
    print(f"Paket doğrulandı: {package} ({len(manifest)} dosya, sır/veri yok)")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="oluşturulacak ZIP")
    parser.add_argument("--verify", type=Path, help="var olan ZIP'i doğrula")
    args = parser.parse_args()
    if bool(args.output) == bool(args.verify):
        parser.error("--output veya --verify seçeneklerinden tam birini verin")
    if args.output:
        build(args.output.resolve())
        verify(args.output.resolve())
    else:
        verify(args.verify.resolve())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
