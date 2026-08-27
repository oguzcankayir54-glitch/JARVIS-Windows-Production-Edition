"""Verified local backups for J.A.R.V.I.S. user data."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path, PurePosixPath

from ..config import load_config

MANIFEST = "manifest.json"
FORMAT_VERSION = 1


class BackupError(RuntimeError):
    pass


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            value.update(chunk)
    return value.hexdigest()


def _safe_name(name: str) -> str:
    pure = PurePosixPath(name)
    if pure.is_absolute() or ".." in pure.parts or not pure.parts:
        raise BackupError(f"Güvensiz arşiv yolu: {name}")
    return pure.as_posix()


def _sqlite_snapshot(source: Path, target: Path) -> None:
    source_db = sqlite3.connect(f"file:{source.as_posix()}?mode=ro", uri=True)
    target_db = sqlite3.connect(target)
    try:
        source_db.backup(target_db)
    finally:
        target_db.close()
        source_db.close()


def create_backup(data_dir: Path, output: Path) -> Path:
    data_dir, output = Path(data_dir).resolve(), Path(output).resolve()
    if not data_dir.is_dir():
        raise BackupError(f"Veri klasörü bulunamadı: {data_dir}")
    output.parent.mkdir(parents=True, exist_ok=True)
    files = [p for p in data_dir.rglob("*") if p.is_file() and p.resolve() != output]
    with tempfile.TemporaryDirectory(prefix="jarvis-backup-") as raw:
        staging = Path(raw)
        entries = []
        for source in sorted(files):
            relative = source.relative_to(data_dir).as_posix()
            _safe_name(relative)
            snapshot = staging / relative
            snapshot.parent.mkdir(parents=True, exist_ok=True)
            if source.suffix == ".sqlite3":
                _sqlite_snapshot(source, snapshot)
            else:
                shutil.copy2(source, snapshot)
            entries.append({"path": relative, "size": snapshot.stat().st_size,
                            "sha256": _digest(snapshot)})
        manifest = {"format": FORMAT_VERSION, "created_at": int(time.time()),
                    "files": entries}
        temporary = output.with_suffix(output.suffix + ".tmp")
        try:
            with zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as archive:
                archive.writestr(MANIFEST, json.dumps(manifest, ensure_ascii=False,
                                                      indent=2, sort_keys=True))
                for entry in entries:
                    archive.write(staging / entry["path"], entry["path"])
            temporary.replace(output)
        finally:
            temporary.unlink(missing_ok=True)
    return output


def verify_backup(archive_path: Path) -> dict:
    try:
        with zipfile.ZipFile(archive_path) as archive:
            names = set(archive.namelist())
            if MANIFEST not in names:
                raise BackupError("Yedek manifest.json içermiyor.")
            manifest = json.loads(archive.read(MANIFEST))
            if manifest.get("format") != FORMAT_VERSION:
                raise BackupError("Yedek biçimi desteklenmiyor.")
            expected = {entry["path"]: entry for entry in manifest.get("files", [])}
            if len(expected) != len(manifest.get("files", [])):
                raise BackupError("Yedekte yinelenen dosya adı var.")
            for name, entry in expected.items():
                _safe_name(name)
                if name not in names:
                    raise BackupError(f"Yedekte dosya eksik: {name}")
                body = archive.read(name)
                if len(body) != entry["size"] or hashlib.sha256(body).hexdigest() != entry["sha256"]:
                    raise BackupError(f"Yedek doğrulaması başarısız: {name}")
            extras = names - set(expected) - {MANIFEST}
            if extras:
                raise BackupError(f"Manifest dışı dosya var: {sorted(extras)[0]}")
            return manifest
    except (OSError, zipfile.BadZipFile, json.JSONDecodeError, KeyError, TypeError) as exc:
        if isinstance(exc, BackupError):
            raise
        raise BackupError(f"Yedek okunamadı: {exc}") from exc


def restore_backup(archive_path: Path, data_dir: Path) -> int:
    manifest = verify_backup(archive_path)
    data_dir = Path(data_dir).resolve()
    data_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="jarvis-restore-", dir=data_dir.parent) as raw:
        staging = Path(raw)
        with zipfile.ZipFile(archive_path) as archive:
            for entry in manifest["files"]:
                name = _safe_name(entry["path"])
                target = staging / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(name) as source, target.open("wb") as destination:
                    shutil.copyfileobj(source, destination)
        for entry in manifest["files"]:
            name = entry["path"]
            source, target = staging / name, data_dir / name
            target.parent.mkdir(parents=True, exist_ok=True)
            source.replace(target)
    return len(manifest["files"])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="jarvis-yedek")
    commands = parser.add_subparsers(dest="command", required=True)
    create = commands.add_parser("olustur", help="doğrulanmış ZIP yedeği oluştur")
    create.add_argument("output", type=Path)
    verify = commands.add_parser("dogrula", help="yedek bütünlüğünü doğrula")
    verify.add_argument("archive", type=Path)
    restore = commands.add_parser("geri-yukle", help="doğrulanmış yedeği geri yükle")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--evet", action="store_true", help="veri dosyalarının üzerine yaz")
    args = parser.parse_args(argv)
    data_dir = load_config().data_dir
    try:
        if args.command == "olustur":
            result = create_backup(data_dir, args.output)
            print(f"Yedek hazır: {result}")
        elif args.command == "dogrula":
            manifest = verify_backup(args.archive)
            print(f"Yedek sağlam: {len(manifest['files'])} dosya")
        else:
            if not args.evet:
                parser.error("geri yükleme için --evet gerekli; önce J.A.R.V.I.S.'i kapatın")
            count = restore_backup(args.archive, data_dir)
            print(f"Geri yükleme tamam: {count} dosya")
        return 0
    except BackupError as exc:
        parser.error(str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
