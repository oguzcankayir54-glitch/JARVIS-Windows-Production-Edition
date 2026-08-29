# Aşama 0–3 İlk Teslimat Raporu

Tarih: 29 Ağustos 2026

## Kapsam

Bu teslimat yalnızca proje analizi, çekirdek kararlılığı, merkezi durum
yönetimi ve çalışma belleğini kapsar. Long-Term Memory, ses mimarisi, event
bus, sağlık paneli, proaktif takip, vision ve multi-agent kapsam dışıdır.

## Değişiklik öncesi mimari

- `Agent`, LLM–tool döngüsünü yönetiyor ve durum geçişlerini doğrudan
  `StateMachine` üzerinde yapıyordu.
- `StateMachine` tek bir enum değeri ve listener listesinden oluşuyordu.
  Eşzamanlı erişim koruması, snapshot, geçiş revizyonu ve unsubscribe yoktu.
- Bir listener istisnası state geçişini çağıran çekirdek akışına yayılabiliyordu.
- Beklenmeyen ve yerel olarak ele alınmayan bir tur hatası, merkezi durumu
  `LISTENING`, `THINKING` veya `ANALYZING` konumunda bırakabiliyordu.
- Aktif konuşma bağlamı doğrudan `Agent.history` listesinde tutuluyordu.
  Context bütçesi vardı ancak kısa süreli belleğin ayrı bir sahibi ve güvenli
  snapshot/istatistik API'si yoktu.
- SQLite `MemoryStore`, kalıcı mesajları ve uzun dönem bilgileri zaten ayrı
  tutuyordu; bu ayrım korunması gereken çalışan davranıştı.

## Değişiklik sonrası mimari

- `Agent.ask`, tüm turu yeniden girişli bir kilitle seri hale getirir. GUI,
  ses veya API çağrılarının aynı oturum geçmişine mesajları iç içe yazması
  engellenir.
- Tur hangi beklenmeyen istisnayla biterse bitsin merkezi state `STANDBY`
  durumuna geri alınır. İstisna yutulmaz; yalnızca state kurtarılır.
- Agent adım sınırı `1..32` aralığına alınmıştır. Varsayılan 6 değişmemiştir.
- `StateMachine` kilitli ve atomiktir. `StateSnapshot`, önceki/mevcut state,
  revizyon, zaman, neden ve ayrıntıları tek tutarlı görünümde sunar.
- Listener hataları structured Python logging üzerinden kaydedilir ve state
  sahibini bozamaz. `subscribe` geriye uyumludur ve unsubscribe callback'i
  döndürür.
- `WorkingMemory`, bir oturumun süreç içi mesajlarının merkezi sahibidir.
  Güvenli snapshot, gerçek istatistik ve yalnızca geçici konuşmayı temizleme
  API'leri sunar.
- `Agent.history` uyumluluk özelliği korunmuştur. Mevcut context manager,
  testler ve sağlayıcılar yeniden yazılmadan `WorkingMemory` üzerinden çalışır.
- SQLite kalıcı hafıza ve mevcut context pruning/retrieval politikası
  değiştirilmemiştir.

## Mimari kararlar

1. Yeni bağımlılık eklenmedi; yalnızca Python standart kütüphanesi kullanıldı.
2. Event bus eklenmedi. Bu Aşama 10 kapsamıdır ve ilk teslimat sınırını aşardı.
3. Working memory ile Long-Term Memory ayrıldı. Bu teslimat yeni kalıcı veri
   şeması veya otomatik bilgi çıkarımı eklemez.
4. State listener sözleşmesindeki `(old, new)` imzası korunarak GUI/HUD geriye
   uyumluluğu sağlandı.
5. Beklenmeyen çekirdek hataları sessizce yutulmadı; çağırana yayılırken state
   deterministik biçimde kurtarılır.
6. Qwen 2.5:14B seçimi, kişilik, ses, GUI ve güvenlik/izin katmanı değiştirilmedi.

## Değiştirilen dosyalar

- `jarvis/core/state.py`: atomik state, snapshot, metadata, unsubscribe ve
  listener hata izolasyonu.
- `jarvis/core/agent.py`: sınırlı planner adımı, seri tur yürütme, state
  recovery ve merkezi working-memory entegrasyonu.
- `tests/test_agent.py`: state ve çekirdek recovery regresyon testleri.

## Eklenen dosyalar

- `jarvis/memory/working.py`: süreç içi çalışma belleği.
- `tests/test_working_memory.py`: snapshot, istatistik ve temizleme testleri.
- `docs/ASAMA-0-3-ILK-TESLIM-RAPORU.md`: bu rapor.

Çalışma ağacında bu teslimattan önce bulunan XTTS/ses değişiklikleri bu
teslimatın parçası değildir ve korunmuştur.

## Testler ve sonuçlar

- Çekirdek/state/context/working-memory smoke grubu: `40 passed`
- Bellek, context sızıntısı ve panel entegrasyonu: `180 passed`
- Tam regresyon: `1101 passed, 6 skipped`
- `git diff --check`: başarılı

Atlanan 6 test, gerçek donanım veya harici servis bulunmasına bağlı mevcut
kabul testleridir; yeni bir skip eklenmemiştir.

## Bulunan ve düzeltilen buglar

1. Hatalı state listener çekirdek geçişini bozabiliyordu. Listener hatası artık
   loglanıyor ve diğer listener/state akışı devam ediyor.
2. Intent routing gibi beklenmeyen bir istisna agent state'ini takılı
   bırakabiliyordu. Tur sonu recovery bunu `STANDBY` durumuna getiriyor.
3. Aynı Agent üzerinde eşzamanlı iki tur konuşma geçmişini iç içe
   geçirebiliyordu. Tur kilidi bunu seri hale getiriyor.
4. `max_agent_steps=0` cevap döngüsünü tamamen devre dışı bırakabiliyor,
   aşırı büyük değerler ise gereksiz uzun agent döngüsü oluşturabiliyordu.
   Sınır artık `1..32`.
5. Çalışma belleğinin salt okunur gözlem API'si yoktu. Snapshot ve stats ile
   GUI/diagnostic tüketicileri canlı listeyi değiştirmeden okuyabilir.

## Kalan riskler

- Tek Agent üzerindeki uzun LLM/tool turu diğer çağrıları sırada bekletir. Bu,
  geçmiş bütünlüğü için bilinçli bir seçimdir; iptal/barge-in Aşama 9'da ayrıca
  tasarlanmalıdır.
- Listener'lar çağıran thread üzerinde çalışır. Ağır listener yazılmamalıdır;
  event bus aşamasında teslim modeli ayrıca ele alınmalıdır.
- `Agent.history` geriye uyumluluk için canlı liste görünümü sunar. Yeni GUI ve
  diagnostic kodu doğrudan bu listeyi değil `working_memory.snapshot()`
  metodunu kullanmalıdır.
- State geçişleri henüz izin verilen geçiş grafiğiyle kısıtlanmıyor. Mevcut
  davranışı kırmamak için bu teslimatta katı geçiş tablosu eklenmedi.

## Teknik borçlar

- Agent içindeki dinamik system-block yenilemeleri ortak, isimli bir API'ye
  taşınabilir; şu anda eski kodla uyumluluk için list comprehensions kullanır.
- State reason alanları mevcut bütün geçişlere henüz eklenmedi; alan hazırdır
  fakat eski çağrılar boş nedenle çalışır.
- Çalışma belleği için oturum özeti/compaction yoktur. Bu, kalıcı hafızaya
  otomatik geçiş anlamına gelmeden ayrıca tasarlanmalıdır.

## Bir sonraki önerilen aşama

Bu teslimat kullanıcı tarafından doğrulandıktan sonra yalnızca planlanan bir
sonraki aşamaya geçilmelidir. Long-Term Memory veya Aşama 9–14 özelliklerine
otomatik geçilmemelidir. En güvenli sonraki adım, mevcut faz tanımındaki Aşama
4'ün gereksinimlerini netleştirip aynı küçük-değişiklik/test döngüsüyle ele
almaktır.
