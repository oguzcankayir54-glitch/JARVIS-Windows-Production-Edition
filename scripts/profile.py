#!/usr/bin/env python3
"""JARVIS çalışma profilini güvenli biçimde seç."""
from __future__ import annotations

import argparse
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
PROFILES = ROOT / "profiles"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("profile", choices=("lite", "windows-dev", "windows-production"))
    parser.add_argument("--write", action="store_true", help="şablonu .env olarak yaz")
    parser.add_argument("--force", action="store_true", help="mevcut .env dosyasının üzerine yaz")
    args = parser.parse_args()
    source = PROFILES / f"{args.profile}.env.example"
    if not args.write:
        print(source.read_text(encoding="utf-8"), end="")
        return 0
    target = ROOT / ".env"
    if target.exists() and not args.force:
        raise SystemExit(".env zaten var; sırları korumak için dokunulmadı. Bilinçli değişim: --force")
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    print(f"Aktif profil: {args.profile} ({target})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
