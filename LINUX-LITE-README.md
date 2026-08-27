# JARVIS Linux Dev/Test Edition

Bu paket düşük sistemli Linux laptopta JARVIS'in panelini, çekirdek akışını ve kod değişikliklerini test etmek içindir.

## Varsayılan: Hafif geliştirme
- LLM: Ollama `qwen3.5:2b-q4_K_M` (gerçek hafif model)
- TTS: Piper ile yerel; Edge TTS de yedek olarak kurulu
- STT: faster-whisper `tiny`, CPU/int8
- Kamera: OpenCV ile açık
- Web: kapalı
- RAG embedding: kapalı
- Panel ve gerçek Linux sistem telemetrisi: açık
- Veri: yalnız proje içindeki `.jarvis-lite-data`

Kurulum ayrıca pytest ve Windows ikon doğrulaması için Pillow paketini kurar.
Türkçe Piper modeli ilk kurulumda `.jarvis-lite-data/sesler` içine indirilir.

## Kurulum
```bash
chmod +x install-lite.sh
./install-lite.sh
./run-panel-lite.sh
```
Tarayıcı: http://127.0.0.1:8765

## İsteğe bağlı Mini AI
```bash
./install-lite.sh --mini-ai
# veya daha sonra
./use-mini-ai.sh
./run-panel-lite.sh
```
Mini model: `qwen3.5:0.8b` (~1 GB Ollama model dosyası).

## Tekrar hafif moda dön
```bash
./use-mock.sh
```

## Not
Bu sürüm üretim makinesindeki 27B Neural Core'un yerini almaz. Ama panel/UI, router, tool zinciri, persona ve Linux telemetrisini düşük donanımda geliştirmek için izole bir çalışma alanıdır.
