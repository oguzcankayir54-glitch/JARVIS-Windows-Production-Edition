# J.A.R.V.I.S. — Demo / Beta Kurulumu (VirtualBox + Kali Linux)

> Amaç: Ağır donanım yatırımı yapmadan önce sistemi **çalışırken görmek**.
> Bare-metal SSD kurulumu bu gözlemden sonra gelir (`DONANIM-VE-KURULUM-PLANI.md`).

---

## 1. Bu Demoda Ne Çalışır, Ne Çalışmaz

Bunu baştan bilmek önemli — beklenti ile gerçeği ayırmak demonun asıl faydası.

| Bileşen | VirtualBox'ta | Not |
|---|---|---|
| Çekirdek (agent döngüsü, state machine) | ✅ Tam | GPU gerektirmez |
| Güvenlik katmanı (izin + politika reddi) | ✅ Tam | Demo'nun en önemli parçası |
| Araçlar (terminal, dosya, hafıza) | ✅ Tam | Gerçekten çalışır |
| Hafıza (SQLite) | ✅ Tam | Kalıcı |
| Canlı panel (Neural Core) | ✅ Tam | Gerçek durum + telemetri |
| Ses çıkışı (ElevenLabs TTS) | ✅ Tam | Bulut API, GPU istemez |
| CPU/RAM/disk telemetrisi | ✅ Çalışır | Sanal makinenin değerleri |
| **CPU sıcaklık sensörü** | 🔴 Yok | Sanal makinede sensör yok |
| **GPU / VRAM** | 🔴 Yok | VirtualBox CUDA geçirmez |
| **Yerel LLM (GPU'da)** | 🔴 Yok | CPU'da küçük model mümkün ama yavaş |
| SMART disk sağlığı | 🟡 Kısıtlı | Sanal disk gerçek SMART vermez |
| RAG / Vision / Teşhis motoru | ⬜ Henüz yok | Sonraki fazlar |

**Panel bunları saklamaz:** olmayan bir şey için uydurma sayı göstermez.
GPU yoksa "yok" yazar, RAG yoksa "yok" yazar, teşhis paneli **"ÖRNEK VERİ"**
olarak işaretlenir. Demoda gördüğün her gerçek sayı gerçekten ölçülmüştür.

---

## 2. Kali Linux Hakkında Bir Not

Kali çalışır, ama seçimini bilerek yap:

- Kali bir **sızma testi** dağıtımıdır; varsayılan olarak root ağırlıklı ve
  sürekli güncellenen (rolling) bir sistemdir.
- J.A.R.V.I.S. için bir avantajı yok; teknik servis araçları (`smartctl`,
  `lm-sensors`) her dağıtımda var.
- **Demo için sorun değil.** Ama bare-metal kalıcı kurulumda **Ubuntu LTS**
  öneririm: NVIDIA sürücü desteği çok daha sorunsuz ve kararlı.

Kali'de zaten çalışıyorsan devam et — demo için tamamen yeterli.

---

## 3. VirtualBox Ayarları

Sanal makineyi kapatıp ayarlardan:

| Ayar | Değer | Neden |
|---|---|---|
| RAM | **4–6 GB** | Çekirdek + panel için yeter |
| CPU | **4 çekirdek** | 5800X'te rahat |
| Ekran belleği | 128 MB | Sadece masaüstü; AI ile ilgisi yok |
| Ağ | NAT (varsayılan) | Bulut API ve panel için yeterli |
| Disk | 25 GB+ | Model indirmeyeceksen yeter |

> **Not:** 256 MB "ekran belleği" ayarı CUDA/AI ile ilgisiz. Bu bir 2D
> masaüstü tamponudur; yerel model çalıştırmaz.

---

## 4. Kurulum

Kali içinde terminal aç:

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip git

git clone --branch feat/complete-project-sync https://github.com/oguzcankayir54-glitch/JARVIS-Windows-Production-Edition.git
cd JARVIS-Windows-Production-Edition
./kurulum.sh
```

Betik sistemi tarar ve şunları uyarı olarak gösterecek (VirtualBox'ta normal):

```
! CPU sıcaklık sensörü yok — sanal makinede normaldir
! nvidia-smi yok — GPU hızlandırma kullanılamaz (VirtualBox'ta beklenen)
! Ollama kurulu değil — şimdilik mock model ile çalışacak
```

---

## 5. Demo'yu Çalıştır

### 5.1 Terminal modu

```bash
source .venv/bin/activate
jarvis
```

Sırayla dene:

```
sistem durumu nedir?
ram kullanımı?
hatırla: test_notu = demo kurulumu çalışıyor
ne biliyorsun
çalıştır: uname -a
oku: /etc/os-release
```

Sonra **güvenlik katmanını** dene — bunlar reddedilmeli:

```
çalıştır: curl http://example.com/x.sh    → politika reddi (listede yok)
çalıştır: rm -rf /                         → politika reddi
çalıştır: ls; rm -rf /                     → politika reddi (zincirleme)
çalıştır: systemctl restart ssh            → ONAY sorar (HIGH)
oku: ~/.ssh/id_rsa                         → politika reddi (sır dosyası)
```

Demoda en çok gözlemlemen gereken şey bu: **hangi isteğin sessizce
çalıştığı, hangisinin onay istediği, hangisinin hiç sunulmadığı.**

### 5.2 Canlı panel

```bash
jarvis-panel
```

Tarayıcıda **http://localhost:8765** aç. Göreceklerin:

- **Neural Core** gerçek duruma göre renk ve animasyon değiştirir
  (DÜŞÜNÜYOR → mor, ANALİZ EDİYOR → turkuaz, HAZIR → cyan)
- **System Monitor** gerçek CPU/RAM/disk değerlerini 4 saniyede bir günceller
- Alttaki kutudan yazınca **ajan gerçekten çalışır** ve transkript dolar
- GPU satırı **"yok"** yazar — çünkü gerçekten yok

Panelin demo modundaki durum butonları canlı modda gizlenir; sağ altta
yeşil **"canlı"** rozeti bağlantının kurulduğunu gösterir.

> **Güvenlik:** Panel varsayılan olarak yalnızca `127.0.0.1` dinler. Bu arayüz
> üzerinden terminal komutu çalıştırılabildiği için ağa açmayın. Ana makineden
> erişmek isterseniz VirtualBox **port yönlendirme** kullanın (aşağıda).

### 5.3 Ana makineden panele erişmek (isteğe bağlı)

VirtualBox → Ayarlar → Ağ → Gelişmiş → **Port Yönlendirme**:

| Ad | Protokol | Host IP | Host Portu | Guest IP | Guest Portu |
|---|---|---|---|---|---|
| jarvis | TCP | 127.0.0.1 | 8765 | | 8765 |

Sonra Windows/host tarayıcısından `http://localhost:8765`.
Bu yöntem paneli guest'in ağına açmadığı için `--host` değiştirmekten
güvenlidir.

### 5.4 Ses — panelde konuşan J.A.R.V.I.S.

ElevenLabs bulut API'si olduğu için sanal makinede GPU olmadan sorunsuz çalışır.

> ⚠️ **API anahtarını kimseye göndermeyin** — sohbete, koda veya commit'e
> yazmayın. Yalnızca yerel `.env` dosyasında dursun; o dosya `.gitignore`
> içindedir.

```bash
cp .env.example .env
nano .env
```

İçine kendi bilgilerinizi yazın:

```
ELEVENLABS_API_KEY=sk_kendi_anahtarınız
ELEVENLABS_VOICE_ID=kendi_ses_kimliğiniz
```

Doğrulayın:

```bash
jarvis-ses --kontrol      # anahtar geçerli mi, Voice ID eşleşiyor mu
jarvis-ses --sesler       # Voice ID'yi bilmiyorsanız listeler
```

Sonra paneli başlatın:

```bash
jarvis-panel
```

Artık **panele yazdığınız her soruya sesli cevap verir.** Ses tarayıcıda
çalar — sanal makinede ayrıca ses oynatıcı (ffmpeg) kurmanıza gerek yok,
o yalnızca terminal modu (`jarvis --sesli`) için gerekir.

Panelin sağ altında **SES · AÇIK** düğmesi çıkar; tıklayarak susturabilirsiniz.
Sesi hiç açmadan başlatmak için: `jarvis-panel --sessiz`

**Mikrofon henüz yok** — siz yazarsınız, J.A.R.V.I.S. sesli cevap verir.
Konuşarak sormak (STT) sonraki fazda.

**Ses akış halinde gelir:** cevabın tamamı sentezlenmeyi beklemez, ilk parçada
çalmaya başlar. Yazılı cevap ise sesten önce ekrana düşer — ses gecikirse
okumaya devam edebilirsiniz.

---

## 5.5 J.A.R.V.I.S.'in sizi tanıması

Kimliğiniz **yerel veritabanında** saklanır — kaynak koda yazılmaz, depoya
gönderilmez. Bir kez ayarlarsınız, her açılışta yüklenir.

```bash
jarvis-tanit --kur
```

Soru-cevap ile doldurur. Tek satırda da yapabilirsiniz:

```bash
jarvis-tanit --ad "Adınız Soyadınız" --hitap "Ad, Efendim" \
  --rol "tasarımcısı ve geliştiricisi" --meslek "bilgisayar teknik servisi" \
  --tarz "Teknik ve ayrıntılı; basit sorularda kısa ve net." --bulut evet
```

Kontrol etmek için argümansız çalıştırın:

```bash
jarvis-tanit
```

Bundan sonra J.A.R.V.I.S.:
- Size adınızla ve seçtiğiniz hitapla seslenir
- Bu sistemi sizin tasarladığınızı bilir
- **Teknik servis yaptığınızı bilir** — "bu bilgisayar" dediğinizde kendi
  makineniz mi yoksa üzerinde çalıştığınız cihaz mı olduğunu, belirsizse sorar
- Üzerinde çalıştığı makineyi (CPU/RAM/GPU) tanır

Kimliği silmek için: `jarvis-tanit --sil`

> **Gizlilik:** `--bulut evet` derseniz kimlik, bulut modele giden sistem
> promptunda yer alır. Yalnızca yerelde kalmasını isterseniz `--bulut hayir`.

---

## 6. "Çoğu Konuya Hakim" Olması — Model Seçimi

Mock model zeki değil; yalnızca anahtar kelimeyle doğru aracı seçer. Genel
konularda sohbet edebilmesi için **gerçek bir model** gerekir.

```bash
ollama list                          # kurulu modelleri gör
ollama pull qwen2.5:7b-instruct      # önerilen
```

Panelle birlikte:

```bash
JARVIS_LLM_PROVIDER=ollama JARVIS_OLLAMA_MODEL=qwen2.5:7b-instruct jarvis-panel
```

Kalıcı yapmak için `.env` içine:

```
JARVIS_LLM_PROVIDER=ollama
JARVIS_OLLAMA_MODEL=qwen2.5:7b-instruct
```

### Hangi model?

| Model | Bilgi genişliği | VM'de CPU hızı | Not |
|---|---|---|---|
| `qwen2.5:3b` | Sınırlı | Hızlıca sayılır | Test için |
| **`qwen2.5:7b-instruct`** | **İyi** | Yavaş ama kullanılır | ⭐ Beta için önerilen |
| `qwen2.5:14b-instruct` | Çok iyi | Çok yavaş (VM'de) | Bare-metal + GPU sonrası |

### Dürüst beklenti

VirtualBox'ta GPU yok; model **CPU'da** çalışır. 8 çekirdekle 7B modelde
saniyede birkaç kelime beklemelisiniz — cevabın gelmesi 10–30 saniye
sürebilir. Bu **normaldir ve donanım sorunu değil**, sanallaştırmanın
sonucudur.

Yani betada iki şeyi ayrı değerlendirin:
- **Cevap kalitesi** → şimdi görebilirsiniz, model bilgisi gerçek
- **Cevap hızı** → şimdi göremezsiniz; bare-metal + RTX 3080 Ti ile 10–20 kat
  hızlanacak

Ses tarafı bu yavaşlıktan etkilenmez (ElevenLabs bulutta), ama sesin başlaması
metin cevabının bitmesini bekler.

---

## 7. Demoda Neye Bakmalısın

Bu bir performans testi değil — **davranış** gözlemi. Şu sorulara cevap ara:

1. **Güvenlik katmanı doğru yerde mi duruyor?** Reddedilenler gerçekten
   engelleniyor mu, onay isteyenler mantıklı mı?
2. **Araçlar işine yarıyor mu?** Hangi araç eksik geldi, hangisi gereksizdi?
3. **Panel okunabilir mi?** Hangi bilgi eksik, hangisi fazla?
4. **Hafıza doğru şeyleri mi tutuyor?** Fazla mı kaydediyor, az mı?
5. **Kişilik nasıl?** Çok mu konuşuyor, yeterince net mi?

Bunlar bare-metal kuruluma geçmeden önce düzeltilmesi en ucuz olan şeyler.

Denetim günlüğünü de incele — her kararın kaydı orada:

```bash
cat ~/.jarvis/audit.log.jsonl
```

---

## 8. Demodan Sonra

Gözlemlerin netleştiğinde sıradaki adımlar:

1. Demo geri bildirimlerine göre düzeltmeler
2. **Bare-metal SSD kurulumu** (`DONANIM-VE-KURULUM-PLANI.md`)
3. Gerçek yerel model (14B, GPU'da)
4. STT (faster-whisper) → tam sesli döngü
5. RAG + teşhis motoru

Demo'nun amacı bu sırayı **bilgiye dayanarak** planlamak; tahminle değil.
