#!/usr/bin/env python3
"""Aktarım sonrası Windows/WSL için kısa, donanımsız kabul testi."""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent


def run(label: str, command: list[str], env: dict[str, str]) -> None:
    print(f"[TEST] {label}")
    result = subprocess.run(command, cwd=ROOT, env=env, text=True)
    if result.returncode:
        raise SystemExit(f"[FAIL] {label} (kod {result.returncode})")
    print(f"[PASS] {label}")


def main() -> int:
    base_env = os.environ.copy()
    with tempfile.TemporaryDirectory(prefix="jarvis-windows-acceptance-") as data:
        env = base_env.copy()
        env.update({
            "JARVIS_DATA_DIR": data,
            "JARVIS_LLM_PROVIDER": "mock",
            "JARVIS_VOICE_ENABLED": "false",
            "JARVIS_STT_ENABLED": "false",
            "JARVIS_VISION_ENABLED": "false",
            "JARVIS_WEB_ENABLED": "false",
            "JARVIS_NON_INTERACTIVE": "true",
        })
        run("Python kaynakları derleniyor", [sys.executable, "-m", "compileall", "-q", "jarvis"], env)
        run("Config ve Agent oluşturuluyor", [sys.executable, "-c",
            "from jarvis.config import load_config; from jarvis.bootstrap import build_agent; "
            "c=load_config(); a=build_agent(c); assert c.llm_provider=='mock'; print('agent:', len(a.registry.all()), 'araç')"], env)
        run("Windows dosya biçimleri", [sys.executable, "windows/src/windows_bicimi.py", "--denetle"], env)
        try:
            import pytest  # noqa: F401
        except ImportError:
            print("[SKIP] pytest kurulu değil; pip install -e '.[dev]' ile etkinleştirin")
        else:
            # Yapılandırma testleri ürün varsayılanlarını sınar; smoke testine
            # özel kapatma bayraklarını onlara sızdırma.
            test_env = base_env.copy()
            test_env["JARVIS_DATA_DIR"] = data
            # Panel rotaları da ürünün parçası: yerel HTTP soketi açabilen gerçek
            # Windows kabul ortamında bunları atlamak bozuk bir kurucuyu geçirirdi.
            run("Tam regresyon testleri", [sys.executable, "-m", "pytest", "-q"],
                test_env)
    print("ÇEKİRDEK KABUL TAMAM")
    print("Gerçek sistem raporu için: jarvis-kabul")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
