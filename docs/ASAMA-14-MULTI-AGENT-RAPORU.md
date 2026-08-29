# AŞAMA 14 — Multi-Agent Raporu

## Sonuç

Aşama 14 tamamlandı. Mevcut tek-agent döngüsü korunarak aynı LLM örneğini
kullanan `CODER`, `SYSTEM` ve `RESEARCHER` uzman rolleri ile deterministik bir
Supervisor eklendi. Sistem opt-in'dir ve varsayılan kapalıdır.

## Önceki mimari

- Bütün intentler tek JARVİS persona ve tek Agent döngüsünde işleniyordu.
- IntentRouter ve ToolRouter görevleri zaten sınıflandırıyor ve araçları
  daraltıyordu.
- Agent adımı `max_steps`, LLM retry'ları mevcut provider ayarlarıyla sınırlıydı.
- Merkezi state, Event Bus, PermissionManager ve request trace hazırdı.

## Yeni mimari

`Kullanıcı -> IntentRouter -> Supervisor -> isteğe bağlı uzman rolü -> mevcut Agent döngüsü`

- `CODER`: Coding ve GitHub intentleri.
- `SYSTEM`: Sistem izleme, bilgisayar kontrolü ve terminal intentleri.
- `RESEARCHER`: Web araştırması ve yerel RAG intentleri.
- CHAT, hafıza, ses, ajanda ve diğer intentler normal JARVİS akışında kalır.
- Uzmanlar ayrı model yüklemez; Agent'ın mevcut Qwen/LLM provider nesnesini
  kullanır.
- Uzman rolü yalnızca o tur için sistem bağlamına eklenir ve sonraki turda
  temizlenir.

## Güvenlik ve sınırlar

- Delegasyon derinliği kod seviyesinde en fazla `1`'dir. Config'e daha yüksek
  değer verilmesi sınırı genişletmez.
- Uzman rolü başka bir uzmanı çağıramaz.
- Ayrı agent loop veya recursive planner oluşturulmadı.
- Tool listesi hâlâ IntentRouter + ToolRouter tarafından belirlenir.
- Bütün çağrılar mevcut ToolManager ve PermissionManager kapısından geçer.
- CODER rolünün açık terminal talebi olmadan shell aracını göremediği test edildi.
- Mevcut `JARVIS_MAX_AGENT_STEPS` ve provider retry limitleri korunur.

## Event ve gözlemlenebilirlik

- `supervisor.routing`
- `agent.delegated`
- `agent.started`
- `agent.finished`
- `agent.error`
- `supervisor.completed`

Panelin mevcut Event Bus -> SSE köprüsü bu eventleri ek bağlantı olmadan yayınlar.
Request trace kayıtlarına `specialist_role` ve `delegation_depth` eklendi. Panel
metadatası multi-agent açık/kapalı durumunu, aktif ve son rolü gösterir.

## Config

- `JARVIS_MULTI_AGENT_ENABLED=false`
- `JARVIS_MULTI_AGENT_MAX_DELEGATIONS=1`

Varsayılanın kapalı olması mevcut üretim davranışının doğrulama yapılmadan
değişmemesini sağlar. Etkinleştirme sonrası da aynı model kullanılır.

## Eklenen dosyalar

- `jarvis/core/multi_agent.py`
- `tests/test_multi_agent.py`

## Değiştirilen dosyalar

- `jarvis/core/agent.py`
- `jarvis/core/intent_router.py`
- `jarvis/core/observability.py`
- `jarvis/bootstrap.py`
- `jarvis/config.py`
- `jarvis/web/server.py`
- `.env.example`
- `profiles/windows-production.env.example`
- `tests/test_config.py`

## Testler

- Rol/intent eşlemesi ve normal sohbet fallback'i.
- Opt-in davranışı ve delegasyon sınırı.
- Aynı LLM nesnesinin kullanılması.
- Event sırası ve tek delegasyon.
- Uzman rol bağlamının tur sonunda temizlenmesi.
- Request trace rol/depth kaydı.
- Tool allowlist'in uzman tarafından genişletilememesi.
- Kontrollü LLM hatasında recursive delegasyon oluşmaması.
- Panel/SSE regresyonu: `119 passed`.
- Tam paket: `1149 passed, 6 skipped` (`139.01s`).
- `compileall` ve `git diff --check` başarılı.

## Kalan riskler ve teknik borç

- Gerçek Qwen 2.5:14B ile rol promptlarının cevap kalitesi henüz karşılaştırmalı
  kabul testinden geçirilmedi; otomatik testler deterministik mock provider kullanır.
- Supervisor şimdilik deterministik intent eşlemesidir. LLM tabanlı planner bilinçli
  olarak eklenmedi; mevcut aşamada ek maliyet ve döngü riski faydasından büyüktür.
- Uzmanlar paralel çalışmaz. Tek konuşma geçmişi ve tek model üzerinde sıralı
  çalışmak bağlam güvenliğini ve GUI stabilitesini korur.

## Önerilen doğrulama

Multi-agent'i önce test profilinde `JARVIS_MULTI_AGENT_ENABLED=true` ile açıp
CODER, SYSTEM ve RESEARCHER için gerçek Qwen cevapları karşılaştırılmalıdır.
Kalite ve gecikme kabul edilmeden üretim profilinin varsayılanı değiştirilmemelidir.
