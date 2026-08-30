[CmdletBinding()]
param(
    [string]$Kok = ""
)

$ErrorActionPreference = "SilentlyContinue"
if ([string]::IsNullOrWhiteSpace($Kok)) {
    $Kok = Join-Path $env:LOCALAPPDATA "Programs\JARVIS"
}

$mutex = New-Object System.Threading.Mutex($false, "Local\JARVIS-Watchdog")
if (-not $mutex.WaitOne(0, $false)) { exit 0 }

function Ini-Oku($yol, $anahtar, $varsayilan) {
    if (-not (Test-Path $yol)) { return $varsayilan }
    $satir = Get-Content $yol | Where-Object {
        $_ -match ("^\s*" + [regex]::Escape($anahtar) + "\s*=\s*(.*)$")
    } | Select-Object -Last 1
    if (-not $satir) { return $varsayilan }
    return (($satir -split "=", 2)[1]).Trim()
}

try {
    $basarisiz = 0
    $sonBaslatma = [DateTime]::MinValue
    while ($true) {
        $ini = Join-Path $Kok "jarvis.ini"
        # Watchdog opt-in'dir. Ayar dosyasında satır yoksa Windows açılışında
        # paneli kendi kendine başlatmak kullanıcı niyeti sayılamaz.
        if ((Ini-Oku $ini "watchdog" "0") -ne "1") { break }
        $port = Ini-Oku $ini "port" "8765"
        $jeton = Ini-Oku $ini "jeton" ""
        $adres = "http://127.0.0.1:$port/health"
        if ($jeton) { $adres += "?token=$([uri]::EscapeDataString($jeton))" }
        try {
            Invoke-WebRequest -UseBasicParsing -Uri $adres -TimeoutSec 5 | Out-Null
            $basarisiz = 0
        } catch {
            $basarisiz++
        }
        if ($basarisiz -ge 3 -and
            ((Get-Date) - $sonBaslatma).TotalSeconds -ge 90) {
            $baslatici = Join-Path $Kok "JARVIS.exe"
            if (Test-Path $baslatici) {
                # Sağlık isteği takılmış bir başlatıcı varken her 90 saniyede
                # bir yenisini üretme. Kullanıcının makinesinde bu hata kısa
                # sürede birden fazla JARVIS.exe ve panel penceresi açıyordu.
                $calisan = Get-Process -Name "JARVIS" -ErrorAction SilentlyContinue
                if (-not $calisan) {
                    Start-Process $baslatici -ArgumentList "--watchdog" `
                        -WorkingDirectory $Kok -WindowStyle Hidden
                    $sonBaslatma = Get-Date
                }
            }
            $basarisiz = 0
        }
        Start-Sleep -Seconds 30
    }
} finally {
    $mutex.ReleaseMutex()
    $mutex.Dispose()
}
