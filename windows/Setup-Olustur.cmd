@echo off
setlocal
rem J.A.R.V.I.S. Setup derleyicisi. Inno Setup 6 veya 7 gerekir.

set "BURASI=%~dp0"
set "ISS=%BURASI%installer\JARVIS.iss"
set "ISCC="

if exist "%ProgramFiles%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 7\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if exist "%ProgramFiles%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles%\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"

if not defined ISCC (
    echo.
    echo HATA: Inno Setup 6 veya 7 bulunamadi.
    echo Kurmak icin:
    echo   winget install JRSoftware.InnoSetup
    echo.
    echo Sonra bu dosyaya yeniden cift tiklayin.
    echo.
    pause
    exit /b 1
)

echo JARVIS-Setup.exe olusturuluyor...
"%ISCC%" "%ISS%"
if errorlevel 1 (
    echo.
    echo HATA: Setup derlenemedi.
    pause
    exit /b 1
)

echo.
echo TAMAM: %BURASI%release\JARVIS-Setup-2.0.1.exe
echo.
pause
