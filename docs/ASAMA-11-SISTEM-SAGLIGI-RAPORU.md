# Aşama 11 — Sistem Sağlığı ve Komut Paneli Raporu

Tarih: 29 Ağustos 2026

## Sonuç

Mevcut Sağlık ve Komutlar sekmeleri kaldırılmadan gerçek health check verileri,
şeffaf sağlık puanı, platforma duyarlı bakım kataloğu ve güvenli komut yürütme
özellikleriyle geliştirildi.

## Ölçülen sağlık bileşenleri

- JARVİS Core ve merkezi state
- CPU, RAM ve disk/SMART
- Ollama erişimi ve yapılandırılmış modelin `/api/tags` içindeki varlığı
- GPU, CUDA ve VRAM
- Python sürümü ve aktif virtual environment
- `python -m pip check` bağımlılık sonucu
- STT ve TTS sağlayıcı hazır olma durumu
- Mikrofon doğrulanabilirliği
- Working Memory mesaj sayısı
- Long-Term Memory gerçek SQLite kayıt sayısı
- Vector/RAG backend belge ve parça sayısı
- Kayıtlı tool sayısı

Tarayıcı mikrofonu sunucu makinesinde güvenilir biçimde doğrulanamadığı için
izin verilene kadar `UNKNOWN` gösterilir; `READY` uydurulmaz ve sağlık puanına
katılmaz.

## Sağlık puanı

Kategoriler: Core, LLM, GPU, Voice, Memory, Tools ve Dependencies.

- `ready`: 100
- `warning`: 50
- `critical` / `unavailable`: 0
- `unknown`: puan hesabı dışında

Kategori puanları bilinen gerçek kontrollerin aritmetik ortalamasıdır. Genel
puan, ölçülebilen kategori puanlarının ortalamasıdır. Gerekli bir bileşenin
kritik olması genel durumu doğrudan `CRITICAL` yapar.

- 85–100: `OPERATIONAL`
- 50–84: `DEGRADED`
- 0–49 veya gerekli bileşen hatası: `CRITICAL`

## Komut merkezi güvenliği

- Katalog Windows/Linux platformuna göre üretilir.
- HTTP API yalnızca sabit katalog kimliği kabul eder; serbest shell metni
  kabul etmez.
- Komutlar `shell=False` ve sabit `argv` ile çalıştırılır.
- stdout/stderr 20.000 karakterle, çalışma süresi komuta özel timeout ile
  sınırlıdır.
- `sudo`, servis başlatma/yeniden başlatma, JARVİS başlatma ve `tail -f` gibi
  uzun veya riskli komutlarda yalnızca Copy bulunur; Run bulunmaz.
- Son return code, stdout, stderr, süre ve zaman sonucu panel belleğinde tutulur.
- Çalıştırmalar Aşama 10 event bus üzerinden `tool.started`, `tool.finished`
  veya `tool.error` olayı üretir.

## Panel değişiklikleri

- Sağlık sekmesine `puan / 100`, durum ve `REFRESH HEALTH` butonu eklendi.
- Komut satırlarına Copy; güvenli komutlara ayrıca Run butonu eklendi.
- Sonuç alanında SUCCESS/FAILED, exit code, süre, stdout ve stderr gösterilir.
- `/health` minimal ve tokensız liveness probe olarak korundu.
- Ayrıntılı `/system-health`, `/health/refresh`, `/maintenance-commands` ve
  `/maintenance/run` uçları panel erişim kontrolünün arkasındadır.

## Eklenen dosyalar

- `jarvis/diagnostics/health.py`
- `jarvis/core/maintenance_commands.py`
- `tests/test_health_panel.py`
- `docs/ASAMA-11-SISTEM-SAGLIGI-RAPORU.md`

## Değiştirilen dosyalar

- `jarvis/web/server.py`
- `docs/mockups/jarvis-panel.html`
- `jarvis/memory/store.py`
- `tests/test_web.py`
- `tests/test_command_guide.py`
- `tests/test_memory.py`
- `README.md`

## Test sonuçları

- Hızlı health/memory/command grubu: `20 passed`
- Health/command/panel hedef grubu: `110 passed`
- Tam regresyon: `1123 passed, 6 skipped`
- Python `compileall`: başarılı
- `git diff --check`: başarılı

## Kalan riskler ve teknik borç

- Health refresh senkrondur; Ollama ve `pip check` zaman sınırlarıyla çalışsa
  da yavaş makinede birkaç saniye sürebilir. Tarayıcı fetch'i asenkrondur ve
  GUI çizim döngüsünü bloklamaz.
- Mikrofonun fiziksel hazır oluşu tarayıcı izin sonucu alınmadan bilinemez.
- CUDA kontrolü Torch import maliyeti taşır; rapor 15 saniye önbelleklenir.
- Health threshold değerlerinin config'e taşınması Aşama 12 proaktif takip
  kapsamında ele alınmalıdır.
- Komut sonuçları süreç içidir ve yeniden başlatmada silinir; denetim için
  event/audit kalıcılığı ayrıca tasarlanabilir.
