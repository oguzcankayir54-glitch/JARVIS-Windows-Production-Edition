#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESK="$HOME/Desktop"
[[ -d "$DESK" ]] || DESK="$HOME/Masaüstü"
[[ -d "$DESK" ]] || DESK="$HOME/Desktop"
mkdir -p "$DESK"
FILE="$DESK/JARVIS-Lite.desktop"
cat > "$FILE" <<DESKTOP
[Desktop Entry]
Type=Application
Name=JARVIS Lite Panel
Comment=JARVIS Linux Development/Test Panel
Exec=bash -lc 'cd "$ROOT" && ./run-panel-lite.sh'
Terminal=true
Categories=Development;
DESKTOP
chmod +x "$FILE"
echo "Kısayol oluşturuldu: $FILE"
