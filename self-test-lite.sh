#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; cd "$ROOT"
[[ -x .venv/bin/python ]] || { echo "Önce ./install-lite.sh"; exit 1; }
source .venv/bin/activate
export JARVIS_DATA_DIR="${JARVIS_DATA_DIR:-$ROOT/.jarvis-lite-data/self-test}"
python -m compileall -q jarvis
python - <<'PY'
from jarvis.config import load_config
from jarvis.bootstrap import build_agent
c=load_config(); a=build_agent(c)
assert c.voice_enabled is False
assert c.stt_enabled is False
print('CONFIG/AGENT: PASS', c.llm_provider, c.ollama_model)
PY
PORT=8876
HEALTH="$(mktemp /tmp/jarvis-lite-health.XXXXXX.json)"
LOG="$(mktemp /tmp/jarvis-lite-selftest.XXXXXX.log)"
jarvis-panel --host 127.0.0.1 --port "$PORT" --sessiz --mikrofonsuz >"$LOG" 2>&1 &
PID=$!
trap 'kill "$PID" 2>/dev/null || true; rm -f "$HEALTH" "$LOG"' EXIT
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >"$HEALTH" 2>/dev/null; then break; fi
  if ! kill -0 "$PID" 2>/dev/null; then
    echo "PANEL HEALTH: FAIL — panel başlatılamadı" >&2
    sed -n '1,120p' "$LOG" >&2
    exit 1
  fi
  sleep 0.25
done
if [[ ! -s "$HEALTH" ]]; then
  echo "PANEL HEALTH: FAIL — 7.5 saniye içinde cevap alınamadı" >&2
  sed -n '1,120p' "$LOG" >&2
  exit 1
fi
python - "$HEALTH" <<'PY'
import json
p=__import__('sys').argv[1]
d=json.load(open(p))
assert d.get('ok') is True and d.get('state') == 'standby', d
print('PANEL HEALTH: PASS', d)
PY
echo 'JARVIS LITE SELF-TEST: PASS'
