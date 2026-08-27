# JARVIS Linux Dev/Test Lite — Doğrulama

- Python `compileall`: PASS
- Config/Agent bootstrap (mock, TTS off, STT off, web off): PASS
- Canlı panel HTTP health: PASS (`ok=true`, `state=standby`)
- Piper odaklı regresyon: 36 passed, 1 skipped, 0 failed
- Geniş pytest: çalışma ortamı süre sınırına kadar %87 ilerledi, 0 failure görüldü
- Paket içinde `.env`, API key veya kullanıcı verisi: YOK

Bu paket düşük donanımlı Linux geliştirme/test makinesi içindir. Üretim Neural Core 27B yerine varsayılan mock kullanır; isteğe bağlı mini AI profili resmi `qwen3.5:0.8b` modelini kullanır.
