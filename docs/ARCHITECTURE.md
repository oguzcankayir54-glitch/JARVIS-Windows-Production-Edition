# J.A.R.V.I.S. — Mimari Analiz ve Fizibilite Raporu

> Durum: **Analiz / Mimari onayı bekleniyor.** Bu doküman kod içermez.
> Amaç: Projeyi eleştirmek, eksikleri bulmak, donanımı hesaplamak ve
> onaylanabilir bir V1 mimarisi önermek.

Bu rapor seni memnun etmek için değil, projeyi **gerçekten çalışır** hale
getirmek için yazıldı. Bazı hedeflerin bugünkü donanımla ya da genel olarak
gerçekçi değil; bunları açıkça işaretledim ve her eleştirinin yanına
uygulanabilir bir alternatif koydum.

---

## 0. Tek Cümlelik Özet

Projenin **%80'i tamamen gerçekçi ve değerli**; ama üç noktada beklentin
gerçeklikle çarpışıyor: **(1)** VirtualBox üzerinde RTX 3080 Ti ile ciddi AI
hesabı yapmak mümkün değil, **(2)** telefon kamerasından anakart model/soket
tanıma "Iron Man" seviyesinde güvenilir olmayacak, **(3)** "her şeyi yapan"
tek bir sistemi baştan kurmaya çalışmak projenin en büyük başarısızlık
riskidir. Doğru yol: **dar ama sağlam bir V1**, hibrit (yerel + bulut) mimari
ve modüler bir çekirdek.

---

## 1. Proje Gerçekçi mi?

**Kısmen — ama parçalara ayrılırsa evet.**

| Yetenek | Gerçekçilik | Not |
|---|---|---|
| Sesli iletişim (STT→LLM→TTS) | ✅ Yüksek | Olgun teknoloji, ElevenLabs + Whisper çalışır |
| Doğal dil / reasoning | ✅ Yüksek | Hibrit (yerel + bulut LLM) ile |
| Sistem bilgisi / donanım okuma (sıcaklık, disk, SMART) | ✅ Yüksek | Linux araçlarıyla kolay |
| Terminal / dosya / uygulama kontrolü (izin katmanıyla) | ✅ Yüksek | Güvenlik katmanı şart |
| RAG teknik bilgi tabanı | ✅ Yüksek | Standart mimari |
| Hafıza (konuşma, vaka, ajanda) | ✅ Yüksek | SQLite + vektör DB |
| Ajanda / proaktif bildirim | ✅ Yüksek | Event-driven |
| iPhone mikrofon/hoparlör/ses | ✅ Orta-Yüksek | Custom app + WebRTC ile |
| Görsel analiz — **genel** ("bu bir anakart") | 🟡 Orta | Bulut vision ile iyi, yerel ile idare eder |
| Görsel analiz — **tam model/soket/hata LED'i tanıma** | 🔴 Düşük | Güvenilir değil. Aşağıda detaylı. |
| Arıza teşhis motoru (teknisyen gibi) | 🟡 Orta | Saf LLM yetmez; hibrit motor gerekir |
| "Sürekli dinleyen" wake word | 🟡 Orta | iOS'ta arka plan kısıtları ciddi engel |
| Akıllı gözlük / AR | 🟡 Uzun vade | V1 için değil, soyutlama ile hazırlanır |

**Sonuç:** Proje bir "hafta sonu projesi" değil; bu **1–2 yıllık ciddi bir
mühendislik yolculuğu.** Ama modüler kurarsan her ay çalışan bir şeyin olur.

---

## 2. En Büyük Teknik Zorluklar (Öncelik Sırasıyla)

1. **Kapsam (scope) yönetimi.** Bu projenin bir numaralı riski teknoloji
   değil, **her şeyi aynı anda yapmaya çalışmak.** 26 yetenek var; 3'ünü
   mükemmel yapmak, 26'sını yarım yapmaktan iyidir.
2. **VirtualBox + GPU.** Mevcut kurulumun AI hesabı için **kullanılamaz**
   (§6). Bu çözülmeden yerel model konusu havada kalır.
3. **Görsel donanım tanıma güvenilirliği.** En çok heyecanlandığın özellik,
   en az güvenilir olanı (§9).
4. **Ses gecikmesi (latency).** Doğal his için tüm zincirin streaming olması
   gerekir; her adım gecikme ekler (§19).
5. **Arıza teşhisinin güvenilirliği.** LLM "halüsinasyon" yapar; teknik
   serviste yanlış teşhis pahalıdır. Yapılandırılmış motor şart (§20).
6. **iOS arka plan kısıtları.** Apple, sürekli mikrofon dinleme ve arka plan
   ağ bağlantısını agresif şekilde kısıtlar (§16, §5).
7. **Güvenlik.** LLM'e sistem erişimi vermek = kendine bir "içeriden tehdit"
   yaratmak. İzin katmanı opsiyonel değil (§12).

---

## 3–5. Donanım Yeterliliği: RTX 3080 Ti · 5800X · 32 GB

> **Doğrulanmış donanım (22.08.2026 güncellemesi).** Önceki sürümde
> 5900X / RTX 3080 10 GB / 24 GB yazıyordu; gerçek yapılandırma aşağıdadır.
> GPU farkı önemli: **3080 Ti = 12 GB**, 3080'in 10 GB'ı değil.

| Bileşen | Model | Not |
|---|---|---|
| CPU | **AMD Ryzen 7 5800X** | 8 çekirdek / 16 iş parçacığı, Zen 3 |
| GPU | **Zotac RTX 3080 Ti** | **12 GB GDDR6X**, GA102 |
| RAM | **32 GB** | Sistem toplamı |

### RTX 3080 Ti — 12 GB Bir Eşiği Aşıyor
GPU'nun gücü işlemcide değil, **VRAM'inde** ve bu hâlâ en sıkı kısıtın —
ama 12 GB, 10 GB'dan anlamlı biçimde daha rahat:

- **12 GB VRAM.** VirtualBox'taki 256 MB "video belleği" ile **hiçbir
  alakası yoktur** — o emüle edilmiş 2D masaüstü belleğidir, CUDA'da
  kullanılmaz. Bu ikisini asla karıştırma.
- **Kritik kazanım: 14B modeller artık rahat sığıyor.** 10 GB'da 14B
  "sıkışık, başka hiçbir şeye yer yok" durumundaydı; 12 GB'da ~3 GB boşluk
  kalıyor. Günlük model 7B değil **14B** olabilir.

**12 GB VRAM'e gerçekçi olarak sığanlar:**

| Görev | Gerçekçi seçim | VRAM |
|---|---|---|
| Yerel LLM (günlük) | **Qwen2.5 14B (Q4_K_M)** | ~9.0 GB |
| Yerel LLM (hafif) | Qwen2.5 7B / Llama 3.1 8B (Q4) | ~4.7–4.9 GB |
| STT | faster-whisper `large-v3` (int8) | ~2–3 GB |
| Yerel Vision | Qwen2-VL-7B / MiniCPM-V (Q4) | ~6–8 GB |
| Embedding | bge-m3 / e5 | <1 GB |

**Neyin aynı anda çalışabildiği (asıl mesele bu):**

| Kombinasyon | Toplam | Durum |
|---|---|---|
| 7B LLM + Whisper large-v3 | ~7.7 GB | ✅ Rahat — sesli asistan için ideal |
| 14B LLM tek başına | ~9.0 GB | ✅ Rahat |
| 14B LLM + Whisper | ~12 GB | 🔴 Sınırda/taşar |
| 14B + Whisper + Vision | ~18 GB | ❌ Sığmaz |

**Sonuç değişmiyor ama yumuşuyor:** Hepsini aynı anda çalıştıramazsın, yani
**hibrit mimari hâlâ zorunlu.** Ama artık iki net kullanım profilin var:
- **Sesli mod:** 7B + Whisper birlikte, GPU'da rahat.
- **Derin analiz modu:** 14B tek başına, STT/vision o an buluta veya sıraya.

Model router'ın işi tam olarak bu geçişi yönetmek.

### 32 GB RAM — Rahat
- 32 GB, planladığımız 24 GB'dan fazla. Vektör DB, embedding, uygulama
  katmanı ve model yükleme tamponları için bol alan var.
- **CPU+GPU hibrit inference** (llama.cpp katman offload) mümkün ama
  **yavaştır** — CPU'ya taşan her katman token/sn'yi düşürür. Sesli, gerçek
  zamanlı kullanım için modeli tamamen VRAM'e sığdır; taşırma. 12 GB ile
  14B'de buna zaten gerek kalmıyor.
- **5800X (8 çekirdek / 16 iş parçacığı)** — embedding, ses ön-işleme ve RAG
  için fazlasıyla yeterli. 5900X'e göre 4 çekirdek az ama bu iş yükünde
  darboğaz değil; asıl yük GPU'da.

**Karar:** Donanım, doğru kurulumla iyi bir V1 için **yeterli ve önceki
varsayımdan bir tık daha iyi.** Tek gerçek engel yazılım tarafında:
**VirtualBox.**

---

## 6. VirtualBox Problemi (Kritik — Önce Bunu Çöz)

**Net cevap: VirtualBox üzerinde RTX 3080 Ti'yi CUDA/AI için kullanamazsın.**

- VirtualBox **NVIDIA CUDA'yı guest'e geçirmez.** Sunduğu grafik (VBoxVGA,
  VMSVGA) emüle edilmiş bir adaptördür; `nvidia-smi` guest içinde GPU'yu
  göremez, CUDA çalışmaz.
- VirtualBox'ta **pratik bir PCIe passthrough yoktur.** (Deneysel/kararsız
  "PCI passthrough" özelliği modern NVIDIA GPU'larla çalışmaz.)
- 256 MB, gerçek 12 GB VRAM ile ilgisizdir.

### Seçeneklerin Karşılaştırması

| Yöntem | GPU/CUDA | Zorluk | Öneri |
|---|---|---|---|
| Yöntem | GPU/CUDA | Sensörler | Maliyet | Durum |
|---|---|---|---|---|
| **VirtualBox** | ❌ Yok | ❌ Yok | — | Yalnızca demo |
| **WSL2 (Windows üzerinde)** | ✅ Tam | ❌ Yok | Sıfır | ⭐ **SEÇİLEN YOL** |
| **Bare-metal Linux** | ✅ Tam (en hızlı) | ✅ Var | Yeni SSD + kurulum | İleride değerlendirilecek |
| **KVM/QEMU + VFIO** | ✅ Tam, host GPU'yu kaybeder | ✅ Var | Yüksek karmaşıklık | Gereksiz |

### Karar: WSL2 (22.08.2026)

Başlangıçta bare-metal Linux öneriliyordu. Kullanıcının makinesinde **Windows
zaten kurulu** olduğu ortaya çıkınca karar WSL2 lehine değişti:

- **CUDA çalışır.** NVIDIA, WSL2'de CUDA'yı resmen destekler; GPU, Windows
  sürücüsü üzerinden gelir ve 12 GB VRAM tam kullanılır.
- **Maliyet sıfır.** Yeni disk yok, bölümleme yok, veri kaybı riski yok.
- **Windows kalır.** Teknik servis işi için gereken üretici araçları ve BIOS
  yazılımları erişilebilir kalıyor; yeniden başlatma gerekmiyor.
- **Kod değişmiyor.** Proje Linux üzerine yazıldı; WSL2 Linux.
- **Kurulum ~30 dakika**, bare-metal'de yarım gün.

**Bilerek kabul edilen kayıp:** WSL2 donanım sensörlerini vermez — CPU
sıcaklığı ve fiziksel disk SMART verisi okunamaz (`nvidia-smi` istisnadır,
çalışır). Bu, VirtualBox'ta da yoktu; yani gerileme değil, mevcut durumun
üstüne GPU eklemek. Sensörler gerçekten gerekli çıkarsa bare-metal seçeneği
açık kalıyor — ama bu karar artık tahminle değil, **canlı kullanım
deneyimiyle** verilecek.

> **WSL2'de en kritik kural:** WSL içine NVIDIA sürücüsü kurulmaz. GPU
> Windows'taki sürücüden gelir; içeride ayrıca sürücü kurmak çalışan
> kurulumu bozar.

**Aksiyon:** VirtualBox yalnızca demo/gözlem için. Geliştirme ve gerçek
kullanım **WSL2** üzerinde (`docs/KURULUM-WSL2.md`).

---

## 7. Önerilen Linux Mimarisi

- **Dağıtım:** Ubuntu 22.04/24.04 LTS (NVIDIA sürücü + CUDA toolkit desteği
  en sorunsuz olan).
- **NVIDIA yığını:** Proprietary driver + CUDA 12.x + cuDNN.
- **İzolasyon:** Servisleri **Docker Compose** ile ayır (LLM sunucusu,
  vektör DB, uygulama API'si, Redis). GPU için `nvidia-container-toolkit`.
- **Süreç yönetimi:** systemd veya Docker restart policy; proaktif izleme
  servisi için ayrı bir long-running process.
- **Neden konteyner:** §21'deki modüler yapıyla birebir uyumlu; her modülü
  bağımsız güncelleyip test edebilirsin.

---

## 8. Önerilen LLM Seçenekleri

**Prensip: Tek model değil, görev-bazlı yönlendirme (model router).**

**Yerel (RTX 3080 Ti, 12 GB) — düşük gecikmeli / gizli veri için:**
- **Qwen2.5 14B Instruct** (Q4_K_M) günlük sürücü; hafif/sesli mod için
  **Qwen2.5 7B** veya **Llama 3.1 8B**.
  Türkçe için Qwen2.5 ve Llama 3.1 makul; küçük modeller Türkçe'de İngilizce
  kadar iyi değil — bunu test et.
- Çalıştırma: başlangıçta **Ollama** (kolay), üretim/paralel istek için
  **llama.cpp server** veya tek kullanıcı senaryosunda yeterli.

**Bulut — ağır reasoning / karmaşık teşhis / en iyi Türkçe için:**
- Büyük reasoning gerektiğinde bir bulut LLM'e (frontier model) çağrı yap.
  Hassas veriyi yerelde tut, genel/karmaşık soruları buluta gönder.

**Neden hibrit:** 12 GB VRAM ile yerel bir model "iyi" olur ama frontier
bulut modellerin karmaşık teşhis kalitesine ulaşamaz. İkisini birleştir.

**Servis motoru karşılaştırması:**

| Araç | Ne zaman |
|---|---|
| **Ollama** | ⭐ Başlangıç, geliştirme, tek kullanıcı — en kolay |
| **llama.cpp** | İnce kontrol, GGUF quant, CPU offload esnekliği |
| **vLLM** | Yüksek throughput / çok kullanıcı — sende **aşırı**, 10 GB'a sığması zor |
| **TGI** | vLLM benzeri, kurumsal — gereksiz |
| **Transformers** | Deney/fine-tune, üretim servisi için değil |

**Öneri:** V1 = **Ollama (yerel) + bir bulut LLM API'si (router ile).**

---

## 9. Önerilen Vision Seçenekleri — ve Dürüst Uyarı

**Burada beklentini düşürmem gerekiyor.** "Kamerayı anakarta tut, JARVIS
tam modeli, soketi, VRM'i, hata LED'ini okusun" senaryosu bugünkü
teknolojiyle **güvenilir çalışmaz.** Nedenleri:

- Anakart üstündeki model yazısı küçük, açılı, parlama/ışık altında; OCR
  hataları yüksek.
- Aynı görünümlü onlarca kart var; model varyantlarını görüntüden ayırmak
  insan uzman için bile zor.
- Vision modelleri **kendinden emin ama yanlış** cevap verir (halüsinasyon).
  Teknik serviste yanlış model bilgisi tehlikelidir.

**Gerçekçi kapsam:**
- ✅ "Bu bir ATX anakart", "bu bir GPU", "bu RAM slotu", "bu 24-pin güç
  konnektörü" gibi **genel bileşen tanıma** → iyi çalışır.
- 🟡 Görünür bir **model/etiket yazısını OCR ile okuma** → ancak net,
  yakın, düz çekilmiş fotoğrafta.
- 🔴 Fotoğraftan **kesin model/varyant/soket çıkarımı** → güvenilmez.
  Bunun yerine: kullanıcıya "etikete/model yazısına yakın çek" dedir,
  OCR ile metni al, sonra o metni **RAG + web arama** ile doğrula.

**Model seçimi:**

| Seçenek | Kalite | Not |
|---|---|---|
| **Bulut vision (frontier multimodal)** | ⭐ En iyi | OCR + akıl yürütme çok üstün; V1 için bunu kullan |
| **Qwen2-VL 7B (yerel, Q4)** | Orta | GPU'da yer kaplar, LLM ile çakışır |
| **MiniCPM-V (yerel)** | Orta | Hafif, idare eder |

**Öneri:** Vision'ı **V1'de buluta ver** (kalite + VRAM tasarrufu).
Gizlilik gerektiren görüntüler için sonradan yerel bir vision modeli ekle.
Ve **JARVIS'e "emin değilim" dedirt** — yanlış kesinlikten iyidir.

---

## 10. Önerilen Speech-to-Text (STT)

| Seçenek | Gecikme | Doğruluk | Türkçe | Donanım | Maliyet |
|---|---|---|---|---|---|
| **faster-whisper large-v3 (yerel, GPU)** | Orta-düşük | Yüksek | İyi | ~2–3 GB VRAM | Ücretsiz (elektrik) |
| **whisper.cpp (yerel, CPU/GPU)** | Orta | Yüksek | İyi | Esnek | Ücretsiz |
| **Deepgram / bulut streaming STT** | ⭐ Çok düşük | Yüksek | Değişken | Yok | Kullanım başı |
| **OpenAI/ElevenLabs STT (bulut)** | Düşük | Yüksek | İyi | Yok | Kullanım başı |

**Değerlendirme:**
- Türkçe + gizlilik + maliyetsizlik istiyorsan → **faster-whisper large-v3
  (yerel).** Ama GPU'yu LLM ile paylaşması gerekir.
- En düşük gecikme + streaming istiyorsan → **bulut streaming STT.**

**Öneri:** V1 = **faster-whisper (yerel)** başla; gecikme çok yüksek gelirse
sesli mod için bulut streaming STT'ye geç. VAD (voice activity detection)
ekle ki sürekli değil, konuşma bittiğinde işlesin.

---

## 11. ElevenLabs Entegrasyonu

- ElevenLabs TTS kalitesi mükemmel; Türkçe destekli seslerini seç.
- **Streaming API kullan** (chunk chunk ses) — yoksa cümle bitmeden ses
  başlamaz, gecikme hissedilir.
- **Mimari not:** TTS'i doğrudan iPhone'a değil, **JARVIS Server üzerinden**
  akıt. Böylece API key sunucuda kalır (telefonda gömülü key = güvenlik
  açığı). Server ElevenLabs'ten alır → iPhone'a WebRTC/WebSocket ile iletir.
- **Maliyet uyarısı:** ElevenLabs karakter başı ücretlidir; çok konuşan bir
  asistan aylık faturayı şişirebilir. Kısa cevaplar (§15 "gereksiz
  konuşmayan" kişiliği) hem UX hem maliyet için iyi.
- **Yedek plan:** Gizli/offline durumlar veya maliyet için yerel bir TTS
  (ör. Piper) fallback olarak eklenebilir.

---

## 12–15. iPhone Mimarisi + Kamera/Mikrofon Aktarımı + Protokol Karşılaştırması

### Protokol Karşılaştırması

| Protokol | Ses (çift yönlü) | Kamera/Video | Gecikme | Not |
|---|---|---|---|---|
| **WebRTC** | ⭐ Mükemmel | ⭐ Mükemmel | En düşük | Gerçek zamanlı ses+video için tasarlandı; NAT geçişi, jitter buffer dahili |
| **WebSocket** | 🟡 İyi (chunk) | 🟡 İdare eder | Düşük-orta | Kontrol mesajları + ses chunk'ları için ideal; basit |
| **gRPC** | 🟡 Streaming var | 🟡 | Düşük | Sunucu-sunucu için güçlü; mobil gerçek-zamanlı sesde WebRTC kadar iyi değil |
| **HTTP (REST)** | ❌ | ❌ | Yüksek | Sadece komut/kontrol, canlı akış için değil |
| **Raw UDP** | Teorik | Teorik | En düşük | Kendin RTP/jitter/NAT yazacaksın = WebRTC'i yeniden icat etmek |
| **Raw TCP** | ❌ | ❌ | Head-of-line blocking | Canlı ses için kötü |

**Öneri:**
- **Canlı ses (çift yönlü) ve kamera akışı → WebRTC.** Tekerleği yeniden
  icat etme; NAT, jitter, kayıp paket işini WebRTC hallediyor.
- **Kontrol/komut/durum mesajları → WebSocket** (JSON). Basit ve yeterli.
- **Pratik V1 kısayolu:** WebRTC ilk sürümde karmaşıksa, MVP'yi
  **WebSocket + ses chunk'ları (push-to-talk)** ile yap; canlı düşük
  gecikme kritikleşince WebRTC'e geç. Böylece iOS tarafında erken takılmazsın.

### iOS Tarafı
- **Swift + SwiftUI** (arayüz), **AVFoundation** (mikrofon/hoparlör/kamera).
- Apple Developer Program gerekir (**~$99/yıl**) — cihaza gerçek uygulama
  yüklemek ve arka plan yetenekleri için pratikte şart.
- **Gerçekçilik uyarısı:** iOS **arka planda sürekli mikrofon dinlemeyi ve
  uzun süreli arka plan ağ bağlantısını kısıtlar.** "Uygulama kapalıyken
  bile sürekli dinleyen JARVIS" App Store kurallarına ve OS kısıtlarına
  takılır. V1'de **uygulama açıkken / push-to-talk** ile başla.

### Güvenli Eşleşme (Pairing)
- İlk eşleşmede telefon ↔ server arası **QR kod ile token değişimi**
  (server bir kez QR gösterir, telefon okur).
- Sonrasında **mutual TLS veya imzalı token (JWT)** ile her bağlantıda
  kimlik doğrula. Yerel ağda çalışıyorsa self-signed sertifika + pinning.
- API key'ler **asla** telefonda gömülü olmasın; hepsi server'da.

---

## 16. Agent Mimarisi

**Saf "prompt at, cevap al" yetmez.** J.A.R.V.I.S. bir **agent loop**
olmalı:

```
Kullanıcı girdisi (ses/metin/görüntü)
  → Orchestrator (context toplar: hafıza + RAG + sistem durumu)
  → LLM (plan yapar, tool çağırır)
  → Tool Manager (izin katmanından geçer, çalıştırır)
  → Sonuç LLM'e döner (gözlem)
  → LLM devam eder / cevabı üretir
  → TTS → ses
```

- **Orchestrator** merkezde: hangi modeli (router), hangi tool'u, hangi
  hafızayı çağıracağına karar verir.
- Başlangıçta bir agent framework (ör. yapılandırılmış tool-calling)
  kullanabilirsin ama **çekirdeği kendi kodunda tut** — framework'e fazla
  bağımlı olma; abstraction'ını koru (§21).

---

## 17. Tool Calling Mimarisi + Güvenli Soyutlama

**Evet — LLM'in işletim sistemine doğrudan/sınırsız erişimi kesinlikle
olmamalı.** İstediğin katman doğru:

```
LLM
 → Tool Manager (tool'ları şema ile tanımlar, girdi doğrular)
 → Permission Layer (risk sınıfı + onay + audit log)
 → OS / donanım / dosya sistemi
```

- Her tool **açık şema** ile tanımlı (ad, parametre, risk sınıfı).
- LLM ham shell'e erişmez; **whitelist edilmiş, doğrulanmış tool'lara**
  erişir. `run_terminal_command` bile bir **allowlist + tehlikeli komut
  filtresi** arkasında olmalı.
- Her tool çağrısı **audit log**'a yazılır (ne, ne zaman, kim onayladı).

---

## 18. Memory Mimarisi

| Katman | Ne saklar | DB önerisi |
|---|---|---|
| **Conversation Memory** | Son konuşmalar, kısa vadeli bağlam | Redis (ephemeral) + SQLite (kalıcı özet) |
| **User Memory** | Tercihler, kişisel profil | SQLite / Postgres |
| **Technical Knowledge** | Teknik bilgi, dokümanlar | **Vektör DB** (RAG) |
| **Service Case Memory** | Servis vakaları, teşhis geçmişi | Postgres (yapısal) + vektör DB (arama) |
| **Task / Calendar Memory** | Görev, randevu, hatırlatma | SQLite / Postgres |

**Karar:**
- **V1: SQLite** (tek dosya, sıfır kurulum) + **bir vektör DB** (RAG için).
- **Büyüyünce: PostgreSQL + pgvector** (yapısal + vektör tek yerde) +
  **Redis** (ephemeral konuşma bağlamı, pub/sub, proaktif event kuyruğu).
- Redis'i erken zorlamana gerek yok; SQLite ile başla.

---

## 19. RAG Mimarisi

```
Doküman (PDF/manual/web/not)
  → Yükleme & parse (PDF metin + tablo çıkarımı)
  → Chunking (semantik, ~500–1000 token, %10–20 overlap)
  → Embedding
  → Vektör DB'ye yaz (metadata: kaynak, sayfa, cihaz tipi)

Sorgu → embed → benzerlik ara (+ metadata filtre) → top-k → LLM'e context
```

- **Embedding modeli:** `bge-m3` veya çok dilli `e5` — **Türkçe destekli
  ve çok dilli** olması önemli (dokümanların Türkçe/İngilizce karışık).
- **Chunking:** Sabit boyut değil; başlık/bölüm sınırlarına saygılı
  **semantik chunking.** Teknik manuel'lerde tablo ve adım listelerini
  bölme.
- **Reranking** ekle (retrieval sonrası) — teknik doğruluk için değerli.

**Vektör DB karşılaştırması:**

| DB | Başlangıç | Uzun vade | Not |
|---|---|---|---|
| **FAISS** | ✅ Hızlı | 🟡 | Kütüphane, sunucu değil; metadata/filtre zayıf |
| **Chroma** | ⭐ En kolay | 🟡 | Prototip için harika, ölçekte sınırlı |
| **Qdrant** | 🟡 | ⭐ En iyi | Filtreleme, kalıcılık, prod-ready |
| **pgvector** | 🟡 | ✅ | Zaten Postgres kullanıyorsan tek DB avantajı |

**Öneri:** **V1'de Chroma** ile başla (hız), **6–12 ay içinde Qdrant'a**
(veya Postgres'e geçtiysen pgvector'a) taşı. Soyutlama koy ki geçiş kolay
olsun.

---

## 20. Teknik Servis Teşhis Motoru

**En kritik mimari kararlardan biri. Saf LLM YETMEZ.** LLM tek başına
tutarsız ve halüsinasyonludur; teknik teşhiste bu pahalıya patlar.

**Önerilen: Hibrit teşhis motoru.**

```
Belirti → LLM (belirtiyi yapılandırılmış forma çevirir)
        → Decision Tree / Rule Engine (bilinen arıza ağaçları)
        → Veri toplama tool'ları (SMART, sıcaklık, loglar)
        → Hipotez listesi + olasılık (basit skorlama/gevşek Bayesian)
        → Bir sonraki en bilgilendirici test'i öner
        → Sonuç → hipotezleri güncelle → döngü
        → RAG (üretici doküman / troubleshooting guide) ile destekle
```

- **State machine + karar ağacı** çekirdek olsun (deterministik, izlenebilir).
- **LLM'i "sınırlı ve doğrulanan" bir akıl yürütücü** olarak kullan, tek
  karar verici olarak değil.
- **Bayesian tam gerekmez** başta; her hipoteze basit olasılık ağırlığı
  yeterli. İleride vaka verisi biriktikçe gerçek Bayesian'a geçebilirsin.
- Bilinen arıza senaryolarını (ör. "açılıyor görüntü yok") **yapılandırılmış
  playbook**'lar olarak sakla; LLM bunları çalıştırsın.

**Özet:** Saf LLM ❌ → **Karar ağacı + rule engine + LLM + RAG** ✅.

---

## 21. Güvenlik Mimarisi

Risk sınıflandırması doğru; şöyle uygula:

| Sınıf | Örnek | Politika |
|---|---|---|
| **LOW** | Sistem bilgisi, sıcaklık okuma | Otomatik, log |
| **MEDIUM** | Dosya değiştirme, uygulama açma | Otomatik + log + geri alınabilir |
| **HIGH** | Sistem ayarı, servis durdurma | **Kullanıcı onayı** |
| **CRITICAL** | Disk format, partition sil, BIOS flash | **Açık, iki-adımlı onay + doğrulama cümlesi** |

**Permission Architecture:**
- Her tool bir risk sınıfıyla **kayıtlı**; LLM sınıfı değiştiremez.
- CRITICAL için: JARVIS ne yapacağını açıkça söyler → kullanıcı sözlü/yazılı
  **açık onay** verir (ör. belirli bir cümleyi tekrarlar) → ancak sonra
  çalışır.
- **Dry-run** modu: yıkıcı işlemler önce simüle edilip kullanıcıya gösterilsin.
- **Audit log** her şey için; geri alma (undo) mümkün olan yerde.
- **Sandbox:** terminal komutları allowlist + tehlikeli-pattern reddi
  (`rm -rf /`, `dd`, `mkfs`, `> /dev/sda` vb. asla otomatik değil).

---

## 22. Ajanda Sistemi

- **V1: Yerel takvim DB** (SQLite tablosu: görev, tarih, tür, hatırlatma,
  durum). CRUD + hatırlatma yeterli.
- **Proaktif entegrasyon:** Görevler §23'teki event sistemine bağlanır
  (yaklaşan teslim → bildirim).
- **İleride:** iOS EventKit (iPhone Calendar) / Google Calendar API ile
  **tek yönlü sonra çift yönlü** senkron. Bir **CalendarProvider
  abstraction** koy ki backend değişse çekirdek değişmesin.

---

## 23. Proaktif Sistem

**Evet, event-driven mimari gerekli — ama gürültü kontrolüyle.**

```
Sensörler (sıcaklık, SMART, disk doluluk, ajanda) 
  → periyodik/eşik-tetikli izleme servisi
  → Event bus (Redis pub/sub veya basit kuyruk)
  → Kural + eşik + debounce/cooldown
  → Önem filtresi (sadece anlamlı olanlar)
  → Bildirim (iPhone push / sesli uyarı)
```

- **Debounce/cooldown zorunlu:** aynı uyarıyı sürekli tekrarlama. "CPU 85°C"
  bir kez bildir, düşene kadar sus.
- **Önem eşiği:** sadece eyleme dönük uyarılar (SSD sağlığı düşüyor, disk
  %95 dolu, teslim yarın). Gereksiz bildirim asistanı sinir bozucu yapar.
- Başlangıçta **basit bir long-running izleme servisi** yeter; tam event
  bus'ı büyüyünce ekle.

---

## 24. Öğrenme: Fine-tuning Gerekli mi?

**Net cevap: Hayır, V1 (ve muhtemelen V2) için fine-tuning gerekmez.**

Senin tarif ettiğin döngü **zaten doğru:**
```
geri bildirim → vaka kaydı → değerlendirme → bilgi tabanı → gelecekte retrieval
```
Bu **RAG + memory + tools** ile "öğrenme" — ve senin ihtiyacın olan tam bu.
Modelin ağırlıklarını değiştirmeden, **yeni bilgiyi bilgi tabanına yazarak**
sistem "öğrenir." Kontrollü, geri alınabilir, güvenli.

- **Fine-tuning ne zaman?** Sadece **davranış/stil/persona** tutarlılığı için
  (JARVIS'in konuşma tarzı), **bilgi eklemek için değil.** Bilgi = RAG.
- **LoRA/QLoRA ne zaman?** İleride, elinde yüzlerce gerçek servis vakası
  birikince ve model belirli bir **format/tarz**ı öğrenmesi gerekirse
  QLoRA (RTX 3080 Ti'de 7B–14B için mümkün). Ama bu bir **optimizasyon**, temel
  değil.
- **Uyarı:** Kontrolsüz otomatik öğrenme (kullanıcı dedi → ağırlık değişti)
  **istemediğin gibi tehlikelidir** — haklısın, onu yapma.

**Karar:** RAG + memory + tools yeterli. Fine-tuning'i yol haritasının
**çok ilerisine** koy.

---

## 25. Yerel + Bulut Hibrit + Model Router

**Yaklaşımın doğru. Model router gerekli.**

| Görev | Nereye |
|---|---|
| Basit komut / kısa cevap | Yerel LLM |
| Hassas/gizli veri | Yerel LLM |
| Büyük reasoning / karmaşık teşhis | Bulut LLM |
| Güncel araştırma | Web arama tool'u |
| Ses (TTS) | ElevenLabs |
| STT | Yerel Whisper (veya bulut streaming) |
| Vision (V1) | Bulut multimodal |

- **Router** basit başlasın: görev tipi + gizlilik bayrağı + karmaşıklık
  tahminine göre yönlendir. Makine öğrenmesiyle karmaşıklaştırma; kural
  tabanlı router V1 için yeter.
- **Gizlilik kuralı:** kişisel/sistem verisi içeren istekler **asla otomatik
  buluta gitmesin** — kullanıcı bayrağı olmadan yerelde kalsın.

---

## 26. Gecikme (Latency) — Gerçekçi Hedefler

**Tüm zincir streaming olmalı**, yoksa doğal hissetmez:

```
Konuşma bitişi → STT (streaming) → LLM (streaming) → TTS (streaming) → ses
```

**Gerçekçi hedefler (yerel + iyi kurulum):**
- İlk ses çıkışına kadar (time-to-first-audio): **~800 ms – 1.5 sn** iyi.
- Tam bulut zincir + ağ: **1.5–3 sn** olabilir.
- **<500 ms "insan gibi anlık"** hedefi bu donanım/mimari ile **gerçekçi
  değil** — bunu baştan kabul et.

**Gecikmeyi düşürme teknikleri:**
- Streaming her katmanda (özellikle LLM ilk token + ElevenLabs streaming).
- VAD ile konuşma bitişini hızlı algıla.
- LLM cevabının **ilk cümlesini** TTS'e hemen gönder, gerisi akarken.
- Kısa cevap kişiliği (§28) hem gecikme hem doğallık için iyi.

---

## 27. Akıllı Gözlük Yol Haritası

**V1'e koyma — ama mimariyi ona hazır tut.** Doğru içgüdü: çekirdek
değişmeden istemci değişmeli.

**Soyutlama:** İstemciyi (iPhone / gözlük) çekirdekten **Client Abstraction**
ile ayır:
```
Herhangi bir istemci (iPhone, gözlük, web)
  → standart I/O sözleşmesi: {audio_in, video_in, audio_out, display_out, events}
  → JARVIS Core (istemcinin ne olduğunu bilmez)
```
- Core sadece **ses/görüntü akışları ve olaylar** görür; cihazın iPhone mı
  gözlük mü olduğunu umursamaz.
- Gözlük geldiğinde sadece **yeni bir istemci adaptörü** yazarsın; Core
  aynı kalır.
- AR ekran (display_out) opsiyonel bir kanal olarak sözleşmede dursun,
  başta boş geç.

---

## 28. Kişilik

- Kişilik bir **sistem prompt + davranış kuralları** katmanı olarak
  tanımlanır (ayrı, versiyonlanabilir bir dosya).
- Kurallar: sakin, teknik, kısa, gereksiz konuşmayan, **emin olmadığında
  açıkça belirten** ("emin değilim, doğrulayayım"), bilinç/duygu iddia
  etmeyen.
- **Emin olmama** davranışı teknik doğruluk için kritik — özellikle vision
  ve teşhiste (§9, §20).

---

## 29. "Sürekli Dinliyor" / Wake Word

- **Wake-word teknolojisi:** cihaz-içi hafif modeller (ör. Porcupine gibi
  gömülü wake-word motorları) — düşük gecikme, düşük tüketim.
- **Ama iOS gerçeği:** Uygulama arka plandayken sürekli mikrofon erişimi
  Apple tarafından ciddi kısıtlıdır ve App Store politikalarına takılır.
  Cihaz-içi "Hey Siri" tarzı her zaman-açık dinleme **OS seviyesi ayrıcalık**
  ister, üçüncü parti uygulamalar için pratikte kapalı.
- **Gerçekçi V1:** Uygulama açıkken wake-word / **push-to-talk** (butona
  bas-konuş). "Kapalıyken bile sürekli dinleyen" senaryosunu **gözlük veya
  ayrı bir donanım cihazı** aşamasına ertele (kendi donanımında bu kısıt yok).
- Gizlilik: sürekli dinleme = sürekli veri; wake-word'ü **cihazda** tut,
  sadece tetiklenince buluta/servera gönder.

---

## 30. Test ve Evaluation Sistemi

Ciddi proje için doğru talep. Katmanlar:

| Kategori | Ne test eder | Yaklaşım |
|---|---|---|
| **Unit** | Fonksiyonlar, tool'lar | pytest |
| **Integration** | Modüller arası akış | pytest + test container'lar |
| **Tool** | Her tool doğru/güvenli çalışıyor mu | Mock OS + gerçek sandbox |
| **LLM Eval** | Cevap kalitesi/tutarlılık | Altın set + LLM-as-judge |
| **Vision Eval** | Bileşen tanıma doğruluğu | Etiketli fotoğraf seti |
| **Speech Eval** | STT WER, TTS anlaşılırlık | Türkçe ses seti, WER metriği |
| **Memory Eval** | Doğru hatırlama/getirme | Senaryo testleri |
| **Security** | İzin katmanı bypass edilemiyor mu | Kırmızı-takım testleri |
| **Latency** | Uçtan uca süre | Benchmark harness |
| **Diagnostic** | Teşhis doğruluğu | **Gerçek servis vakaları benchmark'ı** |

**En değerli varlığın:** Kendi **gerçek servis vakalarından** oluşan bir
benchmark. Her çözdüğün vakayı (belirti → teşhis → çözüm) kaydet; JARVIS'i
bu sette ölç. Bu, projeni herhangi bir chatbottan ayıran şey olacak.

---

# SONUÇ FORMATI

## A) ÖNERİLEN MİMARİ

```
┌─────────────────── İSTEMCİLER ───────────────────┐
│  iPhone (Swift/SwiftUI/AVFoundation)             │
│  [gelecekte: Akıllı gözlük] — Client Abstraction │
└──────────────┬───────────────────────────────────┘
     WebRTC (canlı ses/video) + WebSocket (kontrol)
                │
┌───────────────▼─────────── JARVIS CORE (Linux, bare-metal/WSL2) ┐
│  Orchestrator + Model Router                                    │
│   ├─ Voice: faster-whisper (STT) → LLM → ElevenLabs (TTS)       │
│   ├─ LLM: Ollama (yerel 7-8B) + Bulut LLM (ağır reasoning)      │
│   ├─ Vision: Bulut multimodal (V1) [sonra yerel opsiyon]        │
│   ├─ RAG: Chroma→Qdrant + bge-m3 embed + reranker               │
│   ├─ Memory: SQLite (+ Redis sonra) + Vektör DB                 │
│   ├─ Diagnostic Engine: Karar ağacı + rule + LLM + RAG          │
│   ├─ Tools → Tool Manager → Permission Layer → OS               │
│   ├─ Calendar (SQLite) + Proactive (event-driven izleme)        │
│   └─ Security: risk sınıfları, onay, audit log, sandbox         │
└─────────────────────────────────────────────────────────────────┘
```

## B) DONANIM GEREKSİNİMLERİ
- **Zotac RTX 3080 Ti (12 GB)** — bare-metal Linux üzerinde, CUDA ile.
  **VirtualBox terk edilecek.**
- 32 GB RAM rahat. Ryzen 7 5800X (8C/16T) bu iş yükü için yeterli.
- Tek seferde **tek ağır GPU işi** (LLM); STT/Vision router ile yönetilir
  veya buluta verilir.
- iPhone + Apple Developer (~$99/yıl).

## C) YAZILIM STACK
- OS: Ubuntu LTS (veya Windows+WSL2). Docker Compose.
- LLM: Ollama + bulut LLM API. STT: faster-whisper. TTS: ElevenLabs (streaming).
- Vision: bulut multimodal. Embed: bge-m3. Vektör: Chroma→Qdrant.
- DB: SQLite→Postgres+pgvector, Redis (sonra). Dil: Python (çekirdek), Swift (iOS).
- Test: pytest + eval harness.

## D) MODEL STRATEJİSİ
- **Hibrit + kural-tabanlı router.** Yerel: gizli/basit/düşük-gecikme.
  Bulut: ağır reasoning/en iyi Türkçe/vision. **Fine-tuning yok** (V1/V2).
  Öğrenme = RAG + memory.

## E) iPHONE MİMARİSİ
- Swift/SwiftUI/AVFoundation. **WebRTC** (ses/video) + **WebSocket**
  (kontrol). QR pairing + TLS/JWT. Key'ler serverda. V1: push-to-talk
  (arka plan sürekli dinleme yok).

## F) MEMORY + RAG
- 5 hafıza katmanı; V1 SQLite + Chroma. Semantik chunking, çok dilli embed,
  reranker. Büyüyünce Qdrant/pgvector + Redis.

## G) TECHNICIAN MODE
- **Hibrit teşhis motoru:** karar ağacı + rule engine + LLM + RAG.
  Playbook'lar + hipotez/olasılık + "en bilgilendirici test" döngüsü.
  Gerçek vaka benchmark'ı. Vision genel tanıma için, kesin model iddiası için
  **değil** (emin olmama davranışı).

## H) SECURITY
- LOW/MEDIUM/HIGH/CRITICAL sınıfları. Tool Manager → Permission Layer → OS.
  CRITICAL'de iki-adımlı açık onay + dry-run. Audit log. Komut allowlist +
  tehlikeli-pattern reddi.

## I) SMART GLASSES ROADMAP
- Client Abstraction bugünden. Core istemci-agnostik. Gözlük = yeni adaptör,
  Core değişmez. AR display_out kanalı sözleşmede rezerve, başta boş.

## J) GELİŞTİRME ROADMAP
1. **Faz 0 — Altyapı:** Linux/CUDA kurulumu (VirtualBox'tan çık), repo
   iskeleti, config, test harness.
2. **Faz 1 — Metin çekirdeği:** Orchestrator + yerel LLM (Ollama) + Tool
   Manager + Permission Layer + temel sistem tool'ları (sıcaklık, SMART,
   disk). Terminalden çalışan JARVIS.
3. **Faz 2 — Ses:** faster-whisper + ElevenLabs streaming, uçtan uca sesli
   döngü (önce masaüstü mikrofon).
4. **Faz 3 — Memory + RAG:** SQLite hafıza + Chroma + doküman yükleme.
5. **Faz 4 — Teşhis motoru:** karar ağacı + playbook + vaka kaydı.
6. **Faz 5 — iPhone:** WebSocket push-to-talk MVP → WebRTC.
7. **Faz 6 — Vision:** bulut multimodal ile bileşen tanıma.
8. **Faz 7 — Proaktif + Ajanda.**
9. **Faz 8+ — Router olgunlaştırma, Qdrant geçişi, (opsiyonel) LoRA, gözlük.**

## K) İLK KODLANACAK MODÜL
**Core + Tool Manager + Permission Layer + birkaç LOW-risk sistem tool'u
(get_system_info, get_cpu/gpu_temperature, get_disk_health), yerel LLM
(Ollama) ile bağlanmış, terminalden çalışan bir agent loop.**
Neden: Bu, tüm projenin **güvenlik ve mimari omurgası.** Ses/vision/iPhone
bunun üstüne oturur. Önce iskeleti güvenli ve modüler kur.

---

# "J.A.R.V.I.S. V1 için hangi mimariyi seçtim ve neden?"

**Seçim:** Bare-metal Linux (veya WSL2) üzerinde çalışan, **modüler,
hibrit (yerel + bulut), tool tabanlı bir agent çekirdeği.** V1'de:
yerel LLM (Ollama 7–8B) + bulut LLM (ağır reasoning), faster-whisper (STT),
ElevenLabs (TTS), Chroma (RAG), SQLite (hafıza), ve **her şeyin altında bir
Tool Manager + Permission Layer.** Vision ve iPhone ilk sürümde en basit
çalışan hallleriyle (bulut vision, push-to-talk WebSocket).

**Neden:**
1. **Donanım gerçeği:** 12 GB VRAM tek başına "her şeyi yerel" yaptırmaz;
   hibrit + router **zorunluluktur.** VirtualBox GPU'yu kullanamaz, o yüzden
   bare-metal/WSL2 şart.
2. **Risk yönetimi:** En büyük risk kapsam. Modüler çekirdek + fazlı yol
   haritası, her fazda çalışan bir ürün verir; "her şey aynı anda" tuzağından
   kaçınır.
3. **Güvenlik:** Sistem erişimi olan bir asistanda Permission Layer opsiyonel
   değil; bu yüzden ilk kodlanan şey o.
4. **Doğruluk:** Teşhis ve vision'da saf LLM güvenilmez; hibrit motor +
   "emin olmama" davranışı seni gerçek bir teknisyen aracına yaklaştırır,
   şık ama yanılan bir chatbot'a değil.
5. **Geleceğe hazırlık:** Client Abstraction sayesinde iPhone→gözlük geçişi
   çekirdeği bozmaz; fine-tuning yerine RAG+memory ile kontrollü "öğrenme."

**Kısacası:** Iron Man'in JARVIS'ini bir gecede kurmuyoruz. Ama **güvenli,
modüler, hibrit bir çekirdekle** başlayıp her fazda gerçekten çalışan,
senin teknik servis işine bugün fayda veren bir asistan kuruyoruz — ve onu
zamanla gerçek JARVIS'e büyütüyoruz.

---

## Sana Açıkça "Önermiyorum" Dediklerim (Özet)
- ❌ **VirtualBox'ta AI/GPU** — çalışmaz, terk et.
- ❌ **Baştan fine-tuning** — gereksiz; RAG+memory kullan.
- ❌ **Fotoğraftan kesin anakart/soket model iddiası** — güvenilmez; OCR+RAG
  ile doğrula ve "emin değilim" dedir.
- ❌ **iOS'ta arka planda sürekli dinleme (V1)** — OS/App Store kısıtı;
  push-to-talk ile başla.
- ❌ **vLLM/TGI** senin tek-kullanıcı/10 GB senaryonda **aşırı** — Ollama yeter.
- ❌ **Her şeyi tek seferde** — fazlı git.

> Sıradaki adım: Bu mimariyi onayla (veya değiştirmek istediğin noktaları
> söyle). Onaydan sonra **Faz 0 + Faz 1** ile (repo iskeleti, Core,
> Tool Manager, Permission Layer, ilk sistem tool'ları) **kod yazmaya**
> başlayabiliriz.
