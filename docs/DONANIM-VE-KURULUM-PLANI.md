# J.A.R.V.I.S. — Donanım Değerlendirmesi ve Gerçek Kurulum Planı

> Durum: **Planlama.** Kod yok.
> Kapsam: (1) doğrulanmış donanımın yeniden değerlendirmesi, (2) VirtualBox'tan
> çıkıp işletim sistemini gerçek bir SSD'ye kurma planı.

---

## 1. Doğrulanmış Donanım

| Bileşen | Gerçek | Önceki varsayım | Fark |
|---|---|---|---|
| CPU | **AMD Ryzen 7 5800X** (8C/16T) | Ryzen 9 5900X (12C/24T) | 4 çekirdek az |
| GPU | **Zotac RTX 3080 Ti — 12 GB** | RTX 3080 — 10 GB | **+2 GB VRAM** |
| RAM | **32 GB** | 24 GB ayrılmış | +8 GB |

### Bu farklar ne değiştiriyor?

**GPU (+2 GB) — en önemli değişiklik, olumlu.**
10 GB ile 14B modeller "sıkışık, yanına hiçbir şey sığmaz" durumundaydı.
12 GB ile 14B rahat çalışıyor ve ~3 GB boşluk kalıyor. Yani **günlük model
7B değil 14B olabilir** — teknik akıl yürütme ve Türkçe kalitesinde gözle
görülür fark demek.

**CPU (−4 çekirdek) — pratikte önemsiz.**
5800X hâlâ 8 çekirdek / 16 iş parçacığı. Bu iş yükünde asıl yük GPU'da;
CPU embedding, ses ön-işleme ve RAG için fazlasıyla yeterli. 5900X'e göre
kayıp, aynı anda çok sayıda ağır işlem çalıştırmadıkça hissedilmez.

**RAM (+8 GB) — rahatlık.**
32 GB, vektör DB + embedding + uygulama + model tamponları için bol.

### VRAM Bütçesi (12 GB)

| Kombinasyon | Toplam | Durum |
|---|---|---|
| **7B LLM + Whisper large-v3** | ~7.7 GB | ✅ Sesli mod için ideal |
| **14B LLM tek başına** | ~9.0 GB | ✅ Derin analiz için ideal |
| 14B + Whisper | ~12 GB | 🔴 Sınırda, taşar |
| 14B + Whisper + Vision | ~18 GB | ❌ Sığmaz |

**Sonuç:** İki çalışma profili tanımlıyoruz ve model router bunlar arasında
geçiş yapıyor:
- **Sesli mod** → 7B + Whisper birlikte GPU'da
- **Derin analiz** → 14B tek başına; STT/vision o an bulutta

Hibrit mimari hâlâ zorunlu, ama artık daha rahat bir zorunluluk.

---

## 2. Asıl Hedef: VirtualBox'tan Gerçek Kuruluma

### Neden şart
VirtualBox NVIDIA CUDA'yı guest'e geçirmez. Sanal makine içindeki Linux
`nvidia-smi` çalıştırdığında GPU'yu **göremez**. Yani 3080 Ti'nin 12 GB'ı
VirtualBox içinden **hiç kullanılamıyor** — modeller CPU'da, kullanılamaz
yavaşlıkta çalışır. VirtualBox'un 256 MB "video belleği" ayrı bir şey:
emüle edilmiş 2D masaüstü belleği, CUDA ile ilgisi yok.

**Bare-metal kurulum, yerel AI'nin ön koşuludur.** Bu yapılmadan yerel model
konusu havada kalır.

---

## 3. Kurulum Öncesi Üç Karar

### Karar A — Windows kalacak mı?

| Seçenek | Artı | Eksi |
|---|---|---|
| **Ayrı SSD'ye Linux, Windows dursun** ⭐ | Teknik serviste Windows lazım; her ikisi de tam disk | Bir SSD daha gerekir |
| Tek diske dual-boot (bölümleme) | Yeni disk gerekmez | Bölümleme riski, disk daralır |
| Sadece Linux (Windows silinir) | En temiz | Windows'a ihtiyacın varsa geri dönüş zor |

**Öneri: Ayrı fiziksel SSD.** Sen teknik servisçisin — müşteri işleri,
üretici araçları ve BIOS güncelleme yazılımları çoğunlukla Windows istiyor.
Ayrı disk aynı zamanda **en güvenli dual-boot** yöntemi: her işletim
sisteminin kendi diski ve kendi önyükleyicisi olur, birbirinin boot
kaydını bozamazlar.

### Karar B — Hangi SSD?

| Tip | Hız | Öneri |
|---|---|---|
| **NVMe (M.2, PCIe)** | ~3.500–7.000 MB/s | ⭐ Model yükleme çok daha hızlı |
| SATA SSD | ~550 MB/s | Çalışır, model yükleme yavaş |

**Kapasite hesabı:**

| Kalem | Alan |
|---|---|
| Ubuntu + masaüstü | ~15 GB |
| NVIDIA sürücü + CUDA toolkit | ~6 GB |
| Qwen2.5 14B (Q4) | ~9 GB |
| Qwen2.5 7B (Q4) | ~5 GB |
| Whisper large-v3 | ~3 GB |
| Embedding + vektör DB + RAG dokümanları | ~10 GB |
| Çalışma alanı, günlükler, yedek | ~30 GB |
| **Toplam (rahat)** | **~80 GB** |

**Minimum 500 GB, ideal 1 TB.** Model denemeleri hızla yer yiyor; 250 GB
kısa sürede dolar.

### Karar C — Hangi dağıtım?

**Ubuntu 24.04 LTS** öneriyorum. Gerekçe:
- NVIDIA sürücü desteği en sorunsuz olan dağıtım
- CUDA toolkit resmî paketleri doğrudan var
- Sorun yaşadığında internette en çok çözüm bulacağın dağıtım
- LTS = 5 yıl destek, sürekli sürüm yükseltme derdi yok

Alternatifler: Pop!_OS (NVIDIA sürücüsü kurulu gelir, biraz daha kolay),
Fedora (daha güncel ama NVIDIA tarafı daha zahmetli). İlk bare-metal
kurulumun için **Ubuntu LTS**.

---

## 4. Kurulum Adımları

> ⚠️ **Disk işlemleri geri alınamaz.** Her adımı yapmadan önce hangi diske
> yazdığını doğrula. Yanlış disk seçmek Windows'unu siler.

### Adım 0 — Yedek (atlanamaz)
- Windows tarafındaki önemli verileri **harici diske** yedekle.
- Özellikle: müşteri kayıtları, lisans anahtarları, tarayıcı profilleri.
- Kurulum sırasında yanlış disk seçme ihtimali her zaman vardır.

### Adım 1 — Kurulum medyası
- `ubuntu-24.04-desktop-amd64.iso` indir (ubuntu.com).
- **Rufus** (Windows) veya **balenaEtcher** ile USB'ye yaz (min. 8 GB).
- Rufus'ta bölüm şeması: **GPT**, hedef sistem: **UEFI**.

### Adım 2 — BIOS ayarları
Makineyi yeniden başlat, BIOS'a gir (genelde `Del` veya `F2`):

| Ayar | Değer | Neden |
|---|---|---|
| **Secure Boot** | **Disabled** | NVIDIA sürücüsü imzasız modül yükler; en sık takılınan yer |
| Fast Boot | Disabled | USB'den açılışı engelleyebilir |
| SATA Mode | AHCI | RAID modu Linux'ta diski görünmez yapar |
| Above 4G Decoding | Enabled | GPU için |
| Resizable BAR | Enabled | Performans (opsiyonel) |
| Boot Mode | UEFI (CSM kapalı) | GPT ile uyum |

**Windows tarafında ayrıca:** Denetim Masası → Güç Seçenekleri →
**Hızlı Başlatma'yı (Fast Startup) kapat.** Açık kalırsa Windows diski
"uykuda" bırakır ve Linux'tan erişince dosya sistemi bozulabilir.

### Adım 3 — Kurulum
1. USB'den başlat (boot menüsü genelde `F8`/`F11`/`F12`).
2. **"Try Ubuntu"** ile önce dene — GPU, ağ ve klavye çalışıyor mu gör.
3. Kuruluma geç. Disk adımında **"Something else" / "Başka bir şey"** seç
   — otomatik seçenek yanlış diski kullanabilir.
4. **Yeni SSD'yi seç** (boyutundan ve modelinden teyit et; `lsblk` ile
   kontrol edebilirsin).

**Basit ve yeterli bölümleme (ayrı disk için):**

| Bölüm | Boyut | Tip | Bağlama |
|---|---|---|---|
| EFI | 1 GB | FAT32 | `/boot/efi` |
| Kök | Kalan hepsi | ext4 | `/` |

Swap'ı Ubuntu otomatik dosya olarak oluşturur; 32 GB RAM ile ayrı swap
bölümüne gerek yok (hazırda beklet kullanmayacaksan).

> **Kritik:** "Bootloader kurulacak aygıt" olarak **yeni SSD'yi** seç,
> Windows diskini değil. Böylece iki sistem birbirine dokunmaz; hangisinden
> açacağını BIOS boot menüsünden seçersin.

### Adım 4 — NVIDIA sürücüsü
Kurulum bitip yeniden başlattıktan sonra:

```bash
sudo apt update && sudo apt upgrade -y
ubuntu-drivers devices          # önerilen sürücüyü gösterir
sudo ubuntu-drivers autoinstall # veya: sudo apt install nvidia-driver-550
sudo reboot
```

**Doğrulama — bu komut çalışmadan devam etme:**

```bash
nvidia-smi
```

Çıktıda **"NVIDIA GeForce RTX 3080 Ti"** ve **12288 MiB** görmelisin.
Görüyorsan en zor kısım bitti.

### Adım 5 — CUDA (Ollama için genelde gerekmez)
Ollama kendi CUDA kütüphanelerini getirir; çoğu durumda ayrıca CUDA toolkit
kurmana gerek yok. Derleme/geliştirme yapacaksan:

```bash
sudo apt install nvidia-cuda-toolkit
nvcc --version
```

### Adım 6 — Ollama + model
```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b-instruct     # 12 GB VRAM'e rahat sığar
ollama run qwen2.5:14b-instruct "Merhaba, Türkçe biliyor musun?"
```

Başka bir terminalde `nvidia-smi` çalıştır — VRAM kullanımının yükseldiğini
görmelisin. Görüyorsan **GPU gerçekten kullanılıyor** demektir.

### Adım 7 — J.A.R.V.I.S.
```bash
git clone https://github.com/oguzcankayir54-glitch/jarvis.git
cd jarvis
git checkout claude/jarvis-architecture-analysis-40i73f
./kurulum.sh
```

`.env` içine:
```
JARVIS_LLM_PROVIDER=ollama
JARVIS_OLLAMA_MODEL=qwen2.5:14b-instruct
```

Kurulum betiğinin sistem taraması artık şunu göstermeli:
```
✓ GPU: NVIDIA GeForce RTX 3080 Ti, 12288 MiB
✓ Ollama kurulu — yerel model kullanılabilir
```

---

## 5. Sık Takılınan Yerler

**`nvidia-smi` "command not found" veya "no devices"**
Secure Boot açık kalmış olabilir → BIOS'tan kapat. Ya da sürücü kurulumu
yarım kalmıştır: `sudo apt install --reinstall nvidia-driver-550 && sudo reboot`

**Kurulumdan sonra siyah ekran / açılmıyor**
Açılışta `e` tuşuyla GRUB satırını düzenle, `quiet splash` sonrasına
`nomodeset` ekle, `Ctrl+X` ile aç. Sürücüyü kurunca kalıcı olarak düzelir.

**Windows kayboldu**
Panik yok — diski silmediysen duruyor. BIOS boot menüsünden Windows diskini
seç. Kalıcı liste için: `sudo os-prober && sudo update-grub`

**Ollama modeli CPU'da çalışıyor (çok yavaş)**
`nvidia-smi` ile GPU görünüyor mu bak. Görünmüyorsa sürücü sorunu.
Görünüyor ama kullanılmıyorsa: `ollama ps` ile hangi işlemcide çalıştığını
kontrol et.

**14B model yavaş / VRAM taşıyor**
Aynı anda başka GPU işlemi (tarayıcı donanım hızlandırma, oyun) çalışıyor
olabilir. `nvidia-smi` ile bak. Gerekirse 7B'ye düş.

---

## 6. Kurulum Sonrası Doğrulama Listesi

Şu dördü de ✓ olmadan yerel AI hazır sayılmaz:

- [ ] `nvidia-smi` → RTX 3080 Ti ve 12288 MiB görünüyor
- [ ] `ollama run qwen2.5:14b-instruct` → makul hızda cevap veriyor
- [ ] Model çalışırken `nvidia-smi` → VRAM kullanımı yükseliyor
- [ ] `./kurulum.sh` → sistem taramasında GPU ve Ollama ✓

---

## 7. Bundan Sonra Ne Değişir

Bare-metal kurulum tamamlandığında:

| Şu an (VirtualBox) | Kurulumdan sonra |
|---|---|
| GPU kullanılamıyor | 12 GB VRAM tam kullanımda |
| Yerel model pratikte imkânsız | 14B model rahat çalışıyor |
| Sensör/SMART okuması kısıtlı | Gerçek donanım telemetrisi |
| Mock model ile test | Gerçek yerel model |

Ayrıca J.A.R.V.I.S.'in **kendi sistem araçları da anlamlanır**: gerçek CPU
sıcaklığı, gerçek GPU sıcaklığı ve VRAM, gerçek SMART verisi. Sanal makinede
bunların çoğu "mevcut değil" dönüyordu.

**Sonraki faz:** STT (faster-whisper) — mikrofondan konuşup sesli cevap
almak. Bu, GPU'nun gerçekten kullanılabilir olmasını gerektiriyor; yani
bu kurulum onun da ön koşulu.
