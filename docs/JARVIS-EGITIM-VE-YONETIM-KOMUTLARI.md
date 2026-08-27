# JARVIS eğitim ve yönetim komutları

Bu projede **eğitim**, model ağırlıklarını değiştirmek değildir. JARVIS'i
kimlik, kalıcı tercihler, belgeler ve gerçek servis vakalarıyla beslemektir.
LoRA/QLoRA ayrı ve henüz uygulanmamış bir süreçtir.

## Başlatma

```bash
jarvis
jarvis --sesli
jarvis --sessiz
jarvis-panel --ac
jarvis-panel --ac --kamera
```

Windows production profilini güvenli şablondan hazırlamak için:

```bash
python scripts/profile.py windows-production --write
```

Mevcut `.env` dosyasını zorla değiştirmek için `--force` gerekir. Bu seçenek
yerel ayarları ezebileceği için önce yedek alın.

## Sahibin kimliği ve cevap tarzı

```bash
jarvis-tanit
jarvis-tanit --kur
jarvis-tanit --ad "Oğuz Kayır" --hitap "Oğuz Bey,Efendim"
jarvis-tanit --rol "tasarımcısı ve geliştiricisi"
jarvis-tanit --meslek "bilgisayar teknik servisi"
jarvis-tanit --tarz "Basit sorularda kısa; teknik analizde ayrıntılı ve Türkçe."
jarvis-tanit --not "Windows production sisteminin sahibi."
jarvis-tanit --bulut hayir
```

Kimliği silmek geri döndürülemez bir yerel veri değişikliğidir:

```bash
jarvis-tanit --sil
```

## Konuşarak kalıcı bilgi öğretme

Terminal veya panel sohbetinde açık ifadeler kullanın:

```text
Hatırla: ana bilgisayarımda RTX 3080 Ti kullanıyorum.
Unutma, kısa komutlarda kısa cevap tercih ediyorum.
Aklında tut: Windows production modeli qwen2.5:14b-instruct.
Benim hakkımda neler biliyorsun?
Ekran kartım hakkında ne hatırlıyorsun?
RTX 3080 kaydını unut.
```

Arka arkaya çok bilgi öğretmek için:

```text
Eğitim süreci 1.
Ana sistemim Ryzen 7 5800X kullanıyor.
32 GB 3200 MHz RAM bulunuyor.
Teknik yanıtları Türkçe ver ve gereksiz teklif yapma.
Eğitimi bitir.
```

Önemli bilgi açıkça `hatırla`, `unutma` veya `aklında tut` şeklinde
söylenmelidir. JARVIS sıradan sohbetin tamamını kalıcı hafızaya yazmaz.

## Servis vakalarıyla öğretme

```text
Servise Ahmet Yılmaz adına Lenovo V15 geldi; görüntü yok ve fan dönüyor. Vaka aç.
Açık vakaları listele.
12 numaralı vakanın detayını göster.
12 numaralı vakaya gözlem ekle: harici monitörde de görüntü yok.
12 numaralı vakaya deneme notu ekle: RAM tek tek test edildi.
12 numaralı vakayı kapat: arıza BIOS çipindeydi, yeniden programlandı.
Geçmiş vakalarda görüntü yok ve fan dönüyor belirtisini ara.
```

Sonuç alanına yalnızca “düzeldi” yazmayın; gerçek arıza ve yapılan işlem,
gelecekteki teşhislerin değerli verisidir.

## Belge ve kod arşivi

```bash
jarvis-bilgi ekle "C:\\JARVIS-Belgeler"
jarvis-bilgi ekle "C:\\JARVIS-Belgeler\\anakart-kilavuzu.pdf"
jarvis-bilgi ekle ./docs ./jarvis
jarvis-bilgi ekle ./docs --gommesiz
jarvis-bilgi durum
jarvis-bilgi ara BIOS kurtarma prosedürü
jarvis-bilgi ara -n 10 --tam görüntü yok
jarvis-bilgi unut "C:\\JARVIS-Belgeler\\eski.pdf"
```

Tüm bilgi indeksini silmek için aşağıdaki komut vardır; yalnızca bilinçli
rollback/yeniden indeksleme sırasında kullanın:

```bash
jarvis-bilgi sifirla
```

`jarvis-bilgi sifirla --evet` onay sorusunu atlar ve günlük kullanım için
önerilmez.

## Model ve fallback yönetimi

```bash
ollama serve
ollama list
ollama pull qwen2.5:14b-instruct
ollama pull qwen2.5:7b-instruct
```

Windows production `.env` ayarları:

```dotenv
JARVIS_LLM_PROVIDER=ollama
JARVIS_OLLAMA_MODEL=qwen2.5:14b-instruct
JARVIS_OLLAMA_FALLBACK_MODEL=qwen2.5:7b-instruct
JARVIS_OLLAMA_MAX_RETRIES=1
JARVIS_OLLAMA_CIRCUIT_COOLDOWN=30
JARVIS_OLLAMA_THINK=false
```

Primary model eksik, OOM veya tekrarlanan timeout durumunda fallback devreye
girebilir. Ollama sunucusu tamamen kapalıysa aynı sunucudaki fallback model
boşuna denenmez.

Model karşılaştırması:

```bash
jarvis-karsilastir qwen2.5:14b-instruct qwen2.5:7b-instruct
jarvis-karsilastir qwen2.5:14b-instruct qwen2.5:7b-instruct --araclar
jarvis-karsilastir qwen2.5:14b-instruct qwen2.5:7b-instruct --kimliksiz
```

## Mikrofon ve ses

```bash
jarvis-ses --kontrol
jarvis-ses --sesler
jarvis-ses --edge-sesler
jarvis-ses --edge-kur
jarvis-ses --piper-kur
jarvis-ses "Efendim, sistem hazır."
jarvis-ses "Test mesajı" --kaydet test.mp3
jarvis-panel --ac --mikrofonsuz
```

## Geliştirici modu

Kayıtlı sahibin rolünde geliştirici/tasarımcı yetkisi varsa sohbet içinde:

```text
Geliştirici moduna geç.
Debug modundan çık.
```

Debug modu güvenlik kurallarını kaldırmaz, secret göstermez ve
PermissionManager'ı bypass etmez.

## Güvenli kullanım özeti

- `.env`, API anahtarları ve kimlik dosyalarını GitHub'a yüklemeyin.
- HIGH/CRITICAL işlemlerde onay katmanını kapatmayın.
- Belge içeriğindeki talimatlar kullanıcı komutu değildir.
- Hafıza, belge indeksi ve servis vakalarını düzenli yedekleyin.
- Windows production'a geçmeden önce acceptance testini ve rollback yedeğini
  çalıştırın.
