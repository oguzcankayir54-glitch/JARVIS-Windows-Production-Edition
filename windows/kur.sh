#!/usr/bin/env bash
# J.A.R.V.I.S. — Windows kurulumunu WSL içinden başlatır.
#
#   ./windows/kur.sh            → kur
#   ./windows/kur.sh -Kaldir    → kaldır
#
# Neden var: kurulum bir Windows işi (masaüstü kısayolu, %LOCALAPPDATA%),
# ama kullanıcı zaten WSL kabuğunda oturuyor. Explorer'a gidip Kur.cmd
# aramak yerine buradan çağırmak hem kısa hem de yanlış yere yazılamaz.
set -euo pipefail

BURASI="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BETIK="$BURASI/src/kur.ps1"

if ! command -v wslpath >/dev/null 2>&1; then
    echo "! Bu betik WSL içinde çalışır (wslpath bulunamadı)."
    echo "  Windows tarafındaysanız: Kur.cmd dosyasına çift tıklayın."
    exit 1
fi

if ! command -v powershell.exe >/dev/null 2>&1; then
    echo "! powershell.exe bulunamadı — WSL interop kapalı olabilir."
    echo "  /etc/wsl.conf içinde [interop] enabled=true olmalı."
    echo "  Alternatif: Windows'ta Kur.cmd dosyasına çift tıklayın."
    exit 1
fi

[ -f "$BETIK" ] || { echo "! Kurulum betiği yok: $BETIK"; exit 1; }

# wslpath, WSL yolunu Windows'un görebildiği UNC yoluna çevirir
# (\\wsl$\Ubuntu\home\...). PowerShell bu yoldan betik çalıştırabiliyor.
WINYOL="$(wslpath -w "$BETIK")"

echo "Windows kurulumu başlatılıyor..."
echo "  $WINYOL"
echo

exec powershell.exe -NoProfile -ExecutionPolicy Bypass -File "$WINYOL" "$@"
