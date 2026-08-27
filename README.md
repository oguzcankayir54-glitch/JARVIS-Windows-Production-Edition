# J.A.R.V.I.S. — Windows Production Edition

J.A.R.V.I.S.; Türkçe konuşan, yerel yapay zekâ modeliyle çalışabilen, sesli
iletişim, kalıcı hafıza, teknik servis vaka kaydı, sistem araçları, bilgi tabanı
ve canlı Neural Core panelini tek uygulamada birleştiren kişisel teknisyen
asistanıdır.

Projenin ana hedefi **saf Windows kurulumu**dur. Python, Ollama ve J.A.R.V.I.S.
doğrudan Windows üzerinde çalışır; WSL zorunlu değildir. Linux desteği geliştirme,
test ve alternatif kurulum amacıyla korunmaktadır.

> **Sürüm:** 2.0.1
>
> **Durum:** Çekirdek, panel, hafıza, RAG, ses, mikrofon ve güvenli araç katmanı
> çalışıyor. Gerçek donanım kabul testleri ve üretim kurulum sertleştirmesi devam
> ediyor.

## Öne çıkan özellikler

### Yapay zekâ çekirdeği

- Ollama üzerinden tamamen yerel LLM çalıştırma
- Varsayılan model: `qwen2.5:14b-instruct`
- Daha küçük modele otomatik fallback desteği
- Bağlam yönetimi, niyet yönlendirme ve kontrollü araç seçimi
- Model veya servis hatasında güvenli biçimde `STANDBY` durumuna dönüş
- Testler için internet ve model gerektirmeyen `mock` sağlayıcı

### Neural Core paneli

- Tarayıcı tabanlı canlı kontrol paneli
- `HAZIR`, `DİNLİYOR`, `DÜŞÜNÜYOR`, `ANALİZ EDİYOR` ve `KONUŞUYOR` durumları
- SSE üzerinden canlı durum ve telemetri güncellemeleri
- Metin sohbeti, mikrofon, seslendirme ve Vision bölümleri
- CPU, RAM, disk, GPU ve sistem bilgilerinin gerçek zamanlı gösterimi
- Windows masaüstü başlatıcısı ve tek örnek çalışma kontrolü
- Yerel kullanımda `127.0.0.1`; ağ erişiminde zorunlu erişim jetonu

### Türkçe ses ve mikrofon

- **ElevenLabs:** doğal bulut sesi; `eleven_flash_v2_5` ve `eleven_v3`
- **Edge TTS:** ücretsiz çevrimiçi Türkçe ses
- **Piper:** tamamen yerel ve çevrimdışı yedek ses
- **faster-whisper:** yerel Türkçe konuşma tanıma
- Teknik terimler, model numaraları ve özel adlar için hotword desteği
- Yazılı mikrofon kipinde transkript önce kutuya gelir; kullanıcı görmeden komut olarak çalıştırılmaz
- Eller serbest kipte yüksek riskli işlemler otomatik reddedilir

### Hafıza ve teknik servis kayıtları

- SQLite tabanlı konuşma geçmişi
- Açıkça kaydedilen kalıcı kullanıcı bilgileri
- Kaynak, güven ve önem puanına göre hafıza seçimi
- Eski değerleri kaybetmeyen değişiklik geçmişi
- Müşteri, cihaz, belirti, uygulanan işlemler ve sonuç içeren servis vakaları
- Türkçe karakterlerden etkilenmeyen geçmiş vaka araması
- Sonuç yazılmadan vaka kapatılmasını engelleyen veri bütünlüğü kuralları

### Bilgi tabanı — RAG

- Kod, teknik doküman ve notları yerel olarak indeksleme
- Kelime araması ile anlamsal aramayı birleştiren hibrit retrieval
- Ollama üzerinde yerel `bge-m3` embedding desteği
- Sonuçlarda dosya ve satır bilgisi
- `.env`, özel anahtarlar ve diğer gizli dosyaları indekslemeyen güvenlik filtresi
- Embedding kullanılamazsa kelime aramasına kontrollü fallback

### Görsel analiz

- Yerel kamera karesi işleme
- Yüz konumu ve hedef takibi
- İsteğe bağlı YOLO nesne algılama
- İsteğe bağlı OCR
- Açıkça etkinleştirilen yüz kimliği desteği
- Ham kamera karelerini kalıcı olarak saklamayan tasarım

### Güvenli araç kullanımı

J.A.R.V.I.S. işletim sistemine doğrudan sınırsız erişmez:

```text
Kullanıcı → Agent → Tool Router → Permission Manager → İşletim sistemi
```

- Araçlar `LOW`, `MEDIUM`, `HIGH` ve `CRITICAL` risk seviyelerine ayrılır
- Allowlist dışındaki terminal komutları reddedilir
- Kabuk zincirleme, serbest `sudo` ve kontrolsüz komut çalıştırma yoktur
- `.env`, `.ssh`, özel anahtarlar ve parola dosyaları erişim dışıdır
- Riskli işlemler açık kullanıcı onayı ister
- Risk sınıflandırması hata verirse işlem güvenli tarafta kalır
- Araç kararları redakte edilmiş JSONL denetim günlüğüne yazılır
- Web ve RAG içeriği talimat değil, güvenilmeyen veri olarak değerlendirilir

## Windows kurulumu

### Gereksinimler

- Windows 10 veya Windows 11, 64-bit
- Python 3.10 veya üzeri; önerilen sürüm Python 3.12
- Gerçek yerel yapay zekâ için Ollama
- Mikrofon ve kamera özellikleri için uyumlu donanım
- ElevenLabs kullanılacaksa API anahtarı ve Voice ID

Python kurulumu:

```powershell
winget install Python.Python.3.12
```

Ollama kurulumu ve modeller:

```powershell
winget install Ollama.Ollama
ollama pull qwen2.5:14b-instruct
ollama pull qwen2.5:7b-instruct
ollama pull bge-m3
```

### Kurulum adımları

1. GitHub sayfasında **Code → Download ZIP** seçeneğini kullanın.
2. ZIP dosyasını normal bir klasöre çıkartın.
3. `windows\Kur.cmd` dosyasına çift tıklayın.
4. Kurucu projeyi `%LOCALAPPDATA%\Programs\JARVIS` altına kurar.
5. Masaüstündeki **J.A.R.V.I.S.** simgesinden paneli başlatın.

Kurucu:

- Kendi Python sanal ortamını oluşturur
- Temel paketi, Edge TTS'yi ve faster-whisper'ı kurmayı dener
- Masaüstü ve Başlat menüsü kısayollarını oluşturur
- J.A.R.V.I.S. paketinin gerçekten açılabildiğini doğrular
- Kullanıcı hafızasını `%USERPROFILE%\.jarvis` altında ayrı tutar

Ayrıntılı anlatım: [Windows kurulum rehberi](docs/KURULUM-WINDOWS.md)

## Yapılandırma

Yerel ayarlar uygulama klasöründeki `.env` dosyasından okunur. API anahtarlarını
depoya, README'ye veya destek mesajlarına yazmayın.

Örnek üretim ayarları:

```env
JARVIS_PROFILE=windows-production
JARVIS_DATA_DIR=~/.jarvis

JARVIS_LLM_PROVIDER=ollama
JARVIS_OLLAMA_HOST=http://localhost:11434
JARVIS_OLLAMA_MODEL=qwen2.5:14b-instruct
JARVIS_OLLAMA_FALLBACK_MODEL=qwen2.5:7b-instruct
JARVIS_OLLAMA_NUM_CTX=8192

JARVIS_VOICE_ENABLED=true
JARVIS_TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=
ELEVENLABS_VOICE_ID=

JARVIS_STT_ENABLED=true
JARVIS_STT_MODEL=small

JARVIS_VISION_ENABLED=false
JARVIS_OBJECT_VISION_ENABLED=false
JARVIS_OCR_ENABLED=false
JARVIS_FACE_RECOGNITION_ENABLED=false
```

Hazır şablon: [`profiles/windows-production.env.example`](profiles/windows-production.env.example)

## Kullanım

Masaüstü simgesi önerilen kullanım yoludur. Terminalden çalıştırmak için:

```powershell
jarvis-panel
```

Metin tabanlı terminal arayüzü:

```powershell
jarvis
```

Kimlik tanıtma:

```powershell
jarvis-tanit --kur
```

Bilgi tabanına belge veya proje ekleme:

```powershell
jarvis-bilgi ekle C:\Belgeler\Teknik-Notlar
jarvis-bilgi ara "NVMe görünmüyorsa neyi kontrol etmeliyim?"
```

Ses yapılandırmasını kontrol etme:

```powershell
jarvis-ses --kontrol
```

## Geliştirme ve test

Linux veya Windows geliştirme ortamında:

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -e ".[dev]"
pytest -q
```

Mevcut doğrulama tabanı:

- 1021 otomatik test
- Python kaynak derleme kontrolü
- Windows kurulum ve başlatıcı regresyon testleri
- Paket/ZIP içinde sır bulunmadığını doğrulayan testler
- Panel, erişim jetonu, SSE, ses, mikrofon ve Vision API testleri

Donanıma bağlı mikrofon, kamera, GPU, Ollama ve ses sağlayıcıları gerçek hedef
sistemde ayrıca kabul testinden geçirilmelidir.

## Proje yapısı

```text
jarvis/
├── core/       Agent, durum makinesi, kişilik, niyet ve bağlam
├── llm/        Ollama, mock ve fallback sağlayıcıları
├── memory/     Hafıza ve servis vakaları
├── rag/        Belge indeksleme ve hibrit arama
├── security/   İzin yöneticisi ve audit kayıtları
├── tools/      Sistem, dosya, terminal, Git, hafıza ve uygulama araçları
├── voice/      ElevenLabs, Edge, Piper ve faster-whisper
├── vision/     Yüz, nesne, OCR ve kimlik analizi
├── internet/   Güvenli arama, sayfa getirme ve SSRF koruması
└── web/        Neural Core panel sunucusu ve SSE

windows/        Windows başlatıcısı ve kurulum kaynakları
profiles/       Lite, Windows geliştirme ve üretim ayar şablonları
scripts/        Paketleme, profil ve kabul testi araçları
tests/          Otomatik regresyon testleri
docs/           Mimari, donanım ve kullanım belgeleri
```

## Veri ve gizlilik

- API anahtarları yalnızca yerel `.env` dosyasında tutulmalıdır
- Hafıza, vakalar, bilgi tabanı ve loglar varsayılan olarak `~/.jarvis` içindedir
- Mikrofon çözümlemesi faster-whisper ile yerel yapılır
- Kamera kareleri analizden sonra saklanmaz
- Ollama ve embedding modelleri yerelde çalışır
- ElevenLabs ve Edge seçilirse seslendirilecek metin ilgili çevrimiçi hizmete gider
- Müşteri veya servis verilerini buluta göndermeden önce veri politikanızı belirleyin

## Mevcut sınırlamalar

- İlk üretim kurulumu ve donanım kabul testleri hedef Windows sisteminde yapılmalıdır
- Hazır, dijital imzalı Setup EXE henüz yayınlanmamıştır; kurulum `Kur.cmd` ile yapılır
- iPhone istemcisi ve telefon mikrofonu için HTTPS akışı tamamlanmamıştır
- Ayrı müşteri bilgisayarına bağlanan uzak teşhis ajanı henüz yoktur
- Teşhis playbook/karar ağacı geliştirmesi devam etmektedir
- Otomatik yedekleme, log rotation ve servis/watchdog henüz eklenmemiştir
- Windows SmartScreen için kod imzalama yapılmamıştır

## Yol haritası

- ✅ Güvenli çekirdek, durum makinesi ve araç katmanı
- ✅ Neural Core paneli ve Windows başlatıcısı
- ✅ SQLite hafıza ve servis vaka sistemi
- ✅ Hibrit RAG ve yerel embedding
- ✅ ElevenLabs, Edge, Piper ve faster-whisper entegrasyonları
- ✅ Yerel kamera, yüz, nesne ve OCR altyapısı
- 🔸 Temiz Windows donanım kabul testleri
- 🔸 Teşhis playbook ve karar ağacı
- 🔸 RAG panel yönetimi ve otomatik yeniden indeksleme
- 🔸 Otomatik yedekleme ve kurtarma
- 🔸 HTTPS üzerinden telefon/iPhone istemcisi
- 🔸 Uzak hedef makine teşhis ajanı
- 🔸 Proaktif bildirim ve ajanda

## Belgeler

- [Windows kurulumu](docs/KURULUM-WINDOWS.md)
- [Mimari](docs/ARCHITECTURE.md)
- [Bilgi tabanı](docs/BILGI-TABANI.md)
- [Ses sistemi](docs/SES.md)
- [Mikrofon](docs/MIKROFON.md)
- [Kamera](docs/KAMERA.md)
- [Model karşılaştırma](docs/MODEL-KARSILASTIRMA.md)
- [Gereksinim ve risk analizi](docs/REQUIREMENTS_ANALYSIS.md)

---

J.A.R.V.I.S. şu anda kişisel kullanım ve kontrollü teknik servis denemeleri için
geliştirilmektedir. Kritik veya yıkıcı sistem işlemlerinde insan doğrulaması her
zaman son karar mekanizmasıdır.
