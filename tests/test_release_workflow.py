from __future__ import annotations

import importlib.util
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def _module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(mod)
    return mod


def test_profiles_are_distinct_and_secret_free():
    profiles = ROOT / "profiles"
    values = {}
    for name in ("lite", "windows-dev", "windows-production"):
        text = (profiles / f"{name}.env.example").read_text(encoding="utf-8")
        assert f"JARVIS_PROFILE={name}" in text
        assert "sk_" not in text and "sk-" not in text
        values[name] = text
    assert values["lite"] != values["windows-production"]


def test_transfer_package_excludes_secrets_and_verifies(tmp_path):
    transfer = _module("windows_transfer", ROOT / "scripts/windows_transfer.py")
    output = tmp_path / "jarvis-windows.zip"
    transfer.build(output)
    transfer.verify(output)
    with zipfile.ZipFile(output) as zf:
        names = zf.namelist()
        assert ".env" not in names and ".env.lite" not in names
        assert "kimlik.json" not in names
        assert not any(Path(name).name.startswith(":memory:") for name in names)
        assert not any(".jarvis-lite-data" in name for name in names)
        assert transfer.MANIFEST in names
