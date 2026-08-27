#!/usr/bin/env bash
# JARVIS.exe'yi derler. Linux/WSL üzerinde mingw-w64 ile çapraz derleme.
#
#   sudo apt install mingw-w64
#   ./yap.sh
#
# Simge önce üretilmeli (python ikon_yap.py); .rc dosyası onu gömüyor.
set -euo pipefail

BURASI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CIKTI="$BURASI/../JARVIS.exe"
GCC="${GCC:-x86_64-w64-mingw32-gcc}"
WINDRES="${WINDRES:-x86_64-w64-mingw32-windres}"

command -v "$GCC" >/dev/null || { echo "! $GCC yok: sudo apt install mingw-w64"; exit 1; }
[ -f "$BURASI/../jarvis.ico" ] || { echo "! jarvis.ico yok: python ikon_yap.py"; exit 1; }

echo "Kaynaklar derleniyor..."
"$WINDRES" -I "$BURASI" "$BURASI/jarvis.rc" -O coff -o "$BURASI/jarvis.res"

echo "Bağlanıyor..."
"$GCC" -O2 -s -mconsole \
    -o "$CIKTI" \
    "$BURASI/jarvis-launcher.c" "$BURASI/jarvis.res" \
    -lws2_32 -lshell32

rm -f "$BURASI/jarvis.res"
echo "✓ $CIKTI  ($(stat -c%s "$CIKTI") bayt)"
