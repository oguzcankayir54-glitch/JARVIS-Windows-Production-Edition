# JARVIS vNext — Güvenli Çekirdek Yükseltmesi

Bu paket `jarvis-main.zip` üzerine hazırlanmıştır. Görsel arayüz tasarımı, XTTS ve PyQt/PySide katmanları kapsam dışı bırakılmıştır.

## Değişiklikler

- Kişilik katmanı güçlendirildi:
  - soru / komut / bilgi verme / şaka / yalnızca seslenme ayrımı,
  - önceki bağlamı tekrar sormama,
  - teknik yanıtta sonuç → doğrulama → gerekçe akışı,
  - hata fark edildiğinde kısa ve açık öz-düzeltme,
  - argo/öfke karşısında stabil ve görev odaklı ton,
  - gereksiz kapanış ve gösterişli rol yapmanın engellenmesi.
- İlk-tur sistem notunun sonraki konuşma turlarına sızması düzeltildi.
- Konuşma geçmişi sınırlandı; persona ve dinamik sistem blokları korunuyor.
- Çok büyük tool çıktıları başı ve sonu korunarak kontrollü biçimde kısaltılıyor.
- LLM/Ollama hatalarında Agent artık state'i STANDBY'a döndürüyor ve kontrollü hata yanıtı üretiyor.
- Ollama tool-calling protokolü düzeltildi: aracı isteyen assistant mesajı, tool sonucu ile birlikte sonraki LLM turuna geri gönderiliyor.
- faster-whisper ayarları iyileştirildi:
  - beam search,
  - deterministic temperature=0,
  - ayarlanabilir VAD minimum sessizlik,
  - speech padding,
  - önceki transcript'e koşullanmanın varsayılan kapatılması.
- Hands-free web mikrofon VAD kalibrasyonu düzeltildi:
  - ilk ~1 saniyede konuşmayı yok saymıyor,
  - konuşma örnekleri zemin gürültüsü hesabına karışmıyor,
  - zemin seviyesi yavaş EMA ile ortam değişimine adapte oluyor.
- Yeni ayarlar:
  - JARVIS_STT_BEAM_SIZE (varsayılan 5)
  - JARVIS_STT_VAD_MIN_SILENCE_MS (varsayılan 350)
  - JARVIS_STT_VAD_SPEECH_PAD_MS (varsayılan 250)
  - JARVIS_STT_CONDITION_PREVIOUS (varsayılan false)
  - JARVIS_HISTORY_MAX_MESSAGES (varsayılan 24)
  - JARVIS_TOOL_RESULT_MAX_CHARS (varsayılan 12000)

## Doğrulama

- Çekirdek test paketi (Piper ve uzun web sunucu paketi hariç): 798 passed, 1 skipped.
- Mikrofon/web odaklı seçili entegrasyon testleri: 22 passed.
- Persona/owner/agent regresyon testleri: temiz.
- Python compileall: temiz.

Not: Piper ile ilgili mevcut iki ortam-bağımlı test bu çalışmanın kapsamına alınmadı; kullanıcı isteği doğrultusunda ses sağlayıcı tarafına müdahale edilmedi.

## 2.0.1 — ElevenLabs-first voice

- `JARVIS_TTS_PROVIDER` varsayılanı `elevenlabs` oldu.
- Sohbet için varsayılan model `eleven_flash_v2_5` oldu.
- `ELEVENLABS_OUTPUT_FORMAT`, dil, stability, similarity, style, speaker boost,
  timeout ve retry ayarları eklendi.
- Varsayılan çıktı `mp3_44100_128`.
- `eleven_v3` için desteklenmeyen similarity/speaker-boost alanları otomatik
  gönderilmiyor.
- 429 ve geçici 5xx yanıtlarına sınırlı exponential retry eklendi.
- Voice ID URL path'i encode ediliyor; output format doğrulanıyor.
- API anahtarı GUI/tarayıcı tarafına taşınmıyor.
