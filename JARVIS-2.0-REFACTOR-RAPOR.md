# J.A.R.V.I.S. 2.0 — Refactor Raporu

## Sürüm

- Paket sürümü: **2.0.0**
- Ana model varsayılanı: **Qwen 2.5 14B / Ollama**
- Refactor yaklaşımı: mevcut çalışan katmanları koruyup çekirdek yönlendirme, bağlam, hafıza ve cevap üretimini ayrıştırma

## Tamamlanan çekirdek katmanlar

1. Core Identity / Personality / Assistant Rules ayrımı
2. Yapılandırılmış Intent Router
3. Context Manager ve bağlam bütçesi
4. Conversation History / Long-Term Memory ayrımı ve ilgili hafıza seçimi
5. Response Engine ve internal hata/araç adı sızıntısı filtreleri
6. Intent tabanlı Tool Router
7. Permission katmanı ile zorunlu güvenlik entegrasyonu
8. Training Mode ve Developer Mode state yönetimi
9. Qwen 2.5 14B varsayılanı ve performans/context ayarları
10. Read-only Git araçları: status, log, diff, remote
11. Request-level observability, redaction ve güvenli loglama

## Kritik davranışlar

- Normal CHAT mesajlarında gereksiz RAG/tool çağrısı yapılmaz.
- `RAG ne?` açıklama sorusu CHAT olarak değerlendirilir; RAG veri tabanı sorgusu değildir.
- Doküman/PDF/proje bilgi soruları RAG_QUERY olarak yönlendirilir.
- Kullanıcıya ait kalıcı bilgiler Memory katmanına, doküman/kod bilgileri RAG katmanına ayrılır.
- Tüm Memory verisi her tur modele gönderilmez; yalnız ilgili kayıtlar seçilir.
- HIGH/CRITICAL işlemler PermissionManager katmanını atlayamaz.
- Stack trace, internal tool adı, API key/token/password gibi ayrıntılar kullanıcı cevabına/loga doğrudan sızdırılmaz.

## Doğrulama durumu

- Python `compileall`: başarılı.
- JARVIS 2.0 yeni çekirdek katmanlarını kapsayan kritik test grubu: **159 passed**.
- Sürüm/packaging metadata değişikliğinden sonra seçili regresyon: **58 passed**.
- Geniş pytest koşusu çalışma ortamının zaman sınırına kadar yaklaşık %83 ilerledi ve bu noktaya kadar failure üretmedi.
- Daha önce tespit edilen iki Piper baseline problemi bu Core Architecture Refactor kapsamının dışında tutuldu; XTTS/PyQt/PySide katmanlarına dokunulmadı.

## Önemli yeni modüller

- `jarvis/core/core_identity.py`
- `jarvis/core/personality.py`
- `jarvis/core/assistant_rules.py`
- `jarvis/core/intent_router.py`
- `jarvis/core/context_manager.py`
- `jarvis/core/response_engine.py`
- `jarvis/core/tool_router.py`
- `jarvis/core/observability.py`
- `jarvis/tools/git_tools.py`

## Güvenli yükseltme notu

Üretim/aktif kurulum üzerine doğrudan kopyalamadan önce mevcut kurulumun yedeğini alın. `.env` dosyanızı paketin dışındaki güvenli kopyadan geri koyun; gerçek API anahtarları bu dağıtım paketine dahil edilmemiştir.
