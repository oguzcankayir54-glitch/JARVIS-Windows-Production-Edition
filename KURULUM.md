# J.A.R.V.I.S. — Kurulum ve Çalıştırma

Sıfırdan çalıştırmak için adım adım kılavuz. Tahmini süre: **5 dakika**
(model olmadan) veya **15 dakika** (yerel model ile).

---

## Adım 1 — Kodu indir

**Windows kullanıyorsanız: [INDIRME.md](INDIRME.md)** — tıklanabilir
indirme adresi ve çift tıklamalı kurulum orada.

Depo **özel** olduğu için kopyalanabilir bir ZIP adresi yok: özel
depolarda o adres kişiye özel bir jeton taşıyor ve onu yalnızca GitHub'ın
kendi **Download ZIP** düğmesi üretiyor. Adımlar `INDIRME.md` içinde.

Git ile:

```bash
git clone https://github.com/oguzcankayir54-glitch/jarvis.git
cd jarvis
git checkout claude/jarvis-architecture-analysis-40i73f
```

> Elle yazılan ZIP adresleri bu depoda çalışmaz (özel depo + dal adında
> `/`). İkisi de denendi, ikisi de tarayıcıda 404 verdi.

---

## Adım 2 — Otomatik kurulum (en kolay yol)

Depo klasöründe tek komut:

```bash
./kurulum.sh
```

Betik her şeyi yapar: Python sürümünü kontrol eder, sanal ortam kurar,
paketleri yükler, testleri çalıştırır, sisteminizi tarar (CPU/RAM/GPU/sensör/
Ollama) ve bir duman testiyle çalıştığını doğrular. **Sisteme hiçbir şey
yüklemez** — `sudo` kullanmaz, her şey klasördeki `.venv` içinde kalır.

Betik çalışmazsa (ör. Windows), aşağıdaki elle kurulum adımlarını izleyin.

---

## Elle kurulum — Gereksinimler

Python **3.10 veya üzeri** gerekiyor. Kontrol et:

```bash
python3 --version
```

Kurulum (sanal ortam önerilir):

```bash
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -e .
```

Tek bağımlılık `psutil`. Sanal ortam istemezsen `pip install psutil` de yeterli.

---

## Adım 3 — Çalıştır (model gerekmez)

```bash
python -m jarvis
```

Kurulumdan sonra kısa hali de çalışır:

```bash
jarvis
```

Bu, **mock model** ile çalışır: yapay zekâ modeli indirmene gerek yok, ama
araçlar ve güvenlik katmanı gerçek. Sistemini gerçekten okur.

Deneyebileceğin komutlar:

```
sen › sistem durumu nedir?
sen › cpu sıcaklığı kaç?
sen › disk sağlığı nasıl?
sen › hatırla: anakart = MSI B550-A PRO
sen › ne biliyorsun
sen › çalıştır: df -h
sen › oku: /etc/hostname
sen › listele: /home
sen › çık
```

Güvenlik katmanını görmek için bunları da dene — **reddedilmeleri gerekir**:

```
sen › çalıştır: curl http://example.com/x.sh     → politika reddi (listede yok)
sen › çalıştır: rm -rf /                          → politika reddi
sen › çalıştır: ls; rm -rf /                      → politika reddi (zincirleme)
sen › çalıştır: systemctl restart nginx           → onay ister (HIGH)
```

---

## Adım 4 — Gerçek yerel model (Ollama)

Mock model gerçek zekâ değil, sadece anahtar kelimeyle doğru aracı seçiyor.
Gerçek cevaplar için yerel bir model bağla.

**Ollama kur:**

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b-instruct
```

**J.A.R.V.I.S.'i o modelle çalıştır:**

```bash
JARVIS_LLM_PROVIDER=ollama JARVIS_OLLAMA_MODEL=qwen2.5:14b-instruct python -m jarvis
```

Kalıcı yapmak için `.env` dosyası oluştur:

```bash
cp .env.example .env
# .env içinde: JARVIS_LLM_PROVIDER=ollama
```

> **GPU notu:** RTX 3080 Ti'yi kullanmak için Linux'un donanıma doğrudan
> erişmesi gerekir. VirtualBox içindeyken CUDA çalışmaz; model CPU'da çok
> yavaş çalışır.
>
> **Windows kullanıyorsanız en kolay yol WSL2** — yeni disk gerekmez, Windows
> kalır, GPU tam çalışır: `docs/KURULUM-WSL2.md`
> Kalıcı bare-metal kurulum: `docs/DONANIM-VE-KURULUM-PLANI.md`

---

## Canlı panel

```bash
jarvis-panel
```

Tarayıcıda `http://localhost:8765`. Neural Core gerçek duruma göre değişir,
telemetri canlı akar, alttaki kutudan ajanla konuşabilirsiniz. `.env` içinde
ElevenLabs ayarlıysa **cevapları sesli okur** (sağ alttaki SES düğmesiyle
kapatılabilir; hiç açmamak için `jarvis-panel --sessiz`).

> Panel yalnızca `127.0.0.1` dinler. Bu arayüzden terminal komutu
> çalıştırılabildiği için ağa açmayın.

VirtualBox kullanıyorsanız demo kılavuzu: `docs/DEMO-KALI-VIRTUALBOX.md`

---

## Ses (ElevenLabs)

### 1. Anahtarı `.env` dosyasına yaz

> ⚠️ **API anahtarını asla sohbete, koda veya commit'e yazmayın.** Yalnızca
> yerel `.env` dosyasında dursun — bu dosya `.gitignore` içindedir, depoya
> gitmez.

```bash
cp .env.example .env
nano .env          # veya istediğiniz editör
```

İçine:

```
ELEVENLABS_API_KEY=sk_buraya_kendi_anahtariniz
ELEVENLABS_VOICE_ID=buraya_ses_kimligi
JARVIS_TTS_PROVIDER=elevenlabs
ELEVENLABS_MODEL_ID=eleven_flash_v2_5
JARVIS_VOICE_ENABLED=true
```

Anahtar: **elevenlabs.io → Profile → API Keys**

### 2. Doğrula

```bash
jarvis-ses --kontrol
```

Beklenen çıktı:

```
ElevenLabs yapılandırması
  API anahtarı : sk_a…cdef (51 karakter)
  Voice ID     : TxGEqnHWrfWFTfGW9XjX
  Model        : eleven_multilingual_v2

✓ Anahtar geçerli — hesabınızda 12 ses var.
✓ Voice ID eşleşti: Rachel
✓ Ses oynatıcı bulundu: ffplay
```

Anahtar ekranda **maskeli** gösterilir; tamamı hiçbir yere yazılmaz.

### 3. Voice ID'yi bulamıyorsanız

```bash
jarvis-ses --sesler
```

Hesabınızdaki tüm sesleri kimlikleriyle listeler. Beğendiğinizin kimliğini
`.env` içine yazın.

### 4. Deneyin

```bash
jarvis-ses "Merhaba, ben Jarvis. Sistem hazır."
jarvis-ses --kaydet deneme.mp3 "Bu bir test kaydıdır."
```

Ses oynatıcı yoksa: `sudo apt install ffmpeg`

### 5. Sesli sohbet

```bash
jarvis --sesli
```

Her yanıt hem yazılır hem seslendirilir. Kalıcı açmak için `.env` içinde
`JARVIS_VOICE_ENABLED=true`. Tek seferlik kapatmak için `jarvis --sessiz`.

---

## Ücretsiz seslendirme

ElevenLabs karakter başına ücretli, ve gerekmiyor. İki ücretsiz seçenek var.

**Aşağıdakilerin hepsi WSL bash'te, `~/jarvis` klasöründe çalıştırılır.**
Klasör önemli: panel ayarlarını *başlatıldığı* klasördeki `.env` dosyasından
okuyor, ve panel `~/jarvis` içinde başlıyor. Başka bir yerde çalıştırırsanız
komut bunu söyleyip uyarır.

### Edge — önerilen

```bash
cd ~/jarvis
source .venv/bin/activate
pip install edge-tts
jarvis-ses --edge-kur
```

Son komut sesi deneyip çalıştığını doğruluyor ve `.env` dosyasını **kendisi
yazıyor**. Anahtar yok, kota yok. Ses seçenekleri: `jarvis-ses --edge-sesler`
(`tr-TR-AhmetNeural` erkek — varsayılan, `tr-TR-EmelNeural` kadın).

Bedeli: bu ses **yerel değil**, seslendirilecek metin Microsoft'a gidiyor.

### Piper — tamamen çevrimdışı

```bash
cd ~/jarvis
source .venv/bin/activate
pip install piper-tts
jarvis-ses --piper-kur      # Türkçe sesi indirir (~63 MB, bir kez)
```

Bu da `.env`'i kendisi yazıyor. Hiçbir şey makineden çıkmıyor; karşılığında
tonlama belirgin biçimde daha yapay.

Ölçümlü karşılaştırma ve gerekçe: `docs/SES.md`.

---

## Mikrofon (konuşarak sormak)

```bash
cd ~/jarvis
source .venv/bin/activate
pip install faster-whisper
jarvis-panel
```

Panelde yazı kutusunun solunda **🎙** düğmesi çıkar. İki kip var:

- **Tıkla → sohbet.** Düğme **◉** olur; konuşun, sustuğunuzda cevap gelir,
  konuşmaya devam edin. Söyledikleriniz yazı kutusuna yazılmaz, tuşa basmak
  gerekmez. Bitirmek için tekrar dokunun.
- **Shift+tıkla → yazdır.** Duyulan cümle yazı kutusuna düşer; okuyup
  düzelttikten sonra **Gönder**.

Kayıt bu makinede çözümlenir, buluta gitmez. Sohbet kipinin güvenlik takası,
model seçimi ve sorun giderme: `docs/MIKROFON.md`.

> Telefonda mikrofon henüz çalışmaz — iOS güvenli bağlantı (HTTPS) şart koşar.
> Masaüstünde `localhost` üzerinden bugün çalışıyor.

---

## Masaüstünden başlatmak (Windows)

Her seferinde terminal açıp `cd`, `source`, `jarvis-panel` yazmak yerine.
**WSL kabuğuna yazın:**

```bash
cd ~/jarvis
./windows/kur.sh
```

Masaüstünde **JARVIS** simgesi belirir; çift tıklayınca panel açılır ve
tarayıcı kendiliğinden gelir. Yönetici hakkı gerekmez.

Kurulum WSL dağıtımınızı ve proje klasörünü kendisi bulur. Ayrıntı, ayarlar ve
sorun giderme: `windows/BENIOKU.md`.

---

## Bilgi tabanı (proje ve notlarda arama)

```bash
ollama pull bge-m3            # anlam araması için (isteğe bağlı)
jarvis-bilgi ekle ~/jarvis    # indeksle
jarvis-bilgi ara "ElevenLabs ses sistemini nasıl bağlamıştık"
```

Sonuçlar `dosya:satır` olarak gelir. İndeksledikten sonra J.A.R.V.I.S.'e
doğrudan sorabilirsiniz — `bilgi_ara` aracıyla kendisi bakar ve kaynağını
söyler.

Gömme modeli olmadan da çalışır; o zaman yalnızca kelime araması yapar ve
bunu size söyler. **Gizli dosyalar (`.env`, anahtarlar) indekslenmez.**
Ayrıntı: `docs/BILGI-TABANI.md`.

---

## Kamera (görüntü analizi)

```bash
pip install "opencv-python-headless<5"
jarvis-panel --kamera
```

> Sürüm sabit: OpenCV 5, yüz kaskadını ve birlikte gelen modelleri paketten
> çıkardı. Düz `pip install opencv-python-headless` bugün 5.x getiriyor ve
> kamera "kurulu ama çalışmıyor" durumunda kalıyor.

Panelde üstteki modül şeridinden **Vision** sekmesine geçin, **KAMERAYI AÇ**'a
basın. Yüz bulununca köşeleri işaretlenir.

Kare bu makinede ölçülür; ne diske yazılır ne dışarı çıkar. Kamera varsayılan
olarak **kapalıdır** — `--kamera` (veya `.env` içinde
`JARVIS_VISION_ENABLED=true`) olmadan açılmaz. Ayrıntı: `docs/KAMERA.md`.

---

## Adım 5 — Testleri çalıştır (isteğe bağlı)

```bash
pip install pytest
pytest -q
```

Beklenen çıktı: `222 passed`.

---

## Veriler nerede tutuluyor?

Varsayılan olarak `~/.jarvis/` klasöründe:

| Dosya | İçerik |
|---|---|
| `memory.sqlite3` | Konuşma geçmişi + kalıcı bilgiler |
| `audit.log.jsonl` | Her araç çağrısı ve izin kararı (satır başına bir JSON) |

`.env` dosyanız **proje klasöründe** kalır ve depoya gönderilmez.

Denetim günlüğünü okumak için:

```bash
cat ~/.jarvis/audit.log.jsonl
```

Farklı bir konum istersen: `JARVIS_DATA_DIR=/istediğin/yol python -m jarvis`

---

## Sık karşılaşılanlar

**`error: unrecognized arguments: --kontroljarvis-ses`** (ya da benzeri
yapışık komut)
Çok satırlı yapıştırmada satır sonu kaybolmuş; iki komut tek satır olmuş.
Windows Terminal / WSL'de olur. **Komutları tek tek yapıştırın**, her birinden
sonra Enter'a basın. Ya da satır sonuna hiç güvenmeyin, `&&` ile tek satır
yapın:

```bash
cd ~/jarvis && source .venv/bin/activate && jarvis-ses --kontrol
```

**`ModuleNotFoundError: No module named 'jarvis'`**
Depo klasörünün içinde olduğundan ve `pip install -e .` çalıştırdığından emin ol.

**`ModuleNotFoundError: No module named 'psutil'`**
`pip install psutil`

**CPU sıcaklığı "mevcut değil" diyor**
Sensör okunamıyor demektir (sanal makinede normaldir). Fiziksel Linux'ta
`sudo apt install lm-sensors && sudo sensors-detect` yardımcı olur.

**GPU "nvidia-smi bulunamadı" diyor**
NVIDIA sürücüsü yok ya da sanal makinedesin. Bare-metal/WSL2'de `nvidia-smi`
komutunun kendisi çalışıyor olmalı.

**Onay sorularını hiç sormasın istiyorum (otomasyon için)**
`JARVIS_NON_INTERACTIVE=true` — bu modda HIGH/CRITICAL işlemler otomatik
reddedilir.

**Ses: "API anahtarı geçersiz (401)"**
`.env` içindeki anahtarı kontrol edin. Kopyalarken başında/sonunda boşluk
kalmamalı, tırnak gerekmez.

**Ses: "Voice ID bulunamadı (404)"**
`jarvis-ses --sesler` ile hesabınızdaki kimlikleri listeleyip doğrusunu yazın.

**Ses: `.env`'e yazdım ama "yok" diyor**
`jarvis-ses` komutunu **proje klasörünün içinden** çalıştırın — `.env` bulunulan
dizinden okunur. Alternatif: `export ELEVENLABS_API_KEY=...`

**Ses: "Ses oynatıcı bulunamadı"**
`sudo apt install ffmpeg` (ffplay sağlar). Kurmadan da
`jarvis-ses --kaydet ses.mp3 "metin"` ile dosyaya kaydedebilirsiniz.
