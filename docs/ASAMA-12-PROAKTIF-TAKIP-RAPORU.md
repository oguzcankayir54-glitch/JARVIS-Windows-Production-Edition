# Aşama 12 — Proaktif Sistem Takibi Raporu

Tarih: 29 Ağustos 2026

## Sonuç

Aşama 11'in gerçek telemetry ve health check verileri üzerine config tabanlı,
gürültü kontrollü bir proaktif takip katmanı eklendi. Ölçülemeyen değerler için
bildirim üretilmez; takip sonucu Aşama 10 event bus üzerinden GUI/HUD'a ulaşır.

## İzlenen durumlar

- Yüksek ve kritik RAM kullanımı
- Yüksek ve kritik disk kullanımı
- GPU sıcaklığı
- VRAM kullanım oranı
- Ollama ve aktif model health sonucu
- Beklenen TTS'nin hazır olmaması
- Beklenen mikrofon/STT health sonucu
- `jarvis.error`, `llm.error`, `tool.error`, `voice.error` servis olayları
- Health probe'un kendisinin başarısız olması

GPU/VRAM alanları yalnız GPU gerçekten algılandığında değerlendirilir.
Mikrofon gibi doğrulanamayan `UNKNOWN` değerler bildirim üretmez.

## Gürültü önleme

Bir sorun için bildirim yalnız şu durumlarda üretilir:

1. Sorun ilk kez aktif olduğunda.
2. `warning` seviyesi `critical` seviyesine yükseldiğinde.
3. Sorun devam ederken yapılandırılmış cooldown süresi dolduğunda.

Sorunun geçtiği tek bir ölçüm recovery sayılmaz. Varsayılan olarak art arda iki
normal ölçüm gerekir; ardından bir kez `system.recovered` yayınlanır.

## Eventler

- `system.warning`
- `system.alert`
- `system.recovered`

Panel bu eventleri SSE üzerinden dinler ve kullanıcı bildirimi gösterir. Event
payload'ları ölçülen değer, eşik, birim ve hata tipi gibi sınırlı metadata taşır;
kullanıcı metni veya tool argümanı taşımaz.

## Merkezi config

- `JARVIS_MONITOR_ENABLED=true`
- `JARVIS_MONITOR_INTERVAL=15`
- `JARVIS_MONITOR_HEALTH_INTERVAL=60`
- `JARVIS_MONITOR_COOLDOWN=300`
- `JARVIS_MONITOR_RECOVERY_SAMPLES=2`
- `JARVIS_MONITOR_RAM_WARNING=85`
- `JARVIS_MONITOR_RAM_CRITICAL=95`
- `JARVIS_MONITOR_DISK_WARNING=90`
- `JARVIS_MONITOR_DISK_CRITICAL=97`
- `JARVIS_MONITOR_GPU_TEMP_WARNING=80`
- `JARVIS_MONITOR_GPU_TEMP_CRITICAL=90`
- `JARVIS_MONITOR_VRAM_WARNING=85`
- `JARVIS_MONITOR_VRAM_CRITICAL=95`

Yüzde eşikleri `0..100`, GPU sıcaklığı `0..150` aralığına alınır. Kritik eşik
uyarı eşiğinden düşük verildiyse güvenli biçimde uyarı eşiğine yükseltilir.

## Thread yaşam döngüsü

Telemetry, proactive health, reminder ve RAG arka plan thread'leri isimlendirilip
sunucu tarafından izlenir. Shutdown sırasında stop sinyali gönderilir, HTTP
sunucusu kapatılır ve thread'ler sınırlı süreyle join edilir. Monitor event
abonelikleri idempotent biçimde kaldırılır.

## Eklenen dosyalar

- `jarvis/diagnostics/monitor.py`
- `tests/test_monitor.py`
- `docs/ASAMA-12-PROAKTIF-TAKIP-RAPORU.md`

## Değiştirilen dosyalar

- `jarvis/config.py`
- `jarvis/web/server.py`
- `jarvis/web/cli.py`
- `docs/mockups/jarvis-panel.html`
- `.env.example`
- `profiles/windows-production.env.example`
- `tests/test_config.py`
- `README.md`

## Test sonuçları

- Monitor/config/event/health hedef grubu: `48 passed`
- Thread kapanışı ve monitor-panel grubu: `11 passed`
- Tam regresyon: `1132 passed, 6 skipped`
- Python `compileall`: başarılı
- `git diff --check`: başarılı

## Kalan riskler ve teknik borç

- Proaktif takip yalnız panel süreci çalışırken aktiftir; ayrı Windows servisi
  veya daemon kurulmamıştır.
- Bildirimler süreç içinde tutulur; kalıcı incident geçmişi henüz yoktur.
- GPU ölçümü mevcut `nvidia-smi` erişimine bağlıdır.
- Fiziksel mikrofon durumu tarayıcı izin sonucu olmadan kesin bilinemez.
- Otomatik düzeltme yapılmaz; monitor yalnız bildirir. Riskli servis restart
  işlemleri özellikle otomatikleştirilmemiştir.
