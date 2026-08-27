# J.A.R.V.I.S. 2.0 — ElevenLabs Ses Sistemi

J.A.R.V.I.S. 2.0.1'de **ana TTS motoru ElevenLabs**'tır. Piper ve Edge yalnızca
isteğe bağlı yedek sağlayıcı olarak tutulur; doğru ElevenLabs yapılandırmasında
otomatik olarak başka bir sese düşülmez.

## Neden ElevenLabs?

J.A.R.V.I.S. bir konuşma asistanıdır; bu nedenle varsayılan model
`eleven_flash_v2_5` olarak ayarlanmıştır. Bu profil düşük gecikmeli konuşma için
uygundur. Daha yüksek ifade gücü istenirse `.env` içinde `eleven_v3` seçilebilir;
ancak v3 daha ağır ve daha gecikmelidir.

## Kurulum

`.env` dosyanıza yalnızca kendi makinenizde şunları yazın:

```env
JARVIS_TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=BURAYA_KENDI_ANAHTARINIZ
ELEVENLABS_VOICE_ID=BURAYA_VOICE_ID
ELEVENLABS_MODEL_ID=eleven_flash_v2_5
ELEVENLABS_OUTPUT_FORMAT=mp3_44100_128
ELEVENLABS_LANGUAGE_CODE=tr
ELEVENLABS_STABILITY=0.50
ELEVENLABS_SIMILARITY_BOOST=0.75
ELEVENLABS_STYLE=0.0
ELEVENLABS_SPEAKER_BOOST=true
ELEVENLABS_SPEED=1.0
ELEVENLABS_TIMEOUT=30
ELEVENLABS_MAX_RETRIES=2
JARVIS_VOICE_ENABLED=true
```

API anahtarını kaynak koda yazmayın ve Git'e göndermeyin. `.env` zaten
`.gitignore` kapsamındadır.

## Voice ID bulma

```bash
jarvis-ses --sesler
```

Seçtiğiniz sesin ID'sini `ELEVENLABS_VOICE_ID` değerine koyun.

## Bağlantıyı doğrulama

```bash
jarvis-ses --kontrol
```

Bu komut anahtarı maskeli gösterir, seçili Voice ID'yi doğrular ve erişilebiliyorsa
kalan kotayı kontrol eder. Anahtar loglara yazılmaz.

## Ses testi

```bash
jarvis-ses "Sistemler hazır efendim."
```

Panel için:

```bash
jarvis-panel --ac
```

Panel, `tts_from_config()` üzerinden aynı ElevenLabs provider'ını kullanır; ayrı
bir API anahtarı veya tarayıcıya gömülü credential yoktur.

## Model seçimi

| Model | Kullanım |
|---|---|
| `eleven_flash_v2_5` | J.A.R.V.I.S. canlı sohbeti, düşük gecikme — varsayılan |
| `eleven_multilingual_v2` | Klasik kaliteli çok dilli TTS |
| `eleven_v3` | En yüksek ifade gücü; daha fazla gecikme |

`eleven_v3` kullanıldığında Similarity Boost ve Speaker Boost istek gövdesine
gönderilmez; provider bunu otomatik yönetir.

## Ses ayarları

- `ELEVENLABS_STABILITY`: 0–1. Düşük = daha değişken/ifade dolu, yüksek = daha sabit.
- `ELEVENLABS_SIMILARITY_BOOST`: 0–1. Referans sese yakınlık.
- `ELEVENLABS_STYLE`: 0–1. Genellikle 0 tutulması daha stabil ve hızlıdır.
- `ELEVENLABS_SPEAKER_BOOST`: sese benzerliği güçlendirir; küçük gecikme maliyeti vardır.
- `ELEVENLABS_SPEED`: 0.7–1.2. Varsayılan 1.0.

## Hata toleransı

429 ve geçici 5xx hatalarında provider kısa exponential backoff ile yeniden dener.
401, yanlış Voice ID ve bozuk istekler bekletilmeden anlaşılır Türkçe hata olarak
döner. Kota bitmesi ile geçersiz anahtar ayrıştırılmaya çalışılır.

## Yedek sağlayıcılar

ElevenLabs'ı özellikle kapatmak isterseniz:

```env
JARVIS_TTS_PROVIDER=piper
```

veya:

```env
JARVIS_TTS_PROVIDER=edge
```

Bunlar fallback'tir; J.A.R.V.I.S. 2.0.1'in ana ses motoru değildir.
