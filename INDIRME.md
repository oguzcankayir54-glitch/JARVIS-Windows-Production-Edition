# J.A.R.V.I.S. indirme ve kurulum

## Windows için önerilen indirme

Hazır kurulum paketini indirin:

**[JARVIS-Setup-2.0.1.exe](https://github.com/oguzcankayir54-glitch/JARVIS-Windows-Production-Edition/releases/download/v2.0.1-production.8/JARVIS-Setup-2.0.1.exe)**

Dosyaya çift tıklayın ve kurulum sihirbazını tamamlayın. Paket henüz kod
imzalı olmadığı için SmartScreen görünürse **Daha fazla bilgi → Yine de
çalıştır** seçeneğini kullanın.

Paket bütünlüğünü doğrulamak isteyenler aynı Release içindeki
`JARVIS-Setup-2.0.1.exe.sha256` dosyasını kullanabilir.

## Kaynak koddan kurulum

1. [Production Edition deposunu](https://github.com/oguzcankayir54-glitch/JARVIS-Windows-Production-Edition) açın.
2. Dal olarak `feat/complete-project-sync` seçin.
3. **Code → Download ZIP** seçeneğine basın.
4. ZIP'i ayıklayıp `windows\Kur.cmd` dosyasına çift tıklayın.

Git ile:

```text
git clone --branch feat/complete-project-sync https://github.com/oguzcankayir54-glitch/JARVIS-Windows-Production-Edition.git
```

## Güncellemede korunanlar

| Veri | Konum | Davranış |
|---|---|---|
| `.env` ve servis anahtarları | `%LOCALAPPDATA%\Programs\JARVIS\app\.env` | Korunur |
| Panel jetonu | `%LOCALAPPDATA%\Programs\JARVIS\jarvis.ini` | Korunur |
| Hafıza, vakalar ve bilgi tabanı | `%USERPROFILE%\.jarvis` | Korunur |
| Sanal ortam | `%LOCALAPPDATA%\Programs\JARVIS\app\.venv` | Korunur |

Güncellemeden önce doğrulanmış bir yedek almak için:

```text
jarvis-yedek olustur "%USERPROFILE%\Documents\jarvis-yedek.zip"
```

## Kaldırma

Windows **Ayarlar → Uygulamalar → Yüklü uygulamalar** bölümünden
J.A.R.V.I.S.'i kaldırın. Kaynak kurulumunda `windows\Kur.cmd /kaldir`
kullanılabilir. Kullanıcı verileri bilinçli olarak silinmez.
