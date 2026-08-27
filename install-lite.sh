#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
MINI=0
[[ "${1:-}" == "--mini-ai" ]] && MINI=1

echo "=== JARVIS Linux Dev/Test Edition kurulumu ==="

install_deps() {
  if command -v apt-get >/dev/null 2>&1; then
    sudo apt-get update
    sudo apt-get install -y python3 python3-venv python3-pip curl
  elif command -v dnf >/dev/null 2>&1; then
    sudo dnf install -y python3 python3-pip curl
  elif command -v pacman >/dev/null 2>&1; then
    sudo pacman -Sy --needed --noconfirm python python-pip curl
  else
    echo "Paket yöneticisi otomatik tanınmadı. python3 + venv + pip + curl kurulu olmalı."
  fi
}

if ! command -v python3 >/dev/null 2>&1; then install_deps; fi
if ! python3 -m venv --help >/dev/null 2>&1; then install_deps; fi

python3 - <<'PY'
import sys
if sys.version_info < (3,10):
    raise SystemExit('Python 3.10+ gerekli.')
print('Python:', sys.version.split()[0])
PY

python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip setuptools wheel
python -m pip install -e '.[dev,kamera,mikrofon,ses,ses-yerel]'
cp -f .env.lite .env
mkdir -p .jarvis-lite-data

# Lite sürümde kamera ve çevrimiçi Edge hazır gelir; varsayılan ses ise
# anahtarsız ve tamamen yerel Piper'dır. Model yalnızca yoksa indirilir.
if [[ ! -f .jarvis-lite-data/sesler/tr_TR-dfki-medium.onnx ]]; then
  jarvis-ses --piper-kur
fi

if (( MINI )); then
  if ! command -v curl >/dev/null 2>&1; then install_deps; fi
  if ! command -v ollama >/dev/null 2>&1; then
    echo "Ollama kuruluyor (resmi installer)..."
    curl -fsSL https://ollama.com/install.sh | sh
  fi
  ollama pull qwen3.5:0.8b
  ./use-mini-ai.sh
fi

echo "Derleme/smoke testleri..."
python -m compileall -q jarvis
python - <<'PY'
from jarvis.config import load_config
from jarvis.bootstrap import build_agent
c=load_config()
a=build_agent(c)
print('LLM:', c.llm_provider, c.ollama_model)
print('DATA:', c.data_dir)
print('AGENT: OK')
PY

echo
echo "KURULUM TAMAMLANDI"
echo "Panel: ./run-panel-lite.sh"
echo "Mini AI: ./use-mini-ai.sh"
echo "Mock:    ./use-mock.sh"
