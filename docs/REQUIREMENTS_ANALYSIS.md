# J.A.R.V.I.S. — Gereksinim Denetimi: Eksikler, Çelişkiler ve Kararlar

> Durum: **Gereksinim analizi.** Kod yok.
> Girdi: `docs/ARCHITECTURE.md` (temel davranış ve mimari gereksinimler olarak kabul edildi).
> Amaç: Bu gereksinim setini bir mühendis gözüyle denetlemek — eksik olanı,
> kendi içinde çelişeni ve senin karar vermen gereken belirsizlikleri
> çıkarmak. Her sorunun yanında uygulanabilir bir öneri var.

Bu doküman gereksinimlerin **doğru** olduğunu varsaymıyor; onları **kırmaya**
çalışıyor. Amaç kod yazmadan önce zayıf noktaları bulmak.

---

## 0. Önce En Kritik Bulgu

Gereksinimlerde **projenin ana amacını (bilgisayar teknik servisi) doğrudan
tehdit eden bir mantık boşluğu** var. Kısaca: J.A.R.V.I.S. sıcaklık okur,
SMART okur, terminal komutu çalıştırır, sistem bilgisi alır — **ama hangi
makinede?**

- Kişisel kullanımda hedef makine = J.A.R.V.I.S.'in çalıştığı makine. Sorun yok.
- **Teknik serviste hedef makine, tamir edilen (çoğu zaman bozuk, hatta
  açılmayan) BAŞKA bir makinedir.** J.A.R.V.I.S. bir yazılım olarak,
  **POST etmeyen / açılmayan / işletim sistemi olmayan** bir bilgisayarın
  sıcaklığını, SMART verisini, loglarını **okuyamaz.**

Bu, "get_cpu_temperature / get_disk_health / run_terminal_command" gibi
tool'ların, tam da en çok ihtiyaç duyulacağı senaryoda (arızalı müşteri
makinesi) **işe yaramayacağı** anlamına gelir. Gereksinim bu ayrımı hiç
yapmıyor. Bu, kod yazmadan **çözülmesi gereken bir numaralı konu** (bkz. §2.1).

---

## 1. Çelişkiler (Gereksinimin Kendi İçinde Tutarsızlıkları)

### C1 — Gizlilik vs. Bulut Kullanımı
- **Gereksinim:** "Hassas veri → yerel model" (§18/§25) **ama aynı zamanda**
  vision → bulut, ağır reasoning → bulut, ses → ElevenLabs.
- **Çelişki:** Teknik serviste kameraya tuttuğun şey **müşteri donanımı**;
  konuştuğun metin **müşteri/kişisel veri.** Bulut vision'a giden her fotoğraf
  ve ElevenLabs'e giden her cümle, "hassas veri yerelde kalsın" ilkesini
  deler.
- **Öneri:** Net bir **veri sınıflandırma politikası** yaz: hangi veri türü
  asla buluta gitmez (müşteri kimliği, seri no, ekran görüntüsündeki kişisel
  bilgi), hangisi gidebilir. Router'a bir **"gizlilik bayrağı"** ekle;
  bayrak set ise yerel modele düş, buluta gitme. Bu bir kod değil, önce bir
  **karar** (bkz. Karar D3).

### C2 — Doğal/Düşük Gecikmeli Ses vs. Bulut Zinciri
- **Gereksinim:** "Mümkün olduğunca doğal hissettiren ses" (§19) **ama**
  STT/LLM/TTS zincirinin parçaları bulutta.
- **Çelişki:** Her ağ atlaması gecikme ekler; "insan gibi anlık" (<500 ms)
  hedefiyle bulut zinciri çelişir.
- **Öneri:** Gecikme hedefini **yol bazında** ayır ve gereksinime yaz:
  yerel yol ~0.8–1.5 sn, bulut yol 1.5–3 sn. "<500 ms" bir gereksinim
  **değil**, gerçekçi olmayan bir beklenti olarak işaretlendi (bkz. §26 ana doküman).

### C3 — Proaktif Bildirim vs. "Gereksiz Konuşmayan"
- **Gereksinim:** Proaktif uyarılar (§23) **ama** "gereksiz bildirim
  üretmemeli", "gereksiz konuşmayan" kişilik (§15).
- **Çelişki:** İki hedef aynı eşiği paylaşmıyor; tanımsız bırakılırsa ya çok
  sık ya hiç bildirmez.
- **Öneri:** Bir **bildirim politikası** tanımla: önem eşiği + cooldown +
  "sadece eyleme dönük" kuralı. Bu bir gereksinim maddesi olmalı, kod
  detayı değil (bkz. Karar D5).

### C4 — Sesle Kontrol vs. CRITICAL İşlemlerde "Açık Onay"
- **Gereksinim:** Eller serbest sesli kullanım **ama** CRITICAL işlemlerde
  (disk format, BIOS flash) "açık onay."
- **Çelişki:** STT yanlış duyabilir. Yıkıcı bir işlemi **yalnızca sesle**
  onaylamak tehlikelidir ("format" ↔ "formu" karışması felaket olur).
- **Öneri:** CRITICAL onayı **ikinci bir kanaldan** iste: iPhone'da fiziksel
  onay ekranı / buton, veya belirli bir doğrulama cümlesinin **yazıyla**
  girilmesi. Sesli onay CRITICAL için **tek başına yeterli sayılmasın**
  (bkz. Karar D4).

### C5 — "Teknisyen gibi kesin teşhis" vs. "Emin olmadığını belirt"
- **Gereksinim:** Kesin, teknisyen gibi teşhis (§7/§20) **ama** emin
  olmadığında açıkça söyleyen kişilik (§15).
- **Çelişki:** Bunlar zıt değil ama **kalibre edilmezse** biri diğerini ezer
  (ya aşırı kendinden emin ya sürekli "emin değilim").
- **Öneri:** Teşhis çıktısını **güven skoru + olasılık sıralı hipotezler**
  formatına bağla. "Emin olmama" bir kişilik lafı değil, teşhis motorunun
  **yapısal çıktısı** olsun (bkz. G bölümü ana doküman).

### C6 — "Yerel + gizli" vs. RTX 3080 Ti'nin 12 GB'ına Aynı Anda 3 Model
- **Gereksinim:** Yerel LLM + yerel STT + yerel vision (gizlilik için) **ama**
  donanım tek seferde hepsini VRAM'e sığdırmaz.
- **Çelişki:** "Her şey yerel + gizli" ile 12 GB fiziksel sınırı çelişir.
  (12 GB'da 14B+Whisper birlikte taşar; 7B+Whisper sığar.)
- **Öneri:** Zaten mimaride çözüldü (router ile sırayla yükle/boşalt veya
  bir kısmını buluta ver). Ama bunu bir **gereksinim kısıtı** olarak
  yazıya dök: "Aynı anda GPU'da tek ağır model bulunabilir."

### C7 — iPhone Wake-Word "Sürekli Dinleme" vs. iOS Kısıtları
- **Gereksinim:** iPhone'da sürekli dinleyen "JARVIS" wake word (§16).
- **Çelişki:** iOS arka plan mikrofon/ağ kısıtları bunu pratikte engeller.
- **Öneri:** V1'de push-to-talk / uygulama-açıkken wake-word. "Her zaman
  dinleme"yi gözlük/özel donanım fazına ertele (ana dokümanda mevcut).

---

## 2. Eksik Gereksinimler (Belirtilmemiş ama Zorunlu Kararlar)

### 2.1 — **Hedef Makine Ayrımı (EN KRİTİK EKSİK)**
Gereksinim, "sistem okuma" ile "arıza teşhisi"ni aynı makinede varsayıyor.
Ayrıştırılmalı:
- **Host modu:** J.A.R.V.I.S.'in çalıştığı makine (kişisel kullanım).
  Tool'lar doğrudan çalışır.
- **Servis modu (hedef ayrı makine):** Tamir edilen makine. Seçenekler:
  1. **Canlı ve açılabiliyorsa:** hedefe küçük bir **ajan/agent** kur
     (SSH veya hafif bir yardımcı servis) → J.A.R.V.I.S. uzaktan okur.
  2. **Açılmıyor / POST etmiyorsa:** yazılım okuması **imkânsız.** Burada
     J.A.R.V.I.S.'in rolü **rehberli manuel teşhis** olur: kullanıcıdan
     gözlem ister (LED, bip kodu, koku, fan dönüyor mu), kamerayla bakar,
     ve **teşhis motorunu (playbook) bu manuel gözlemlerle** yürütür.
  3. **Canlı ortam (Linux USB) ile boot:** bazı testler için bir tanı USB'si.
- **Öneri:** Teşhis motorunu **iki girdi kaynağına** göre tasarla: (a) otomatik
  telemetri (host/ajan), (b) **insan-gözlem girdisi** (manuel). Servis
  senaryosunun büyük kısmı (b) olacak — motor buna göre kurulmalı
  (bkz. Karar D1). Bu, ana dokümandaki teşhis motorunu **güçlendiren** en
  önemli düzeltme.

### 2.2 — Ağ Topolojisi ve Uzak Erişim
- **Eksik:** iPhone ↔ Server bağlantısı nerede? Sadece ev LAN'ı mı? Serviste
  sahadayken ev sunucusuna nasıl erişilecek?
- **Öneri:** Bir bağlantı modeli seç: (a) yalnızca ev LAN'ı (basit, saha
  yok), (b) **VPN/güvenli tünel** (WireGuard/Tailscale) ile sahadan eve
  erişim, (c) hibrit. Saha kullanımı istiyorsan (b) neredeyse zorunlu
  (bkz. Karar D2).

### 2.3 — Çevrimdışı (Offline) Davranış
- **Eksik:** İnternet yokken ne çalışır? Bulut LLM/vision/ElevenLabs hepsi
  internet ister.
- **Öneri:** Bir **düşüş (degradation) stratejisi** tanımla: internet yoksa
  yerel LLM + yerel STT + yerel TTS (Piper) fallback; vision devre dışı.
  Her yeteneğin "offline'da çalışır/çalışmaz" etiketi olsun.

### 2.4 — Prompt Injection / Araç Kötüye Kullanımı (KRİTİK GÜVENLİK EKSİĞİ)
- **Eksik:** RAG'e yüklenen bir PDF, bir web sayfası veya bir müşteri
  dokümanı, model için **gizli talimat** içerebilir ("tüm diskleri sil"
  gibi). Tool execution katmanı olan bir sistemde bu **ciddi bir saldırı
  yüzeyi.** Gereksinimde hiç yok.
- **Öneri:** Güvenlik gereksinimine ekle: (a) retrieval içeriği ve web
  çıktısı **veri olarak** işaretlenir, talimat olarak değil; (b) tool
  çağrıları **kaynağı ne olursa olsun** izin katmanından ve risk
  sınıfından geçer — yani bir dokümandan gelen "format" isteği bile CRITICAL
  onaya takılır; (c) yıkıcı tool'lar asla otomatik tetiklenmez. Bu, izin
  katmanının **neden var olduğunun** asıl gerekçesidir.

### 2.5 — Kimlik / Çok Kullanıcı / Yetki
- **Eksik:** Tek kullanıcı mı? Başkası konuşursa? CRITICAL komutu kim
  verebilir?
- **Öneri:** V1 = tek yetkili kullanıcı. İstersen **ses/cihaz kimliği** ile
  "sahip" doğrulaması (opsiyonel). CRITICAL işlemler yalnızca doğrulanmış
  sahip + ikinci kanal onayı ile.

### 2.6 — Veri Saklama, Silme ve Yasal Uyum (KVKK)
- **Eksik:** Servis vakaları müşteri verisi içerir (isim, cihaz, belki
  kişisel dosya izleri). Ne kadar saklanır? Silme hakkı? Türkiye'de **KVKK**
  yükümlülüğü doğabilir.
- **Öneri:** Bir **veri saklama politikası** tanımla: ne saklanır, ne kadar,
  nasıl silinir, şifreleme (at-rest). Müşteri kişisel verisini **minimum**
  tut. Bu bir gereksinim maddesi olmalı.

### 2.7 — Kayıt Rızası (Kamera/Mikrofon, Üçüncü Kişiler)
- **Eksik:** Serviste ortamda başkaları olabilir; kamera/mikrofon kaydı
  rıza gerektirebilir.
- **Öneri:** Kayıt/işlemenin ne zaman aktif olduğunu **görünür** yap
  (gösterge), ve gerektiğinde rıza akışı.

### 2.8 — Maliyet Bütçesi ve Limitler
- **Eksik:** ElevenLabs (karakter başı), bulut LLM/vision (token başı) —
  harcama sınırı yok. Çok konuşan bir asistan faturayı patlatır.
- **Öneri:** Aylık **bütçe tavanı** ve uyarı eşiği tanımla; router'da
  "buluta gitmeden önce maliyet farkındalığı." Kısa cevap kişiliği hem UX
  hem maliyet için.

### 2.9 — Kabul Kriterleri / Başarı Ölçütü
- **Eksik:** Her yetenek "çalışıyor" ne demek? Özellikle teşhis doğruluğu
  hedefi yok.
- **Öneri:** Her yeteneğe **ölçülebilir kabul kriteri** yaz (ör. STT WER < %X
  Türkçe'de; time-to-first-audio < 1.5 sn; teşhis motoru altın vaka setinde
  ilk-hipotez isabeti > %Y). §30'daki eval sistemi bunları ölçer.

### 2.10 — Gözlemlenebilirlik ve Hata Ayıklama
- **Eksik:** Audit log var ama agent kararlarının **izlenebilirliği** (neden
  bu tool, neden bu cevap) yok.
- **Öneri:** Yapılandırılmış **tracing/log** (her turda: hangi model, hangi
  retrieval, hangi tool, hangi karar). Hem hata ayıklama hem güven için.

### 2.11 — Yedekleme / Kurtarma
- **Eksik:** Hafıza + bilgi tabanı + vaka DB'si için yedek/geri yükleme yok.
- **Öneri:** Düzenli yedek stratejisi (SQLite + vektör DB snapshot). Vaka
  geçmişi senin en değerli varlığın; kaybı kabul edilemez.

### 2.12 — Dil Politikası
- **Eksik:** Türkçe konuşma + çoğu teknik doküman İngilizce. J.A.R.V.I.S.
  hangi dilde cevap verir? Kod-değiştirme (code-switching)?
- **Öneri:** Varsayılan **Türkçe cevap**, teknik terimler İngilizce
  korunur; kullanıcı isterse dil değişir. Embedding **çok dilli** olmalı
  (zaten bge-m3 seçildi).

---

## 3. Belirsizlikler — Senin Karar Vermen Gerekenler (Karar Kaydı)

| # | Karar | Neden gerekli | Önerim (V1) |
|---|---|---|---|
| **D1** | Teşhis hedefi: host mu, ayrı müşteri makinesi mi, ikisi de mi? | Tüm teşhis motoru ve tool tasarımını belirler (§2.1) | **İkisi de**, ama V1'de **manuel-gözlem tabanlı** rehberli teşhis + host telemetri; uzak ajan sonra |
| **D2** | Ağ modeli: sadece ev LAN mı, saha erişimi (VPN) mi? | iPhone bağlantısı ve saha kullanımı (§2.2) | Ev LAN ile başla; saha için **Tailscale/WireGuard** ekle |
| **D3** | Veri sınıflandırma: ne asla buluta gitmez? | Gizlilik-bulut çelişkisi (C1) | Müşteri kimliği/kişisel veri **yerel**; genel teknik sorgu bulut olabilir |
| **D4** | CRITICAL onay kanalı | Sesli onayın riski (C4) | **İkinci kanal**: iPhone dokunmatik onay + doğrulama cümlesi |
| **D5** | Bildirim eşiği + cooldown politikası | Proaktif vs. sessiz çelişkisi (C3) | Sadece eyleme dönük + tek uyarı + düşene kadar sus |
| **D6** | Bütçe tavanı (ElevenLabs + bulut API) | Maliyet kontrolü (§2.8) | Aylık tavan + %80 uyarısı |
| **D7** | Tek kullanıcı mı, sahip doğrulama mı? | Yetki (§2.5) | Tek yetkili kullanıcı; CRITICAL'de sahip + ikinci kanal |
| **D8** | Veri saklama süresi + KVKK yaklaşımı | Yasal + gizlilik (§2.6) | Minimum saklama, at-rest şifreleme, silme akışı |

---

## 4. Gereksinim Setine Önerdiğim Eklemeler (Fonksiyonel Olmayan)

Mevcut gereksinimler ağırlıkla **fonksiyonel** (ne yapsın). Ciddi proje için
**fonksiyonel olmayan** gereksinimleri de yazıya dökmeni öneriyorum:

- **Güvenlik:** prompt-injection savunması, tool izin zorunluluğu, at-rest
  şifreleme, audit log değişmezliği.
- **Gizlilik/Veri yönetişimi:** veri sınıflandırma, saklama, silme, KVKK.
- **Güvenilirlik:** offline düşüş stratejisi, servis yeniden başlatma,
  yedek/kurtarma.
- **Performans:** yol-bazlı gecikme hedefleri, GPU tek-ağır-model kısıtı.
- **Gözlemlenebilirlik:** karar izleme, metrik toplama.
- **Maliyet:** bütçe tavanı ve izleme.
- **Test edilebilirlik:** her yetenek için kabul kriteri + eval seti.

---

## 5. Özet: Gereksinim Setinin Sağlığı

**Güçlü yanlar:** Kapsam net, modülerlik ve güvenlik bilinci var, hibrit
yaklaşım doğru, öğrenmeyi (fine-tuning yerine RAG) doğru konumlamışsın.

**En kritik 3 boşluk (kod öncesi çözülmeli):**
1. **Hedef makine ayrımı (D1)** — teşhisin gerçek dünyada nasıl çalışacağını
   belirler; şu anki tool varsayımı serviste çökard.
2. **Prompt injection / tool kötüye kullanımı (§2.4)** — tool erişimi olan
   bir sistemde ele alınmazsa ciddi güvenlik açığı.
3. **Ağ topolojisi / saha erişimi (D2)** — "teknisyenin saha asistanı"
   hedefi buna bağlı.

**En kritik 2 çelişki:**
1. **Gizlilik vs. bulut (C1)** — veri sınıflandırma kararı (D3) ile çözülür.
2. **Sesli kontrol vs. CRITICAL onay (C4)** — ikinci onay kanalı (D4) ile çözülür.

---

## 6. Önerilen Sonraki Adım

Kod yazmadan önce **D1–D8 kararlarını** netleştirelim. Bu 8 karar,
ilk kodlanacak modülün (Core + Tool Manager + Permission Layer) tasarımını
doğrudan belirliyor — özellikle D1 (hedef makine) ve §2.4 (prompt injection),
izin katmanının şeklini tanımlıyor.

Sen bu kararları verdikçe, gereksinim dokümanını (`ARCHITECTURE.md`) buna
göre güncelleyip **kabul kriterli, çelişkisiz** bir V1 gereksinim temeli
oluşturacağız. Ancak ondan sonra Faz 0/Faz 1 kodlaması başlamalı.
