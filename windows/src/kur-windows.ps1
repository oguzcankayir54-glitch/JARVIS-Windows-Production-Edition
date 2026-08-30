<#
    J.A.R.V.I.S. — saf Windows kurulumu

    WSL yok. Ne dağıtım, ne interop, ne her yeniden başlatmada değişen bir
    sanal ağ, ne de portproxy zinciri. Python doğrudan Windows'ta çalışıyor,
    panel doğrudan Windows'ta açılıyor.

    Yönetici gerektirmez: her şey kullanıcı profiline kuruluyor.

    Yaptıkları:
      1. Python'u bulur (yoksa nereden alınacağını söyler)
      2. Projeyi %LOCALAPPDATA%\Programs\JARVIS\app altına kopyalar
      3. Kendi .venv'ini kurar ve bağımlılıkları yükler
      4. .env ve kimlik.json'u hazırlar (varsa dokunmaz)
      5. jarvis.ini'yi "mod = windows" olarak yazar
      6. Masaüstüne ve Başlat menüsüne kısayol koyar
      7. Kurulumun gerçekten çalıştığını DOĞRULAR

    Son adım isteğe bağlı değil. Bu projede iki kez "kurulum bitti" denip
    ilk çift tıklamada hata alındı; kurulum kendi işini kendi kontrol
    etmezse kontrolü kullanıcı yapıyor demektir.
#>
[CmdletBinding()]
param(
    [switch]$Kaldir,
    [string]$Python = "",
    [switch]$Sessiz
)

$ErrorActionPreference = "Stop"

$Kaynak = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Kok    = Join-Path $env:LOCALAPPDATA "Programs\JARVIS"
$Uygulama = Join-Path $Kok "app"
$Venv   = Join-Path $Uygulama ".venv"
$VenvPy = Join-Path $Venv "Scripts\python.exe"

$Masaustu = [Environment]::GetFolderPath("Desktop")
if ([string]::IsNullOrWhiteSpace($Masaustu) -and $env:USERPROFILE) {
    $Masaustu = Join-Path $env:USERPROFILE "Desktop"
}
$BaslatMenusu = ""
if ($env:APPDATA) {
    $BaslatMenusu = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs"
}
$Baslangic = ""
if ($env:APPDATA) {
    $Baslangic = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
}

function Yaz($metin, $renk = "Gray") { Write-Host $metin -ForegroundColor $renk }
function Baslik($metin) {
    Write-Host ""
    Write-Host ("=" * 58) -ForegroundColor DarkCyan
    Write-Host "  $metin" -ForegroundColor Cyan
    Write-Host ("=" * 58) -ForegroundColor DarkCyan
}
function Adim($n, $metin) { Yaz "" ; Yaz "[$n] $metin" "White" }
function Tamam($metin) { Yaz "    OK  $metin" "Green" }
function Uyari($metin) { Yaz "    !   $metin" "Yellow" }
function Hata($metin)  { Yaz "    X   $metin" "Red" }

# ------------------------------------------------------------------ kaldirma

if ($Kaldir) {
    Baslik "J.A.R.V.I.S. kaldiriliyor"
    foreach ($k in @((Join-Path $Masaustu "J.A.R.V.I.S..lnk"),
                     (Join-Path $BaslatMenusu "J.A.R.V.I.S..lnk"),
                     (Join-Path $Baslangic "J.A.R.V.I.S. Watchdog.lnk"),
                     (Join-Path $Masaustu "F.R.I.D.A.Y..lnk"),
                     (Join-Path $BaslatMenusu "F.R.I.D.A.Y..lnk"))) {
        if ($k -and (Test-Path $k)) { Remove-Item $k -Force; Tamam "kisayol silindi" }
    }
    if (Test-Path $Kok) {
        # Veri klasoru (~/.jarvis) BILEREK silinmiyor: hafiza, vakalar ve
        # bilgi tabani orada duruyor ve program silindi diye gitmemeli.
        Remove-Item $Kok -Recurse -Force
        Tamam "program klasoru silindi"
    }
    Yaz ""
    Yaz "  Hafiza ve notlar duruyor: $env:USERPROFILE\.jarvis" "DarkGray"
    Yaz "  Onlari da silmek isterseniz o klasoru elle kaldirin." "DarkGray"
    Yaz ""
    return
}

Baslik "J.A.R.V.I.S. — Windows kurulumu"

# ------------------------------------------------------------------ 1. Python

Adim 1 "Python araniyor"

function Python-Bul {
    param([string]$Tercih)

    $adaylar = @()
    if ($Tercih) { $adaylar += $Tercih }
    # py.exe (Python Launcher) Windows'ta en guvenilir yol: birden fazla
    # surum kuruluysa dogru olani secmeyi o biliyor.
    $adaylar += @("py", "python", "python3")

    foreach ($aday in $adaylar) {
        $komut = Get-Command $aday -ErrorAction SilentlyContinue
        if (-not $komut) { continue }
        try {
            # $args YAZILMAZ: PowerShell'in otomatik degiskeni, islevin kendi
            # argumanlarini tutuyor. Uzerine yazmak splatting'i bozar.
            $pArgs = if ($aday -eq "py") { @("-3.11", "-c", "import sys;print(sys.executable)") }
                     else { @("-c", "import sys;print(sys.executable)") }
            $yol = & $komut.Source @pArgs 2>$null
            if ($LASTEXITCODE -ne 0 -or -not $yol) { continue }
            $yol = $yol.Trim()
            # Microsoft Store'un "app execution alias" saplamasi python.exe
            # gibi gorunup Store'u aciyor. Gercek bir yorumlayici degil.
            if ($yol -like "*WindowsApps*") { continue }
            $surum = & $yol -c "import sys;print('%d.%d' % sys.version_info[:2])" 2>$null
            if (-not $surum) { continue }
            $parca = $surum.Trim().Split('.')
            if ([int]$parca[0] -lt 3 -or [int]$parca[1] -lt 10) { continue }
            return [pscustomobject]@{ Yol = $yol; Surum = $surum.Trim() }
        } catch { continue }
    }
    return $null
}

$py = Python-Bul -Tercih $Python
if (-not $py) {
    Hata "Python 3.10 veya uzeri bulunamadi."
    Yaz ""
    Yaz "    Kurmak icin (yonetici gerekmez):" "White"
    Yaz "        winget install Python.Python.3.11" "Cyan"
    Yaz ""
    Yaz "    Ya da: https://www.python.org/downloads/windows/" "Cyan"
    Yaz "    Kurulum sirasinda 'Add python.exe to PATH' KUTUSUNU ISARETLEYIN." "Yellow"
    Yaz ""
    Yaz "    Kurduktan sonra bu pencereyi kapatip Kur.cmd'yi tekrar calistirin." "Gray"
    exit 1
}
Tamam "Python $($py.Surum) — $($py.Yol)"

# ------------------------------------------------------------------ 2. kopyala

Adim 2 "Dosyalar kopyalaniyor"

New-Item -ItemType Directory -Force -Path $Uygulama | Out-Null

# Kaynak: bu betigin iki ust klasoru = depo koku.
$Depo = Split-Path -Parent $Kaynak
if (-not (Test-Path (Join-Path $Depo "pyproject.toml"))) {
    # Kur.cmd depo icinden calisiyorsa bir ust klasor dogru olur; degilse
    # kullanicinin nereden calistirdigini bilemiyoruz.
    Hata "Proje dosyalari bulunamadi: $Depo"
    Yaz "    Kur.cmd'yi depo klasorunun icinden calistirin." "Yellow"
    exit 1
}

# Kopyalanmayacaklar: kendi .venv'i, git gecmisi, derleme artiklari ve
# kullanicinin .env'i (asagida ayri ele aliniyor).
$atla = @(".venv", ".git", "__pycache__", ".pytest_cache", "node_modules")
Get-ChildItem -Path $Depo -Force | ForEach-Object {
    if ($atla -contains $_.Name) { return }
    $hedef = Join-Path $Uygulama $_.Name
    if ($_.PSIsContainer) {
        Copy-Item $_.FullName -Destination $hedef -Recurse -Force `
                  -Exclude @("__pycache__", "*.pyc")
    } else {
        Copy-Item $_.FullName -Destination $hedef -Force
    }
}
Tamam "proje $Uygulama altina kopyalandi"

Copy-Item (Join-Path $Kaynak "JARVIS.exe") -Destination $Kok -Force
Copy-Item (Join-Path $Kaynak "jarvis.ico") -Destination $Kok -Force
Tamam "baslatici ve simge yerlestirildi"

# ------------------------------------------------------------------ 3. venv

Adim 3 "Sanal ortam kuruluyor (birkac dakika surebilir)"

if (-not (Test-Path $VenvPy)) {
    & $py.Yol -m venv $Venv
    if ($LASTEXITCODE -ne 0) {
        Hata "Sanal ortam kurulamadi."
        exit 1
    }
}
Tamam "$Venv"

Yaz "    pip guncelleniyor..." "DarkGray"
& $VenvPy -m pip install --upgrade pip --quiet 2>&1 | Out-Null

Yaz "    J.A.R.V.I.S. kuruluyor..." "DarkGray"
& $VenvPy -m pip install --quiet -e "$Uygulama[kod]"
if ($LASTEXITCODE -ne 0) {
    Hata "Bagimliliklar kurulamadi."
    exit 1
}
Tamam "temel paketler"

# Ses ve mikrofon istege bagli: olmadan da calisiyor, ve indirmeleri buyuk.
# Basarisiz olmalari kurulumu DUSURMEMELI — panel yazarak yine calisir.
foreach ($ek in @(
    @{ Ad = "Yerel Craig sesi (XTTS)"; Paket = "$Uygulama[ses-xtts]" },
    @{ Ad = "Ses (edge-tts)";        Paket = "edge-tts>=7.0" },
    @{ Ad = "Mikrofon (whisper)";    Paket = "faster-whisper>=1.0" }
)) {
    Yaz "    $($ek.Ad) kuruluyor..." "DarkGray"
    & $VenvPy -m pip install --quiet $ek.Paket 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) { Tamam $ek.Ad } else { Uyari "$($ek.Ad) kurulamadi — bu ozellik kapali kalir" }
}

# ------------------------------------------------------------------ 4. ayarlar

Adim 4 "Ayarlar hazirlaniyor"

$EnvYolu = Join-Path $Uygulama ".env"
if (Test-Path $EnvYolu) {
    Tamam ".env zaten var — dokunulmadi"
} else {
    # UTF8 BOM'suz: Notepad'in BOM'u ilk satiri sessizce yutuyordu ve
    # "anahtar hic ayarlanmamis" gibi gorunuyordu. Buradan BOM'suz cikiyor.
    $satirlar = @(
        "# J.A.R.V.I.S. ayarlari",
        "",
        "# Dil modeli. 'mock' anahtar kelime esleyen SAHTE bir modeldir:",
        "# sizi tanimaz, soylediginizi anlamaz. Gercek model icin Ollama:",
        "#     winget install Ollama.Ollama",
        "#     ollama pull qwen2.5:14b-instruct",
        "JARVIS_LLM_PROVIDER=ollama",
        "JARVIS_OLLAMA_MODEL=qwen2.5:14b-instruct",
        "",
        "# Baglam penceresi. Yazilmazsa Ollama'nin varsayilani (2048)",
        "# gecerli oluyor ve ilk tur bile onu asiyor; pencere tastiginda",
        "# en eski mesaj -- sistem istemi -- kirpiliyor ve J.A.R.V.I.S.",
        "# kisiligini, Turkce kuralini ve sizi tanimayi kaybediyor.",
        "# Buyutmek bellek istiyor: 8192 ~1.6 GB, 32768 ~6.3 GB KV onbellegi.",
        "JARVIS_OLLAMA_NUM_CTX=8192",
        "",
        "# Ana ses: ElevenLabs. API anahtarini ve ses kimligini asagidaki satirlara girin.",
        "JARVIS_TTS_PROVIDER=elevenlabs",
        "ELEVENLABS_API_KEY=",
        "ELEVENLABS_VOICE_ID=",
        "ELEVENLABS_TIMEOUT=15",
        "ELEVENLABS_MAX_RETRIES=0",
        "COQUI_TOS_AGREED=1",
        "JARVIS_XTTS_SPEAKER=Craig Gutsy",
        "JARVIS_XTTS_SPEED=1.04",
        "JARVIS_XTTS_DEVICE=auto",
        "JARVIS_XTTS_PRELOAD=true",
        "JARVIS_XTTS_READY_BEFORE_LISTEN=true",
        "JARVIS_XTTS_CACHE_SIZE=32",
        "",
        "# Mikrofon",
        "JARVIS_STT_ENABLED=true",
        "JARVIS_STT_MODEL=small",
        ""
    )
    # [string[]] donusumu SART: WriteAllLines Object[] kabul etmiyor ve
    # "asiri yukleme bulunamadi" ile dusuyor.
    [System.IO.File]::WriteAllLines($EnvYolu, [string[]]$satirlar,
        (New-Object System.Text.UTF8Encoding $false))
    Tamam ".env yazildi"
}

# Ayar dosyasi baslatici tarafindan okunuyor: port, jeton, pencere olculeri.
function Ini-Yaz($kod, $ad, $port) {
    $yol = Join-Path $Kok "$kod.ini"
    $satirlar = @(
        "; $ad baslatici ayarlari — Windows kurulumu",
        "[jarvis]",
        "mod = windows",
        "klasor = $Uygulama",
        "python = $VenvPy",
        "port = $port",
        "tarayici = 1",
        "uygulama = 1",
        "tamekran = 1",
        "genislik = 1920",
        "yukseklik = 1080",
        "intro = 1",
        "watchdog = 0",
        "jeton ="
    )
    if (Test-Path $yol) {
        # Jeton bir kez uretilip yaziliyor ve sabit kalmasi istendi.
        # Kurulumu tekrar calistirmak onu SIFIRLAMAMALI.
        $eski = Get-Content $yol -ErrorAction SilentlyContinue |
                Where-Object { $_ -match '^\s*jeton\s*=\s*\S' }
        # @() sarmalamasi SART: Where-Object tek satir donerse dize doner
        # ve $eski[0] ilk KARAKTERI verir — jeton "j" olurdu.
        $eski = @($eski)
        if ($eski.Count -gt 0) {
            $satirlar[$satirlar.Count - 1] = $eski[0].Trim()
            Tamam "$kod.ini: mevcut jeton korundu"
        }
    }
    [System.IO.File]::WriteAllLines($yol, [string[]]$satirlar,
        (New-Object System.Text.UTF8Encoding $true))
    Tamam "$kod.ini yazildi (mod = windows, port $port)"
}

Ini-Yaz "jarvis" "J.A.R.V.I.S." 8765

# Bir donem ikinci bir asistan (F.R.I.D.A.Y.) kuruluyordu; kaldirildi.
# ONCEDEN kurmus olanlarda masaustunde calismayan bir simge ve artik
# okunmayan bir friday.ini kaliyor. Kurulum kendi biraktigi seyi kendi
# topluyor: kullanicidan elle silmesini beklemek, "kaldirdim" demenin
# yarim kalmasi olurdu.
$kalinti = @((Join-Path $Kok "friday.ini"),
             (Join-Path $Masaustu "F.R.I.D.A.Y..lnk"),
             (Join-Path $BaslatMenusu "F.R.I.D.A.Y..lnk"))
foreach ($k in $kalinti) {
    if ([string]::IsNullOrWhiteSpace($k)) { continue }
    if (Test-Path $k) {
        Remove-Item $k -Force -ErrorAction SilentlyContinue
        Tamam "eski F.R.I.D.A.Y. kalintisi silindi: $(Split-Path $k -Leaf)"
    }
}

# ------------------------------------------------------------------ 5. kisayol

Adim 5 "Kisayollar olusturuluyor"

function Kisayol-Yap($hedefKlasor, $ad, $aciklama) {
    if ([string]::IsNullOrWhiteSpace($hedefKlasor)) { return $false }
    if (-not (Test-Path $hedefKlasor)) { return $false }
    $kabuk = New-Object -ComObject WScript.Shell
    $lnk = $kabuk.CreateShortcut((Join-Path $hedefKlasor "$ad.lnk"))
    $lnk.TargetPath = Join-Path $Kok "JARVIS.exe"
    $lnk.WorkingDirectory = $Kok
    $lnk.IconLocation = Join-Path $Kok "jarvis.ico"
    $lnk.Description = $aciklama
    $lnk.Save()
    return $true
}

if (Kisayol-Yap $Masaustu "J.A.R.V.I.S." "J.A.R.V.I.S. — kisisel teknik asistan") {
    Tamam "masaustu: J.A.R.V.I.S."
} else { Uyari "masaustu kisayolu atlandi (klasor bulunamadi)" }
Kisayol-Yap $BaslatMenusu "J.A.R.V.I.S." "J.A.R.V.I.S. — kisisel teknik asistan" | Out-Null

# Watchdog kullanici oturumunda calisir; yonetici veya Windows servisi
# gerekmez. Panel uc kez ust uste yanit vermezse baslaticiyi yeniden acar.
if ($Baslangic -and (Test-Path $Baslangic)) {
    $kabuk = New-Object -ComObject WScript.Shell
    $lnk = $kabuk.CreateShortcut((Join-Path $Baslangic "J.A.R.V.I.S. Watchdog.lnk"))
    $lnk.TargetPath = "powershell.exe"
    $watchdog = Join-Path $Uygulama "windows\src\watchdog.ps1"
    $lnk.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$watchdog`" -Kok `"$Kok`""
    $lnk.WorkingDirectory = $Kok
    $lnk.IconLocation = Join-Path $Kok "jarvis.ico"
    $lnk.Description = "J.A.R.V.I.S. panelini izler ve gerekirse yeniden baslatir"
    $lnk.Save()
    Tamam "watchdog Windows baslangicina eklendi"
} else { Uyari "watchdog baslangic kisayolu olusturulamadi" }

# ------------------------------------------------------------------ 6. dogrula

Adim 6 "Kurulum dogrulaniyor"

$sorun = 0

& $VenvPy -c "import jarvis; print(jarvis.__name__)" 2>&1 | Out-Null
if ($LASTEXITCODE -eq 0) { Tamam "jarvis paketi ice aktarilabiliyor" }
else { Hata "jarvis paketi ice aktarilamiyor"; $sorun++ }

$kimlik = & $VenvPy -c "from jarvis.core.kimlik_tohumu import tohumu_bul; s=tohumu_bul(); print(s.name if s else '')" 2>$null
if ($kimlik) { Tamam "kimlik hazir: $kimlik" }
else { Uyari "kimlik.json okunamadi — J.A.R.V.I.S. sizi tanimayabilir" }

$ollama = Get-Command "ollama" -ErrorAction SilentlyContinue
if ($ollama) {
    Tamam "Ollama kurulu"
} else {
    Uyari "Ollama YOK — gercek dil modeli olmadan J.A.R.V.I.S. sizi anlamaz."
    Yaz "        winget install Ollama.Ollama" "Cyan"
    Yaz "        ollama pull qwen2.5:14b-instruct" "Cyan"
}

if (-not (Test-Path (Join-Path $Kok "JARVIS.exe"))) { Hata "JARVIS.exe yerinde degil"; $sorun++ }

# ------------------------------------------------------------------ bitis

Baslik $(if ($sorun -eq 0) { "Kurulum tamam" } else { "Kurulum bitti — $sorun sorun var" })
Yaz ""
Yaz "  Program : $Kok" "Gray"
Yaz "  Proje   : $Uygulama" "Gray"
Yaz "  Veriler : $env:USERPROFILE\.jarvis" "Gray"
Yaz ""
Yaz "  Masaustundeki J.A.R.V.I.S. simgesine cift tiklayin." "White"
Yaz "  Panel 1920x1080 tam ekran acilir; cikmak icin F11." "DarkGray"
Yaz ""
if (-not $Sessiz) {
    Yaz "  Kapatmak icin Enter'a basin." "DarkGray"
    [void](Read-Host)
}
exit $(if ($sorun -eq 0) { 0 } else { 1 })
