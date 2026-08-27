<#
    J.A.R.V.I.S. — WSL2 port yönlendirmesi

    WSL'in IP adresi her yeniden başlatmada değişir. Yönlendirme kuralı ise
    eski adreste kalır ve 0.0.0.0:8765'i dinlemeye devam eder — yani
    localhost dahil her isteği yakalayıp ölü bir adrese gönderir. Tarayıcı
    bunu ERR_CONNECTION_RESET diye gösterir: bağlantı kabul edildi, sonra
    koptu. Panel çalışıyor olsa bile ulaşılamaz.

    Bu betik kuralı güncel IP'ye göre yeniden kurar ve sonucu sınar.

    Çalıştırma (PowerShell'i YÖNETİCİ olarak açın):
        cd \\wsl$\Ubuntu\home\<kullanıcı>\jarvis\scripts
        powershell -ExecutionPolicy Bypass -File .\windows-yonlendirme.ps1

    Kaldırmak için:
        .\windows-yonlendirme.ps1 -Kaldir
#>
param(
    [int]$Port = 8765,
    [switch]$Kaldir
)

$ErrorActionPreference = "Stop"

function Yaz($isaret, $renk, $metin) { Write-Host "$isaret $metin" -ForegroundColor $renk }
function Ok($m)   { Yaz "OK  " Green  $m }
function Uyari($m){ Yaz "!   " Yellow $m }
function Hata($m) { Yaz "HATA" Red    $m }

# --- yönetici mi? --------------------------------------------------------
$kimlik = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
if (-not $kimlik.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Hata "Bu betik yonetici yetkisi ister."
    Write-Host "  PowerShell'e sag tiklayip 'Yonetici olarak calistir' secin."
    exit 1
}

Write-Host ""
Write-Host "J.A.R.V.I.S. - WSL2 port yonlendirmesi (port $Port)" -ForegroundColor Cyan
Write-Host ("-" * 52)

if ($Kaldir) {
    netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=0.0.0.0 2>$null | Out-Null
    Remove-NetFirewallRule -DisplayName "JARVIS Panel" -ErrorAction SilentlyContinue
    Ok "Yonlendirme ve guvenlik duvari kurali kaldirildi."
    exit 0
}

# --- IP Helper servisi ---------------------------------------------------
# portproxy bu servise dayanir. Servis durmussa kural listede gorunur ama
# hicbir sey yapmaz - sessiz ve bulmasi zor bir ariza.
$svc = Get-Service iphlpsvc -ErrorAction SilentlyContinue
if ($null -eq $svc) {
    Hata "iphlpsvc (IP Helper) servisi bulunamadi."
    exit 1
}
if ($svc.StartType -eq "Disabled") {
    Set-Service iphlpsvc -StartupType Automatic
    Uyari "iphlpsvc devre disiydi, otomatige alindi."
}
if ($svc.Status -ne "Running") {
    Start-Service iphlpsvc
    Ok "iphlpsvc baslatildi (portproxy bu servise dayanir)."
} else {
    Ok "iphlpsvc calisiyor."
}

# --- WSL'in guncel adresi ------------------------------------------------
$wsl = (wsl hostname -I 2>$null)
if (-not $wsl) {
    Hata "WSL'den IP alinamadi. WSL calisiyor mu?  wsl -l -v"
    exit 1
}
$wsl = $wsl.Trim().Split(" ")[0]
Ok "WSL adresi: $wsl"

# --- kurali yenile -------------------------------------------------------
netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=0.0.0.0 2>$null | Out-Null
netsh interface portproxy add v4tov4 listenport=$Port listenaddress=0.0.0.0 connectport=$Port connectaddress=$wsl | Out-Null
Ok "Yonlendirme kuruldu: 0.0.0.0:$Port -> ${wsl}:$Port"

# --- guvenlik duvari -----------------------------------------------------
# Yalnizca "Ozel" ag profilinde: kural kafe/otel Wi-Fi'sinde kapali kalsin.
if (-not (Get-NetFirewallRule -DisplayName "JARVIS Panel" -ErrorAction SilentlyContinue)) {
    New-NetFirewallRule -DisplayName "JARVIS Panel" -Direction Inbound `
        -LocalPort $Port -Protocol TCP -Action Allow -Profile Private | Out-Null
    Ok "Guvenlik duvari kurali eklendi (yalnizca Ozel ag)."
} else {
    Ok "Guvenlik duvari kurali zaten var."
}

# --- sina ----------------------------------------------------------------
# Iki ayri sinama, cunku iki ayri ariza var ve tek mesaj ikisini de "panele
# ulasilamadi" diye anlatirsa yanlis yere bakilir:
#   WSL'e dogrudan ulasilamiyor  -> panel calismiyor (ya da 0.0.0.0'da degil)
#   WSL tamam ama localhost degil -> yonlendirme/servis tarafi
function Sina($url) {
    try   { return @{ ok = $true;  govde = (Invoke-WebRequest -Uri $url -TimeoutSec 5 -UseBasicParsing).Content } }
    catch {
        # 401 means the panel answered — it is alive and asking for a token.
        # Reading that as "not running" sent us hunting a dead panel while it
        # was serving normally, so any HTTP status at all counts as reachable.
        $kod = $null
        try { $kod = [int]$_.Exception.Response.StatusCode } catch { }
        if ($kod) { return @{ ok = $true; govde = "HTTP $kod (panel cevap veriyor)" } }
        return @{ ok = $false; govde = $_.Exception.Message }
    }
}

Write-Host ""
Write-Host "Sinaniyor..." -ForegroundColor Cyan

$dogrudan = Sina "http://${wsl}:$Port/health"
$yerel    = Sina "http://localhost:$Port/health"

if ($yerel.ok) {
    Ok "Panele ulasildi: $($yerel.govde)"
    $ip = (Get-NetIPAddress -AddressFamily IPv4 |
           Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "172.*" } |
           Select-Object -First 1).IPAddress
    Write-Host ""
    Write-Host "  Bu bilgisayardan : http://localhost:$Port"
    if ($ip) { Write-Host "  Telefondan       : http://${ip}:$Port/?token=JETONUNUZ" }
    Write-Host ""
    Write-Host "  Jetonu jarvis-panel'i baslattiginiz terminal yaziyor." -ForegroundColor DarkGray
}
elseif (-not $dogrudan.ok) {
    # WSL'in kendi adresine de ulasilamiyor: sorun yonlendirmede degil.
    Uyari "Panel calismiyor gorunuyor - WSL adresine de ulasilamadi."
    Write-Host ""
    Write-Host "  WSL terminalinde calistirin ve o pencereyi ACIK BIRAKIN:"
    Write-Host "      cd ~/jarvis && source .venv/bin/activate && jarvis-panel --host 0.0.0.0" -ForegroundColor White
    Write-Host ""
    Write-Host "  Zaten calisiyorsa: --host 0.0.0.0 vermeyi unutmus olabilirsiniz."
    Write-Host "  Varsayilan 127.0.0.1'dir ve WSL disina cikmaz. WSL'de kontrol:"
    Write-Host "      ss -tlnp | grep $Port        # 0.0.0.0:$Port yazmali"
    Write-Host ""
    Write-Host "  Panel acikken bu betigi tekrar calistirin."
}
else {
    # Panel ayakta ama Windows'tan gecmiyor: yonlendirme katmani suclu.
    Uyari "Panel calisiyor (WSL adresinden ulasildi) ama localhost'tan gecmiyor."
    Write-Host "  Yonlendirme kuruldu, yine de istek WSL'e varmiyor. Sirasiyla:"
    Write-Host "    1) Bu betigi bir kez daha calistirin (WSL IP'si yeni degismis olabilir)"
    Write-Host "    2) Ucuncu parti guvenlik duvari / antivirus 8765'i kesiyor olabilir"
    Write-Host "    3) netsh interface portproxy show v4tov4   ile kurali dogrulayin"
}
Write-Host ""
