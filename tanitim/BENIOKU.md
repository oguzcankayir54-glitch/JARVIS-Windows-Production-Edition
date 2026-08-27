# Tanıtım videosu

> Tek kural: hiçbir sahne canlandırma değil. Kayıt, çalışan panelin kendisi.

`JARVIS-tanitim.mp4` — 1920×1080, ~1 dakika 35 saniye, Türkçe anlatımlı
(`tr-TR-EmelNeural`), altında müzik yatağı.

---

## Neden bu şekilde yapıldı

Bir tanıtım videosunun en kolay yolu ekran görüntülerini animasyona
dökmektir. Bu proje boyunca tekrar tekrar geçerli olan kural burada da
geçerli: **ölçmediğini gösterme.**

Bu yüzden videodaki her şey gerçek:

| Görünen | Nereden geliyor |
|---|---|
| Açılış girişindeki satırlar | Panelin `meta` olayı — gerçek model adı, gerçek araç sayısı |
| Telemetri | Makinenin kendisi (psutil) |
| Soru–cevap | Gerçek dil modeli (Ollama) |
| Anlatım sesi | Projenin kendi seslendirme katmanı, `tr-TR-AhmetNeural` |
| Mikrofon turu | Gerçek Whisper çözümlemesi |

Anlatımın ayrı bir spikere okutulmaması bilinçli: **duyduğunuz ses, ürünün
gerçekten çıkardığı ses.** Stüdyo kaydı olsaydı tanıtım, ürünün yapamadığı
bir şeyi gösteriyor olurdu.

---

## Yeniden üretmek

Gereken: çalışan bir panel, `edge-tts`, `playwright`, `imageio-ffmpeg`.

```bash
# 1. Paneli başlatın (ayrı bir terminalde)
cd ~/jarvis && source .venv/bin/activate
jarvis-panel --port 8801

# 2. Anlatımı üretin (süreleri ölçüp zamanlama.json'a yazar)
python tanitim/anlatim_uret.py tanitim/cikti

# 3. Videoyu yakalayın
python tanitim/video_cek.py http://127.0.0.1:8801/ tanitim/cikti

# 4. Müzik yatağını üretin (isteğe bağlı)
python tanitim/muzik_uret.py 96 tanitim/cikti/muzik.wav

# 5. Ses ile birleştirin
python tanitim/birlestir.py tanitim/cikti \
    --muzik tanitim/cikti/muzik.wav
```

Üretilenler `tanitim/cikti/` altına yazılıyor ve depoya girmiyor.
Sahne süreleri `anlatim.py` içinde. Bir sahnenin süresi, o sahnenin
anlatım sesinin **gerçek uzunluğundan** hesaplanıyor — sabit sayılar
yazılsaydı ses ile görüntü kayardı.

---

## Sahneler

| # | Sahne | Ne gösteriyor |
|---|---|---|
| 1 | Giriş | ~10 saniyelik açılış; satırlar gerçek |
| 2 | Panel | Bağlanmış panel, canlı durum |
| 3 | Telemetri | İşlemci, bellek, disk, sıcaklık |
| 4 | Modüller | Dokuz sekme, her biri kendi gerçek durumu |
| 5 | Soru | Yazılan soru, gerçek modelden cevap |
| 6 | Mikrofon | Eller serbest sohbet |
| 7 | Güvenlik | Risk seviyeleri ve araç izinleri |
| 8 | Kapanış | Künye |

---

## Müzik

İstenen parça AC/DC — *Back In Black* idi. Telifli ticari bir kayıt:
indirilip bir videoya gömülemez. Bunun yerine `muzik_uret.py` özgün bir
enstrümantal üretiyor — mi minör, 94 vuruş, yani o parçanın tempo ve
tonalitesine yakın ama riff kendine ait.

**Lisanslı kopyanız varsa** tek bayrakla değişiyor:

```bash
python tanitim/birlestir.py tanitim/cikti --muzik ~/Muzik/back-in-black.mp3
```

Karışım iki aşamalı kısıyor: sabit −9 dB, artı **yan zincir sıkıştırma**
(anlatım konuşurken müzik geriye çekiliyor, susunca geri geliyor).
Seviye ölçülerek seçildi:

| ayar | boşlukta | konuşurken |
|---|---|---|
| −21 dB | %6 | %1 — neredeyse duyulmuyor |
| −14 dB | %14 | %3 |
| **−9 dB** | **%24** | **%5** ← seçilen |
| −7 dB | %30 | %6 |

Yüzdeler anlatım seviyesine göre. Daha kısık isterseniz `--muzik-db -14`.

---

## Bilinen sınırlar

- Kayıt Linux'ta, başsız bir tarayıcıda alındı. Windows'taki gerçek
  uygulama penceresi (tam ekran, kendi simgesi) aynı görünüyor ama kayıt
  ondan değil.
- Videodaki cevaplar `qwen2.5:3b` ile üretildi — küçük bir model.
  Türkçesi 14B'ye göre belirgin biçimde zayıf. Tanıtımı kendi makinenizde
  yeniden çekerseniz cevaplar daha iyi olur.
- Kayıt sırasında panelin kendi seslendirmesi kapatılıyor, yoksa anlatımın
  üstüne biniyor.
- Müziği üreten taraf onu **dinleyemiyor**. Sayısal olarak denetleniyor
  (tempo, kırpma, sessizlik, karışım oranları), ama "kulağa hoş geliyor mu"
  sorusunun cevabı dinleyene ait.
