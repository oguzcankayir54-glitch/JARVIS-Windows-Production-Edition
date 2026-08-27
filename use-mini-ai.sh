#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"
if ! command -v ollama >/dev/null 2>&1; then
  echo "Ollama bulunamadı. Önce: ./install-lite.sh --mini-ai"
  exit 1
fi
ollama list | grep -q '^qwen3.5:2b-q4_K_M' || ollama pull qwen3.5:2b-q4_K_M
[[ -f .env ]] || cp .env.lite .env
python3 - <<'PY'
from pathlib import Path
import re
p=Path('.env'); s=p.read_text()
s=re.sub(r'(?m)^JARVIS_LLM_PROVIDER=.*$', 'JARVIS_LLM_PROVIDER=ollama', s)
s=re.sub(r'(?m)^JARVIS_OLLAMA_MODEL=.*$', 'JARVIS_OLLAMA_MODEL=qwen3.5:2b-q4_K_M', s)
p.write_text(s)
print('MINI-AI modu aktif: qwen3.5:2b-q4_K_M')
PY
