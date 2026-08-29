# Aşama 10 — Event Bus Raporu

Tarih: 29 Ağustos 2026

## Sonuç

J.A.R.V.I.S. içine bağımlılıksız, süreç içi ve thread-safe bir event bus
eklendi. Sistem message broker veya dağıtık servis mimarisine dönüştürülmedi.
Mevcut panel SSE `EventHub` yapısı korunarak çekirdek event bus'a köprülendi.

## Event sözleşmesi

Her event şu ortak alanları taşır:

- `id`: süreç içinde benzersiz event kimliği
- `name`: noktalı event adı
- `source`: üreten modül
- `timestamp`: gerçek üretim zamanı
- `payload`: olaya özel, hassas olmayan metadata

Desteklenen abonelik biçimleri:

- Tam ad: `tool.finished`
- Alan öneki: `tool.*`
- Tüm olaylar: `*`

Abonelik kaldırma callback'i idempotenttir. Aynı listener örtüşen birden fazla
pattern ile eşleşse bile event başına bir kez çağrılır. Listener istisnaları
structured logging ile kaydedilir ve publisher akışını bozmaz.

## Bağlanan olaylar

- `jarvis.started`, `jarvis.ready`, `jarvis.error`
- `state.changed`
- `llm.started`, `llm.finished`, `llm.error`
- `tool.started`, `tool.finished`, `tool.error`
- `memory.saved`, `memory.retrieved`
- `voice.input`, `voice.listening`, `voice.output`, `voice.finished`, `voice.error`

`system.warning`, `system.alert` ve gelecekteki event adları ek kod gerektirmeden
publish edilebilir. Proaktif sistem takibi uygulanmadığı için bu aşamada sahte
warning/alert üretilmez.

## Güvenlik ve performans

- Tool argümanları ve kullanıcı metni event payload'larına kopyalanmaz.
- Hata eventleri ham hata mesajı yerine yalnızca hata tipini taşır.
- Event history varsayılan olarak son 100 event ile sınırlıdır ve kalıcı log
  değildir.
- Teslim senkrondur; callback'ler kısa çalışmalıdır. Event bus ağır işi veya
  GUI thread yönetimini üstlenmez.
- Yeni üçüncü taraf bağımlılık eklenmedi.

## Dosyalar

Eklenen:

- `jarvis/core/events.py`
- `tests/test_events.py`
- `docs/ASAMA-10-EVENT-BUS-RAPORU.md`

Değiştirilen:

- `jarvis/core/agent.py`
- `jarvis/web/server.py`
- `README.md`

## Kalan sınırlar

- Eventler süreç içidir; uygulama yeniden başladığında history sıfırlanır.
- Ağır subscriber işi kendi kuyruğuna aktarılmalıdır.
- ToolManager'ın Agent dışından doğrudan kullanımı Agent eventlerini üretmez.
- Voice interruption/barge-in veya proaktif warning üretimi bu aşamanın
  kapsamında değildir.

## Test sonuçları

- Event bus ve entegrasyon testleri: `10 passed`
- Event bus + panel hedef grubu: `106 passed`
- Tam regresyon: `1111 passed, 6 skipped`
- Python `compileall`: başarılı
- `git diff --check`: başarılı

Atlanan testler mevcut donanım/harici servis kabul testleridir; Aşama 10 yeni
bir skip eklememiştir.
