# Windows kabul testi

Kurulumdan sonra PowerShell veya Komut İstemi'nde çalıştırın:

```powershell
& "$env:LOCALAPPDATA\Programs\JARVIS\app\.venv\Scripts\jarvis-kabul.exe"
```

Makinece okunabilir rapor için aynı komuta `--json` ekleyin. Kaynak kurulumu
etkinleştirilmiş bir terminalde kısa `jarvis-kabul` komutu da kullanılabilir.
Komut yalnızca
durum okur; kamera veya mikrofonu açmaz, ayar değiştirmez, paket kurmaz ve
kişisel veriyi dışarı göndermez. Sonuçlar paneldeki **Kabul** sekmesinde de
görünür.

## Denetlenen alanlar

- Windows ve desteklenen Python sürümü
- Veri klasörünün yazılabilirliği ve en az 5 GB boş disk
- Ollama servisinin ve seçilen gerçek modelin varlığı
- Seslendirme, faster-whisper mikrofon ve OpenCV kamera altyapısı
- Windows kullanıcı oturumu bildirim desteği
- Sistem telemetrisi ve regresyon test paketi

`HAZIR`, denetimin geçtiğini; `EKSİK`, özellik/ayarın bulunmadığını;
`ARIZALI`, etkin olması beklenen bileşenin çalışmadığını gösterir. Her eksik
veya arızalı satır uygulanabilir bir çözüm komutu verir.

## Donanımın son fiziksel doğrulaması

Gizlilik nedeniyle kabul komutu cihazları kendiliğinden etkinleştirmez.
Altyapı `HAZIR` olduktan sonra panelde mikrofonla kısa bir Türkçe cümle
kaydedin, kamera önizlemesini açın, yazılı cevabın sesini dinleyin ve bir
dakikalık ajanda kaydıyla Windows bildirimini doğrulayın. Bu adımlar gerçek
aygıt ve tarayıcı izni gerektirdiği için otomatik test başarılıymış gibi
göstermez.
