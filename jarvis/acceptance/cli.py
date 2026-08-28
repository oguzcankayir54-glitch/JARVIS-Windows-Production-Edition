from __future__ import annotations

import argparse
import json

from ..config import load_config
from ..vision.detect import build_vision
from ..vision.identity import build_face_recognizer
from ..vision.objects import build_object_vision
from ..vision.ocr import build_ocr
from ..voice.stt import build_stt
from ..web.cli import tts_from_config
from .engine import run_acceptance


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="J.A.R.V.I.S. Windows kabul testi")
    parser.add_argument("--json", action="store_true", help="Makinece okunabilir JSON")
    args = parser.parse_args(argv)
    cfg = load_config()
    report = run_acceptance(
        cfg, tts=tts_from_config(cfg),
        stt=build_stt(enabled=cfg.stt_enabled, model_size=cfg.stt_model,
                      device=cfg.stt_device, compute_type=cfg.stt_compute_type),
        vision=build_vision(enabled=cfg.vision_enabled),
        object_vision=build_object_vision(enabled=cfg.object_vision_enabled),
        ocr=build_ocr(enabled=cfg.ocr_enabled),
        face_recognizer=build_face_recognizer(
            enabled=cfg.face_recognition_enabled,
            path=cfg.data_dir / "face_templates.json",
        ),
    )
    if args.json:
        print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    else:
        icons = {"hazir": "PASS", "eksik": "MISS", "arizali": "FAIL"}
        for check in report.checks:
            print(f"[{icons[check.status]}] {check.name}: {check.detail}")
            if check.status != "hazir" and check.fix:
                print(f"       Çözüm: {check.fix}")
        print(f"\nSONUÇ: {report.status.upper()}")
    return 0 if report.status == "hazir" else 2
