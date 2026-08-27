#!/usr/bin/env bash
# J.A.R.V.I.S. — otomatik kurulum betiği
#
# Kullanım:   ./kurulum.sh
#
# Yaptıkları: Python sürümünü kontrol eder, sanal ortam kurar, paketleri
# yükler, testleri çalıştırır, sistemi tarar ve sonucu raporlar.
# Sisteme hiçbir şey yüklemez (sudo kullanmaz); her şey bu klasördeki .venv
# içinde kalır.

set -uo pipefail

VENV=".venv"
OK=0
UYARI=0
HATA=0

c_ok()   { printf '  \033[32m✓\033[0m %s\n' "$1"; OK=$((OK+1)); }
c_warn() { printf '  \033[33m!\033[0m %s\n' "$1"; UYARI=$((UYARI+1)); }
c_err()  { printf '  \033[31m✗\033[0m %s\n' "$1"; HATA=$((HATA+1)); }
baslik() { printf '\n\033[36m%s\033[0m\n' "$1"; }

printf '\033[36m'
cat <<'BANNER'
=========================================================
  J.A.R.V.I.S.  ·  Kurulum
=========================================================
BANNER
printf '\033[0m'

# --- 1. Python -----------------------------------------------------------
baslik "1/5  Python kontrolü"

PY=""
for aday in python3.12 python3.11 python3.10 python3; do
    if command -v "$aday" >/dev/null 2>&1; then
        sur=$("$aday" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null) || continue
        maj=${sur%%.*}; min=${sur##*.}
        if [ "$maj" -eq 3 ] && [ "$min" -ge 10 ]; then
            PY="$aday"
            c_ok "Python $sur bulundu ($aday)"
            break
        fi
    fi
done

if [ -z "$PY" ]; then
    c_err "Python 3.10+ bulunamadı."
    echo
    echo "  Kurmak için:  sudo apt update && sudo apt install python3 python3-venv"
    exit 1
fi

if ! "$PY" -c 'import venv' >/dev/null 2>&1; then
    c_err "python3-venv modülü yok."
    echo "  Kurmak için:  sudo apt install python3-venv"
    exit 1
fi

# --- 2. Sanal ortam ------------------------------------------------------
baslik "2/5  Sanal ortam"

if [ -d "$VENV" ]; then
    c_ok "Mevcut sanal ortam kullanılıyor ($VENV)"
else
    if "$PY" -m venv "$VENV" >/dev/null 2>&1; then
        c_ok "Sanal ortam oluşturuldu ($VENV)"
    else
        c_err "Sanal ortam oluşturulamadı."
        exit 1
    fi
fi

VPY="$VENV/bin/python"
[ -x "$VPY" ] || VPY="$VENV/Scripts/python.exe"   # Windows/Git Bash

# --- 3. Paketler ---------------------------------------------------------
baslik "3/5  Paketler yükleniyor"

"$VPY" -m pip install --quiet --upgrade pip >/dev/null 2>&1

if "$VPY" -m pip install --quiet -e . >/dev/null 2>&1; then
    c_ok "J.A.R.V.I.S. ve bağımlılıkları yüklendi"
else
    c_err "Paket kurulumu başarısız. Ayrıntı için:  $VPY -m pip install -e ."
    exit 1
fi

if "$VPY" -m pip install --quiet pytest >/dev/null 2>&1; then
    c_ok "pytest yüklendi"
else
    c_warn "pytest yüklenemedi (testler atlanacak)"
fi

# --- 4. Testler ----------------------------------------------------------
baslik "4/5  Testler"

if "$VPY" -m pytest -q >/tmp/jarvis_test_out 2>&1; then
    c_ok "$(grep -oE '[0-9]+ passed' /tmp/jarvis_test_out | tail -1)"
else
    c_warn "Bazı testler geçmedi. Ayrıntı: cat /tmp/jarvis_test_out"
fi

# --- 5. Sistem taraması --------------------------------------------------
baslik "5/5  Sistem taraması"

TARAMA_SAYAC=$(mktemp)

"$VPY" - "$TARAMA_SAYAC" <<'PYEOF'
import shutil, sys

_sayac = {"ok": 0, "warn": 0}

def ok(m):
    print(f"  \033[32m✓\033[0m {m}"); _sayac["ok"] += 1

def warn(m):
    print(f"  \033[33m!\033[0m {m}"); _sayac["warn"] += 1

try:
    import psutil
    vm = psutil.virtual_memory()
    ok(f"CPU: {psutil.cpu_count(logical=False)} çekirdek / {psutil.cpu_count()} iş parçacığı")
    ok(f"RAM: {vm.total/1e9:.1f} GB")
except Exception as e:
    warn(f"psutil okunamadı: {e}")

# CPU sıcaklık sensörü
try:
    import psutil
    temps = getattr(psutil, "sensors_temperatures", lambda: {})() or {}
    hit = next((k for k in ("k10temp","coretemp","cpu_thermal","acpitz") if k in temps and temps[k]), None)
    if hit:
        ok(f"CPU sıcaklık sensörü: {temps[hit][0].current:.0f}°C ({hit})")
    else:
        warn("CPU sıcaklık sensörü yok — sanal makinede normaldir")
except Exception:
    warn("CPU sıcaklık sensörü okunamadı")

# GPU
if shutil.which("nvidia-smi"):
    import subprocess
    try:
        out = subprocess.run(["nvidia-smi","--query-gpu=name,memory.total",
                              "--format=csv,noheader"], capture_output=True, text=True, timeout=6)
        if out.returncode == 0 and out.stdout.strip():
            ok(f"GPU: {out.stdout.strip().splitlines()[0]}")
        else:
            warn("nvidia-smi çalıştı ama GPU bildirmedi")
    except Exception:
        warn("nvidia-smi çalıştırılamadı")
else:
    warn("nvidia-smi yok — GPU hızlandırma kullanılamaz (VirtualBox'ta beklenen)")

# Ollama
if shutil.which("ollama"):
    ok("Ollama kurulu — yerel model kullanılabilir")
else:
    warn("Ollama kurulu değil — şimdilik mock model ile çalışacak")

# SMART
if shutil.which("smartctl"):
    ok("smartctl kurulu — disk sağlığı okunabilir")
else:
    warn("smartctl yok (isteğe bağlı):  sudo apt install smartmontools")

# Sayaçları bash tarafına aktar, böylece özet gerçeği yansıtsın.
with open(sys.argv[1], "w") as fh:
    fh.write(f"{_sayac['ok']} {_sayac['warn']}\n")
PYEOF

if [ -s "$TARAMA_SAYAC" ]; then
    read -r t_ok t_warn < "$TARAMA_SAYAC"
    OK=$((OK + t_ok))
    UYARI=$((UYARI + t_warn))
fi
rm -f "$TARAMA_SAYAC"

# --- Duman testi ---------------------------------------------------------
baslik "Duman testi"

if printf 'sistem durumu nedir?\nçık\n' | "$VPY" -m jarvis 2>/dev/null | grep -q 'get_system_info'; then
    c_ok "J.A.R.V.I.S. yanıt verdi ve sistemi okudu"
else
    c_err "Çalıştırma testi başarısız — elle deneyin:  $VPY -m jarvis"
fi

# --- Özet ----------------------------------------------------------------
printf '\n\033[36m=========================================================\033[0m\n'
if [ "$HATA" -eq 0 ]; then
    printf '  \033[32mKURULUM TAMAM\033[0m  (%d başarılı, %d uyarı)\n' "$OK" "$UYARI"
    [ "$UYARI" -gt 0 ] && printf '  Uyarılar eksik donanım/araçla ilgilidir; J.A.R.V.I.S. yine de çalışır.\n'
else
    printf '  \033[31mKURULUM SORUNLU\033[0m  (%d hata, %d uyarı)\n' "$HATA" "$UYARI"
fi
printf '\033[36m=========================================================\033[0m\n\n'

cat <<EOF
Çalıştırmak için:

    source $VENV/bin/activate
    jarvis

Ya da tek satırda:

    $VPY -m jarvis

Mikrofonla konuşmak istersen (isteğe bağlı, panelde 🎙 düğmesi çıkar):

    $VPY -m pip install faster-whisper
    jarvis-panel

Deneyebileceklerin:
    sistem durumu nedir?
    disk sağlığı nasıl?
    hatırla: anakart = MSI B550-A PRO
    çalıştır: df -h
    çalıştır: rm -rf /          <- reddedilmeli

Uyarılar varsa ve yardım istersen, şu komutun çıktısını paylaş:

    ./kurulum.sh 2>&1 | tail -30

EOF
