# J.A.R.V.I.S.

Kişisel, modüler bir yapay zekâ teknisyen asistanı. Sesli iletişim, görsel
analiz, donanım/sistem teşhisi, hafıza ve araç (tool) kullanımı hedeflenen; şu
an **V1 metin çekirdeği** çalışır durumda olan bir proje.

> **Durum:** V1 çekirdeği (Faz 0 + Faz 1). Ses, vision ve Neural Core paneli
> sonraki fazlarda. Mimari ve gereksinim analizi için `docs/` klasörüne bakın.

## Ne var (V1 çekirdeği)

- **Core state machine** — `HAZIR / DİNLİYOR / DÜŞÜNÜYOR / KONUŞUYOR / …`
  durumları (Neural Core paneliyle birebir; panel sonra bu makineye bağlanacak).
- **Güvenli araç katmanı** — `LLM → Agent → Tool Manager → Permission Layer → OS`.
  Her araç bir risk seviyesi taşır (`LOW/MEDIUM/HIGH/CRITICAL`); HIGH/CRITICAL
  işlemler açık kullanıcı onayı ister, her çağrı denetim günlüğüne (audit log)
  yazılır.
- **Host sistem araçları** (LOW risk, salt-okunur) — CPU/GPU sıcaklık, RAM,
  disk/SMART, sistem özeti. Sensör/GPU yoksa zarifçe "mevcut değil" döner.
- **Hafıza (SQLite)** — konuşma otomatik kaydedilir; kalıcı bilgiler yalnızca
  açık `remember_fact` çağrısıyla yazılır. Bilinen bilgiler her turda bağlama
  eklenir.
- **Servis defteri** — serviste gelen cihaz bir *vaka* olarak kaydedilir:
  müşteri, cihaz, belirti, denenenler, sonuç. Vaka boş belirtiyle açılamaz ve
  sonuç yazılmadan kapatılamaz — sonradan aranamayan bir kayıt hiç kayıt
  tutmamaktan kötüdür. Kapanan vakalar silinmez, arşivlenir.
- **Geçmiş vaka arama** — `vaka_ara` benzer belirtiyi geçmişte arar ve **ne
  çıktığını** getirir. Türkçe katlama var: `IŞIK`, `ışık`, `isik` ve
  `goruntu yok` ↔ `görüntü yok` birbirini bulur. Açık vakalar ayrıca her turda
  bağlama girer — sorulmadan neyin tezgâhta olduğunu bilir.
- **Kimlik katmanı** — `jarvis-tanit` ile sahibini tanır (ad, hitap, rol,
  meslek, cevap tercihi) ve üzerinde çalıştığı makineyi bilir. Kimlik yerel
  veritabanında tutulur, koda yazılmaz; `forget_fact` ile silinemez.
- **Terminal aracı** — allowlist'li, **kabuk kullanmadan** (komut zincirleme ve
  `sudo` yok). Risk komuta göre belirlenir: okuma MEDIUM, sistem değişikliği
  HIGH, yıkıcı işlem CRITICAL. Listede olmayan komut hiç çalışmaz.
- **Dosya araçları** — oku/yaz/listele. Sır dosyaları (`id_rsa`, `.env`, `.ssh/`
  …) tamamen erişim dışı; sistem dizinine yazmak onay ister.
- **Ses (ElevenLabs-first)** — J.A.R.V.I.S. 2.0.1'in ana TTS motoru ElevenLabs.
  Canlı konuşma için `eleven_flash_v2_5`, yüksek ifade için `eleven_v3`;
  Piper ve Edge yalnızca isteğe bağlı yedek sağlayıcıdır. **ElevenLabs** daha doğal
  ama karakter başına ücretli — uzun bir cevap para kararına dönüşüyor.
  Kurulu olmayan bir sağlayıcı "hazır" demez; eksik neyse açılışta söyler.
  Anahtar yalnızca `.env` içinde. `jarvis-ses --kontrol` · `docs/SES.md`.
- **Mikrofon (faster-whisper STT)** — panelde 🎙 düğmesi. Kayıt **bu makinede**
  çözümlenir, buluta gitmez. Duyulan metin doğrudan çalıştırılmaz, yazı
  kutusuna düşer — yanlış duyulmuş bir cümle görülmeden komut olmasın diye.
  İsteğe bağlı bağımlılık: yoksa yalnızca mikrofon kapalı olur.
  Ayrıntı: `docs/MIKROFON.md`.
- **Kamera (yerel görüntü analizi)** — panelde **Vision** sekmesi. Kare **bu
  makinede** ölçülür, ne diske yazılır ne dışarı çıkar: geriye yalnızca kaç
  yüz ve nerede bilgisi kalır. Varsayılan **kapalı** — bir tezgâh kamerası
  müşteriyi de görür, açmak bilinçli bir hareket olmalı: `jarvis-panel
  --kamera`. Aşama 1 yalnızca hedef takibi; tanıma ve nesne ayırt etme sırada.
  Ayrıntı: `docs/KAMERA.md`.
- **Bilgi tabanı (RAG)** — `jarvis-bilgi ekle ~/proje` ile kodunuzu, notlarınızı
  ve dokümanlarınızı aranabilir yapar. Hafızadan **ayrı bir katman**: hafıza
  sizinle ilgili olanı her turda *iter*, bilgi tabanı belgeleri sorulduğunda
  *çeker*. Arama hibrit — anlam (yerel gömme) + kelime (BM25), RRF ile
  birleştirilir; tam tanımlayıcılar (`libcublas.so.12`) ile kavramsal sorular
  ("nasıl bağlamıştık") farklı yarılarda yakalanır. Sonuçlar `dosya:satır`
  olarak gelir. Gizli dosyalar (`.env`, anahtarlar) indekslenmez — dosya
  araçlarıyla **aynı** kara liste. Ayrıntı: `docs/BILGI-TABANI.md`.
- **Uygulama açma** — "YouTube aç", "hesap makinesi aç", "ayarları aç".
  Ad Türkçe söylendiği gibi verilir; eşleştirme katlamalı ve affedici
  ("hesap makinası", "gorev yoneticisi" da bulur). **Katalog bir beyaz
  liste**: eline verilen bir yolu çalıştırmaz, çünkü o zaman terminal
  aracının allowlist'i nazikçe rica ederek atlanabilirdi — ve rica bir web
  sayfasından gelebilir. Eksik olanı sahibi `~/.jarvis/uygulamalar.json`
  içine ekler.
- **Model karşılaştırma** — `jarvis-karsilastir` iki yerel modele aynı soruları
  sorar ve **kör** bir karşılaştırma sayfası üretir (model adları ve süreler
  ayrı dosyada). Donanım kararını tahminle değil ölçümle vermek için:
  `docs/MODEL-KARSILASTIRMA.md`.
- **Provider-agnostik LLM** — `mock` (modelsiz, test için) ve `ollama` (yerel).
  İleride bulut model + router aynı arabirime eklenecek.
- **Terminal agent** — `python -m jarvis` ile çalışan REPL.
- **Windows başlatıcı** — masaüstündeki simgeye çift tıkla, panel açılsın.
  Kurulum WSL kabuğundan: `./windows/kur.sh` (veya Windows'tan `Kur.cmd`).
  WSL'i ve proje klasörünü kendisi bulur; panelin gerçekten
  hazır olduğunu `/health` cevabından anlar — port açık olduğu hâlde ölü bir
  `portproxy`'ye tarayıcı açmasın diye. Ayrıntı: `windows/BENIOKU.md`.
- **Canlı panel** — `jarvis-panel` ile Neural Core arayüzü gerçek duruma ve
  telemetriye bağlanır (SSE, ek bağımlılık yok). ElevenLabs ayarlıysa cevapları
  **tarayıcıda sesli okur**. Olmayan modüller için uydurma veri göstermez:
  yoksa "yok" yazar.

Teşhis/telemetri hedefi V1'de **çalıştığı makinedir (host)** — karar D1,
bkz. `docs/REQUIREMENTS_ANALYSIS.md`.

## Kurulum

```bash
pip install -e .            # veya: pip install psutil
cp .env.example .env        # ayarları düzenleyin (gizli anahtarlar .env'de kalır)
```

## Çalıştırma

```bash
python -m jarvis
```

Örnek:

```
sen › cpu sıcaklığı kaç?
   · durum: DÜŞÜNÜYOR
   · durum: ANALİZ EDİYOR
JARVIS › [get_cpu_temperature] sonucu: {...}
```

Yerel model ile (Ollama kurulu ve model indirilmişse):

```bash
JARVIS_LLM_PROVIDER=ollama JARVIS_OLLAMA_MODEL=qwen2.5:14b-instruct python -m jarvis
```

## Test

```bash
pytest -q
```

## Proje yapısı

```
jarvis/
  config.py            # ayarlar (.env / env vars)
  bootstrap.py         # bileşenleri birleştirir
  core/                # state machine, agent loop, persona
  memory/              # SQLite hafıza deposu (konuşma + kalıcı bilgiler)
  security/            # permission layer + audit log
  tools/               # tool base + manager + sistem/hafıza/terminal/dosya araçları
  llm/                 # LLM soyutlaması: mock / ollama
  voice/               # ElevenLabs TTS + ses doğrulama komutu
  web/                 # canlı panel sunucusu (HTTP + SSE)
tests/                 # permission, tool, agent testleri
docs/                  # mimari analiz, gereksinim denetimi, PDF, UI mockup
```

## Güvenlik ilkesi

LLM işletim sistemine doğrudan erişmez. Her işlem Tool Manager ve Permission
Layer'dan geçer; bir dokümandan ya da web'den gelen "şunu çalıştır" isteği bile
aynı risk kapısına takılır (prompt-injection savunması). KRİTİK işlemler tek
başına sesle değil, açık bir doğrulama ile onaylanır.

İki kademeli koruma vardır:

1. **Politika reddi (mutlak)** — allowlist dışı komutlar ve sır dosyaları
   *onaya hiç sunulmaz*. Kullanıcı onaylasa bile çalışmazlar; yoksa allowlist
   bir onayla baypas edilebilirdi.
2. **İzin kapısı (onaylanabilir)** — meşru ama riskli işlemler (`systemctl`,
   sistem dizinine yazma) kullanıcı onayına sunulur.

Risk çağrı bazında hesaplanır ve **asla beyan edilen seviyenin altına inemez**;
sınıflandırıcı hata verirse işlem CRITICAL sayılır (fail-closed). Her karar tek
satır olarak `audit.log.jsonl` dosyasına yazılır.

## Yol haritası (özet)

1. ✅ **Faz 0–1** — Core + güvenli araç katmanı + host telemetri + terminal agent
2. ✅ **Faz 1.5** — Hafıza (SQLite) + terminal/dosya araçları + iki kademeli koruma
3. ✅ **Faz 2** — Ses: ElevenLabs TTS ✅ · faster-whisper STT ✅ · Canlı panel ✅
   (telefonda mikrofon HTTPS bekliyor — `docs/MIKROFON.md`)
4. 🔸 **Faz 3** — RAG: hibrit arama (anlam + kelime) ✅ · `jarvis-bilgi` ✅ ·
   panel sekmesi ve otomatik yeniden indeksleme sırada (`docs/BILGI-TABANI.md`)
5. 🔸 **Faz 4** — Diagnostic Brain: vaka kaydı ✅ · geçmiş arama ✅ · karar ağacı, playbook sırada
6. **Faz 5** — iPhone istemci · 🔸 **Faz 6** — Vision: hedef takibi ✅ ·
   yüz tanıma, karşılama, nesne tanıma sırada (`docs/KAMERA.md`) ·
   **Faz 7** — Proaktif + Ajanda

## Kurulum yolları

| Ortam | Rehber | GPU |
|---|---|---|
| **Windows + WSL2** ⭐ | `docs/KURULUM-WSL2.md` | ✅ tam |
| Bare-metal Linux | `docs/DONANIM-VE-KURULUM-PLANI.md` | ✅ tam + sensörler |
| VirtualBox (demo) | `docs/DEMO-KALI-VIRTUALBOX.md` | ❌ yok |

Ayrıntılı mimari ve gerekçeler: `docs/ARCHITECTURE.md`,
`docs/REQUIREMENTS_ANALYSIS.md`, `docs/JARVIS-Proje-Dokumani.pdf`.

Donanım planlaması:

| Belge | İçerik |
|---|---|
| `docs/JARVIS-32B-Sistem-Tasarimi.pdf` | **Güncel plan** — 32B sistem, görsel tasarım, katmanlı bütçe |
| `docs/JARVIS-Donanim-Butce-Raporu.pdf` | 70B analizi ve dört yolun karşılaştırması (arka plan) |
| `docs/MODEL-KARSILASTIRMA.md` | Kart almadan önce modeli kör olarak sınama |

