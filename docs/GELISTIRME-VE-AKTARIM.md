# Linux Lite → Windows geliştirme ve aktarım akışı

## 1. Profil seçimi

Profili ekranda görmek için:

```bash
python scripts/profile.py lite
python scripts/profile.py windows-dev
python scripts/profile.py windows-production
```

Yeni bir yerel `.env` oluşturmak için `--write` kullanılır. Var olan `.env`,
anahtarları ve kişisel ayarları korumak için varsayılan olarak değiştirilmez.

## 2. Linux doğrulaması

```bash
python -m pytest -q
./self-test-lite.sh
```

Panel testi soket açılmasına izin verilen normal bir Linux oturumunda yapılır.

## 3. Windows paketi

```bash
python scripts/windows_transfer.py --output /tmp/jarvis-windows.zip
python scripts/windows_transfer.py --verify /tmp/jarvis-windows.zip
```

Paket `.env`, API anahtarları, `kimlik.json`, hafıza/veritabanı, loglar, sanal
ortam ve Git geçmişini içermez. Manifest her dosyanın SHA-256 özetini taşır.
Temiz hedefte sahibi tanımlamak için `jarvis-tanit --kur` çalıştırılır; mevcut
Windows hafızası ise yükseltme sırasında yerinde korunur.

## 4. Windows/WSL kabul testi

ZIP'i hedef klasöre açıp sanal ortamı etkinleştirdikten sonra:

```bash
python scripts/windows_acceptance.py
```

Bu test gerçek kullanıcı verisine dokunmaz ve mock model kullanır. Geçtikten
sonra Ollama/GPU, mikrofon, kamera ve TTS gerçek donanımda ayrı sınanır.
