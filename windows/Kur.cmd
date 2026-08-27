@echo off
rem J.A.R.V.I.S. - kurulum. Cift tiklayin.
rem
rem PowerShell betikleri cift tiklamayla calismaz (Not Defteri'nde acilir),
rem bu yuzden asil is src\ icindeki betikte ve buradan cagriliyor.
rem
rem Varsayilan artik SAF WINDOWS kurulumu: WSL gerekmiyor.
rem   Kur.cmd            - Windows'a kur (onerilen)
rem   Kur.cmd /wsl       - eski WSL kurulumu
rem   Kur.cmd /kaldir    - kaldir

setlocal
set "BURASI=%~dp0"
set "BETIK=%BURASI%src\kur-windows.ps1"
set "EKPARAM="
rem Asagidaki "pause" zaten bekletiyor; betikten ikinci bir tus istemesini
rem beklemiyoruz. Eski kur.ps1 bu parametreyi TANIMIYOR ve kendisine
rem gonderilirse "parametre bulunamadi" ile duser - o yuzden /wsl
rem secildiginde siliniyor.
set "SESSIZ=-Sessiz"

if /i "%~1"=="/wsl"       set "BETIK=%BURASI%src\kur.ps1" & set "SESSIZ="
if /i "%~1"=="-wsl"       set "BETIK=%BURASI%src\kur.ps1" & set "SESSIZ="
if /i "%~1"=="/kaldir"    set "EKPARAM=-Kaldir"
if /i "%~1"=="-kaldir"    set "EKPARAM=-Kaldir"
if /i "%~1"=="--kaldir"   set "EKPARAM=-Kaldir"

powershell -NoProfile -ExecutionPolicy Bypass -File "%BETIK%" %EKPARAM% %SESSIZ%

echo.
pause
