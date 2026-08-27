<#
    J.A.R.V.I.S. — Windows kurulumu

    Yönetici gerektirmez: her şey kullanıcı profiline kurulur.

    Yaptıkları:
      1. JARVIS.exe ve simgeyi %LOCALAPPDATA%\Programs\JARVIS altına kopyalar
      2. WSL dağıtımını ve proje klasörünü BULUR, jarvis.ini'ye yazar
      3. Masaüstüne ve Başlat menüsüne kısayol koyar

    İkinci adım kurulumu bir kopyalayıcıdan fazlası yapan şey: kullanıcı
    dağıtım adını elle yazmak zorunda kalmasın, ve klasör yoksa bunu
    kurulumda öğrensin — ilk çift tıklamada değil.
#>
[CmdletBinding()]
param(
    [switch]$Kaldir
)

$ErrorActionPreference = "Stop"

$Kaynak  = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Hedef   = Join-Path $env:LOCALAPPDATA "Programs\JARVIS"

# Masaüstü yolu boş dönebiliyor — OneDrive'a yönlendirilmiş veya ilke ile
# taşınmış profillerde görülüyor. Boş yolla Join-Path çağırmak kurulumu işini
# bitirdikten SONRA anlaşılmaz bir hatayla düşürüyordu; yedeği var, yoksa da
# o kısayol atlanıyor.
$Masaustu = [Environment]::GetFolderPath("Desktop")
if ([string]::IsNullOrWhiteSpace($Masaustu) -and $env:USERPROFILE) {
    $Masaustu = Join-Path $env:USERPROFILE "Desktop"
}
$BaslatMenusu = ""
if ($env:APPDATA) {
    $BaslatMenusu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
}

function Yaz($metin, $renk = "Gray") { Write-Host $metin -ForegroundColor $renk }
function Baslik($metin) {
    Write-Host ""
    Write-Host ("=" * 58) -ForegroundColor DarkCyan
    Write-Host "  $metin" -ForegroundColor Cyan
    Write-Host ("=" * 58) -ForegroundColor DarkCyan
}

# ------------------------------------------------------------------ kaldır

if ($Kaldir) {
    Baslik "J.A.R.V.I.S. kaldırılıyor"
    # Boş yolla Join-Path çağırmak kaldırmayı da düşürürdü; kurulumdakiyle
    # aynı sebep, aynı koruma.
    foreach ($klasor in @($Masaustu, $BaslatMenusu)) {
        if ([string]::IsNullOrWhiteSpace($klasor)) { continue }
        $k = Join-Path $klasor "JARVIS.lnk"
        if (Test-Path $k) { Remove-Item $k -Force; Yaz "  - kısayol silindi: $k" }
    }
    if (Test-Path $Hedef) {
        # jarvis.ini kullanıcının kendi ayarı; silmeden önce söylüyoruz.
        $ini = Join-Path $Hedef "jarvis.ini"
        if (Test-Path $ini) { Yaz "  ! ayarlarınız siliniyor: $ini" "Yellow" }
        Remove-Item $Hedef -Recurse -Force
        Yaz "  - klasör silindi: $Hedef"
    }
    Yaz ""
    Yaz "  Kaldırıldı. (WSL içindeki J.A.R.V.I.S. projesine dokunulmadı.)" "Green"
    Yaz ""
    return
}

# ------------------------------------------------------------------- kur

Baslik "J.A.R.V.I.S. kuruluyor"

$exe = Join-Path $Kaynak "JARVIS.exe"
if (-not (Test-Path $exe)) {
    Yaz "  ! JARVIS.exe bulunamadı: $exe" "Red"
    Yaz "    Bu betiği windows klasöründeki Kur.cmd ile çalıştırın." "Red"
    exit 1
}

New-Item -ItemType Directory -Path $Hedef -Force | Out-Null
Copy-Item $exe $Hedef -Force
Yaz "  + $Hedef\JARVIS.exe"

$ico = Join-Path $Kaynak "jarvis.ico"
if (Test-Path $ico) { Copy-Item $ico $Hedef -Force; Yaz "  + $Hedef\jarvis.ico" }

# ---------------------------------------------------------- WSL'i bul

$dagitim = ""
$klasor  = "~/jarvis"

$wsl = Get-Command wsl.exe -ErrorAction SilentlyContinue
if (-not $wsl) {
    Yaz ""
    Yaz "  ! wsl.exe bulunamadı — WSL kurulu değil gibi görünüyor." "Yellow"
    Yaz "    Yönetici PowerShell'de: wsl --install" "Yellow"
} else {
    # wsl.exe çıktısı UTF-16LE; bu ayarlanmazsa PowerShell 5.1 harflerin
    # arasına boş karakter serpiştirilmiş gibi okur ve hiçbir şey eşleşmez.
    $oncekiKodlama = [Console]::OutputEncoding
    try {
        [Console]::OutputEncoding = [System.Text.Encoding]::Unicode
        $dagitimlar = @(& wsl.exe -l -q 2>$null |
                        ForEach-Object { $_.Trim() } |
                        Where-Object { $_ -ne "" })
    } finally {
        [Console]::OutputEncoding = $oncekiKodlama
    }

    if ($dagitimlar.Count -eq 0) {
        Yaz ""
        Yaz "  ! WSL dağıtımı bulunamadı." "Yellow"
    } else {
        $dagitim = $dagitimlar[0]
        Yaz ""
        Yaz "  WSL dağıtımı : $dagitim" "White"
        if ($dagitimlar.Count -gt 1) {
            Yaz "  (diğerleri: $($dagitimlar[1..($dagitimlar.Count-1)] -join ', '))"
            Yaz "  Başkasını istiyorsanız jarvis.ini içindeki 'dagitim' satırını değiştirin."
        }

        # Proje klasörünü gerçekten var mı diye soruyoruz — ilk çift
        # tıklamada öğrenmek yerine şimdi öğrenmek daha iyi.
        $adaylar = @("~/jarvis", "~/projeler/jarvis", "~/Projects/jarvis")
        $bulundu = $false
        foreach ($aday in $adaylar) {
            $kontrol = & wsl.exe -d $dagitim -- bash -lc "[ -d $aday ] && echo VAR" 2>$null
            if ($kontrol -match "VAR") { $klasor = $aday; $bulundu = $true; break }
        }
        if ($bulundu) {
            Yaz "  Proje klasörü: $klasor" "White"
            $panel = & wsl.exe -d $dagitim -- bash -lc `
                "cd $klasor 2>/dev/null; [ -f .venv/bin/activate ] && . .venv/bin/activate; command -v jarvis-panel >/dev/null && echo VAR" 2>$null
            if ($panel -match "VAR") {
                Yaz "  jarvis-panel : kurulu" "Green"
            } else {
                Yaz "  jarvis-panel : BULUNAMADI" "Yellow"
                Yaz "    WSL içinde: cd $klasor && source .venv/bin/activate && pip install -e ." "Yellow"
            }
        } else {
            Yaz "  ! Proje klasörü bulunamadı." "Yellow"
            Yaz "    jarvis.ini içindeki 'klasor' satırına doğru yolu yazın." "Yellow"
        }
    }
}

# ------------------------------------------------------------- jarvis.ini

$iniYolu = Join-Path $Hedef "jarvis.ini"
if (Test-Path $iniYolu) {
    Yaz ""
    Yaz "  = jarvis.ini zaten var, dokunulmadı (ayarlarınız korundu)."
} else {
    # Bilerek here-string DEGIL. Windows PowerShell 5.1 here-string
    # sonlandiricisini LF satir sonlariyla tanimiyor; bu dosya Linux'ta
    # yazildigi icin blok acik kaliyor ve icindeki '&&' isaretleri kod diye
    # ayristirilip betigi tumden bozuyordu. Satir dizisi bu tuzagi tamamen
    # ortadan kaldiriyor: satir sonu ne olursa olsun ayrisir.
    $satirlar = @(
        "; J.A.R.V.I.S. baslatici ayarlari",
        "; Bu dosya istege baglidir; silinirse varsayilanlar kullanilir.",
        "",
        "[jarvis]",
        "",
        "; Hangi WSL dagitimi. Bos birakilirsa WSL'in varsayilani kullanilir.",
        "dagitim = $dagitim",
        "",
        "; Proje klasoru (WSL icindeki yol).",
        "klasor = $klasor",
        "",
        "; Panelin portu.",
        "port = 8765",
        "",
        "; Panel hazir olunca tarayici acilsin mi? 0 = acma.",
        "tarayici = 1",
        "",
        "; Kendi penceresinde mi acilsin? 1 = evet (sekme yok, adres cubugu",
        "; yok, gorev cubugunda kendi simgesi). Edge/Chrome --app kipi.",
        "uygulama = 1",
        "",
        "; Acilis girisi (~10 saniye). 0 yaparsaniz panel dogrudan gelir.",
        "intro = 1",
        "",
        "; Erisim jetonu. Bos birakirsaniz baslatici BIR KEZ uretip bu satira",
        "; yazar; sonraki her aciliste ayni deger kullanilir. Adres SABITTIR,",
        "; yer imine eklenebilir. Degistirmek icin bu satiri bosaltin.",
        "; Jetonu paylasmayin; bu adres makinede komut calistirabilir.",
        "jeton =",
        "",
        "; Gelismis: panelin baslatilma bicimini tamamen degistirmek isterseniz.",
        "; Doluysa yukaridaki 'klasor' yok sayilir.",
        "; ONEMLI: icinde CIFT TIRNAK kullanmayin.",
        "; komut = cd ~/jarvis && . .venv/bin/activate && exec jarvis-panel --kamera"
    )
    $ini = ($satirlar -join "`r`n") + "`r`n"
    # UTF-8 BOM: baslatici .ini'yi UTF-8 olarak okuyor.
    [System.IO.File]::WriteAllText($iniYolu, $ini, (New-Object System.Text.UTF8Encoding $true))
    Yaz ""
    Yaz "  + $iniYolu"
}

# ---------------------------------------------------------------- kısayol

$script:MasaustundeVar = $false

function Kisayol-Yap($klasor, $ad, $masaustu = $false) {
    if ([string]::IsNullOrWhiteSpace($klasor)) {
        Yaz "  ! $ad yapılamadı: klasör yolu bulunamadı." "Yellow"
        return
    }
    try {
        if (-not (Test-Path $klasor)) {
            New-Item -ItemType Directory -Path $klasor -Force | Out-Null
        }
        $yol = Join-Path $klasor "JARVIS.lnk"
        $kabuk = New-Object -ComObject WScript.Shell
        $k = $kabuk.CreateShortcut($yol)
        $k.TargetPath       = Join-Path $Hedef "JARVIS.exe"
        $k.WorkingDirectory = $Hedef
        $k.IconLocation     = (Join-Path $Hedef "JARVIS.exe") + ",0"
        $k.Description      = "J.A.R.V.I.S. panelini baslat"
        $k.Save()
        Yaz "  + $ad"
        if ($masaustu) { $script:MasaustundeVar = $true }
    } catch {
        # Bir kısayolun yapılamaması kurulumu iptal ettirmemeli: exe kurulu,
        # elle de başlatılabilir.
        Yaz "  ! $ad yapılamadı: $($_.Exception.Message)" "Yellow"
    }
}

Kisayol-Yap $Masaustu "Masaüstü kısayolu" $true
Kisayol-Yap $BaslatMenusu "Başlat menüsü kısayolu"

Baslik "Kuruldu"
if ($script:MasaustundeVar) {
    Yaz "  Masaüstündeki JARVIS simgesine çift tıklayın." "Green"
} else {
    # Kısayol yapılamadıysa doğru talimat farklı; "simgeye tıklayın" demek
    # olmayan bir simgeyi aratır.
    Yaz "  Kısayol yapılamadı. Başlatmak için doğrudan:" "Yellow"
    Yaz "    $Hedef\JARVIS.exe" "Yellow"
}
Yaz ""
Yaz "  Kurulum yeri : $Hedef"
Yaz "  Ayarlar      : $iniYolu"
Yaz "  Kaldırmak    : Kur.cmd /kaldir"
Yaz ""
