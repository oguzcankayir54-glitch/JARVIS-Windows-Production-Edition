# J.A.R.V.I.S. 2.0.1 — ElevenLabs Migration

Bu sürümde ana TTS sağlayıcısı ElevenLabs'tır.

## Kaynak kod gerçekliği

Bu repository içinde XTTS, PyQt veya PySide kaynakları yoktur. Bu nedenle
olmayan GUI/XTTS dosyaları değiştirilmedi. Ses katmanı merkezi
`jarvis.voice.tts.tts_from_config()` üzerinden ElevenLabs-first hale getirildi.
Ayrı bir PySide/PyQt masaüstü uygulaması varsa onun kaynakları bu provider'a
bağlanmak üzere ayrıca eklenmelidir.

## Yerel .env

API anahtarını kaynak koda veya bu ZIP'e koymayın. Proje kökündeki `.env`:

```env
JARVIS_TTS_PROVIDER=elevenlabs
ELEVENLABS_API_KEY=KENDI_API_KEYINIZ
ELEVENLABS_VOICE_ID=KENDI_VOICE_IDINIZ
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

## Doğrulama

```powershell
jarvis-ses --kontrol
jarvis-ses "Sistemler hazır efendim."
```

## Model profilleri

- `eleven_flash_v2_5`: gerçek zamanlı J.A.R.V.I.S. konuşması için varsayılan.
- `eleven_multilingual_v2`: klasik çok dilli kalite.
- `eleven_v3`: daha ifade gücü yüksek, fakat daha gecikmeli.

## Güvenlik

`ELEVENLABS_API_KEY` yalnız server-side Python katmanında okunur. Panel veya
istemci tarafı JavaScript'e gömülmez ve loglanmaz.
