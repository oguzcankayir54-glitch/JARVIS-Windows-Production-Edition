#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"
[[ -f .env ]] || cp .env.lite .env
python3 - <<'PY'
from pathlib import Path
p=Path('.env'); s=p.read_text()
import re
s=re.sub(r'(?m)^JARVIS_LLM_PROVIDER=.*$', 'JARVIS_LLM_PROVIDER=mock', s)
p.write_text(s)
print('PANEL-ONLY / MOCK modu aktif.')
PY
