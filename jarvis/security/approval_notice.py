"""Best-effort local sound when an operation waits for user approval."""
from __future__ import annotations

import os
import platform
import subprocess
import sys


def play_approval_sound() -> None:
    """Play a local alert without turning notification failure into tool failure."""
    try:
        if platform.system() == "Windows":
            import winsound
            winsound.MessageBeep(winsound.MB_ICONEXCLAMATION)
            return
        if "microsoft" in platform.release().lower() and os.name != "nt":
            subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command",
                 "[System.Media.SystemSounds]::Exclamation.Play()"],
                check=False, timeout=2, stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            return
        sys.stderr.write("\a")
        sys.stderr.flush()
    except Exception:
        # Approval itself remains usable even if the audio device is missing.
        return
