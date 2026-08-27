#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT"
if [[ ! -x .venv/bin/python ]]; then
  echo "JARVIS Lite kurulmamış. Önce: ./install-lite.sh"
  exit 1
fi
if [[ ! -f .env ]]; then cp .env.lite .env; fi
source .venv/bin/activate
exec jarvis-panel --host 127.0.0.1 --port 8765 --ac --kamera
