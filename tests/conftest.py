"""Testleri kullanıcının gerçek JARVIS verisinden kesin olarak ayır."""
from __future__ import annotations

import atexit
import os
import shutil
import tempfile


_TEST_DATA = tempfile.mkdtemp(prefix="jarvis-pytest-")
os.environ["JARVIS_DATA_DIR"] = _TEST_DATA
atexit.register(shutil.rmtree, _TEST_DATA, ignore_errors=True)
