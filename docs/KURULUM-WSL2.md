# J.A.R.V.I.S. — WSL2 Kurulumu (Windows + RTX 3080 Ti)

> Amaç: Windows'u kaybetmeden, yeni disk almadan **GPU'yu gerçekten kullanmak.**
> Süre: ~30 dakika (model indirme hariç).

---

## Neden WSL2

VirtualBox NVIDIA CUDA'yı geçirmez; WSL2 geçirir. NVIDIA bunu resmen destekler:
Windows sürücüsü kuruluysa WSL2 içindeki Linux, RTX 3080 Ti'nin **12 GB'ını tam
olarak** kullanır.

| | VirtualBox | WSL2 | Bare-metal |
|---|---|---|---|
| GPU / CUDA | ❌ | ✅ | ✅ |
| Yeni SSD | — | ❌ gerekmez | ✅ gerekir |
| Windows aynı anda | ✅ | ✅ | ❌ |
| CPU sıcaklık sensörü | ❌ | ❌ | ✅ |
| Fiziksel disk SMART | ❌ | ❌ | ✅ |

**Bilerek kabul ettiğimiz kayıp:** WSL2 donanım sensörlerini vermez. GPU
istisna (`nvidia-smi` çalışır), ama CPU sıcaklığı ve fiziksel disk SMART
verisi okunamaz. Bu zaten VirtualBox'ta da yoktu — yani gerileme değil,
mevcut durumun üstüne GPU eklemek.

---

## ⚠️ En Kritik Kural

> **WSL içine NVIDIA sürücüsü KURMAYIN.**

WSL2'de GPU, **Windows'taki sürücü** üzerinden gelir. İçeride ayrıca
`nvidia-driver` kurmaya çalışmak çalışan kurulumu bozar. Bu, WSL2 + CUDA
konusunda en sık yapılan hatadır.

İçeride kurulacak tek şey (gerekirse) CUDA **toolkit**'tir — sürücü değil.
Ollama kullanacaksanız ona bile gerek yok.

---

## Adım 1 — Windows Hazırlığı

**Gereken:** Windows 11, veya Windows 10 sürüm 21H2 ve üzeri.

Kontrol: `Win + R` → `winver` → Enter.

**NVIDIA sürücüsünü güncelleyin.** WSL2'de CUDA için güncel bir Windows
sürücüsü şart. GeForce Experience'tan veya nvidia.com/drivers adresinden
son sürümü kurun.

Windows'ta doğrulayın (PowerShell):

```powershell
nvidia-smi
```

RTX 3080 Ti ve 12288 MiB görmelisiniz. Windows'ta çalışmıyorsa WSL2'de de
çalışmaz — önce burayı düzeltin.

---

## Adım 2 — WSL2 Kurulumu

**PowerShell'i yönetici olarak açın** (Başlat → PowerShell → sağ tık →
"Yönetici olarak çalıştır"):

```powershell
wsl --install
```

Bu komut WSL2'yi ve Ubuntu'yu kurar. **Bilgisayarı yeniden başlatın.**

Yeniden başlattıktan sonra Ubuntu penceresi otomatik açılır ve sizden
kullanıcı adı + parola ister. (Bu parola Windows parolanızdan bağımsızdır;
`sudo` için kullanılır.)

WSL zaten kuruluysa güncelleyin:

```powershell
wsl --update
wsl --set-default-version 2
```

---

## Adım 3 — GPU Doğrulaması (Geçilmemesi Gereken Kontrol)

Ubuntu (WSL) terminalinde:

```bash
nvidia-smi
```

**Görmeniz gereken:**

```
+-----------------------------------------------------------------------------+
| NVIDIA-SMI 5xx.xx    Driver Version: 5xx.xx    CUDA Version: 12.x            |
|   0  NVIDIA GeForce RTX 3080 Ti    ...    12288MiB                           |
+-----------------------------------------------------------------------------+
```

**Bu çalışmadan devam etmeyin.** Çalışmıyorsa:
- Windows'ta `nvidia-smi` çalışıyor mu? (Adım 1)
- `wsl --update` çalıştırıp WSL'i yeniden başlattınız mı? (`wsl --shutdown`)
- WSL sürüm 2 mi? → `wsl -l -v` çıktısında VERSION sütunu **2** olmalı

---

## Adım 4 — Bellek Ayarı (İsteğe Bağlı)

WSL2 varsayılan olarak Windows RAM'inin yarısını kullanabilir. 32 GB'ta bu
16 GB demek — 14B model için yeterli. Daha fazlasını ayırmak isterseniz
Windows'ta `C:\Users\<kullanıcı>\.wslconfig` dosyası oluşturun:

```ini
[wsl2]
memory=24GB
processors=8
```

Sonra: `wsl --shutdown` ve WSL'i yeniden açın.

---

## Adım 5 — Ollama ve Model

WSL içinde:

```bash
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5:14b-instruct
```

> 12 GB VRAM ile **14B model rahat çalışır** (~9 GB). VirtualBox'ta
> mecbur kaldığımız 3B/7B'ye artık gerek yok.

Test edin:

```bash
ollama run qwen2.5:14b-instruct "Merhaba, kısaca kendini tanıt."
```

**Başka bir WSL terminalinde** `nvidia-smi` çalıştırın — VRAM kullanımının
yükseldiğini görmelisiniz. Görüyorsanız **GPU gerçekten kullanılıyor**
demektir; bu, tüm kurulumun asıl kanıtıdır.

Cevap hızı VirtualBox'takinden **10–20 kat** daha iyi olmalı.

---

## Adım 6 — J.A.R.V.I.S.

```bash
sudo apt update
sudo apt install -y git python3 python3-venv python3-pip

git clone --branch feat/complete-project-sync https://github.com/oguzcankayir54-glitch/JARVIS-Windows-Production-Edition.git
cd JARVIS-Windows-Production-Edition
./kurulum.sh
```

Kurulum betiğinin sistem taraması artık şunu göstermeli:

```
✓ GPU: NVIDIA GeForce RTX 3080 Ti, 12288 MiB
✓ Ollama kurulu — yerel model kullanılabilir
! CPU sıcaklık sensörü yok — sanal makinede normaldir
```

> Depo gizliyse `git clone` sizden kimlik doğrulama isteyebilir. GitHub
> kullanıcı adınız ve **personal access token**'ınızla giriş yapın (parola
> değil). Token: github.com → Settings → Developer settings → Personal
> access tokens.

---

## Adım 7 — Yapılandırma

```bash
cp .env.example .env
nano .env
```

İçine:

```
JARVIS_LLM_PROVIDER=ollama
JARVIS_OLLAMA_MODEL=qwen2.5:14b-instruct
ELEVENLABS_API_KEY=kendi_anahtarınız
ELEVENLABS_VOICE_ID=kendi_ses_kimliğiniz
```

Kaydet: `Ctrl+O` → `Enter` → `Ctrl+X`

Kimliğinizi tanıtın:

```bash
source .venv/bin/activate
jarvis-tanit --kur
```

---

## Adım 8 — Çalıştırın

```bash
jarvis-panel
```

Sonra **Windows tarayıcınızdan** açın:

```
http://localhost:8765
```

> **Güzel taraf:** WSL2 `localhost`'u Windows'a yönlendirir. Yani panel WSL
> içinde çalışır ama Windows tarayıcınızda açılır — **ses de Windows
> hoparlöründen çalar.** WSL içinde ses kurulumuyla uğraşmanıza gerek yok.

---

## Doğrulama Listesi

Dördü de ✓ olmadan kurulum tamam sayılmaz:

- [ ] WSL içinde `nvidia-smi` → RTX 3080 Ti, 12288 MiB
- [ ] `ollama run qwen2.5:14b-instruct` → makul hızda cevap
- [ ] Model çalışırken `nvidia-smi` → VRAM kullanımı yükseliyor
- [ ] `jarvis-panel` → Windows tarayıcısında açılıyor ve sesli cevap veriyor

---

## Sık Karşılaşılanlar

**WSL'de `nvidia-smi: command not found`**
Windows sürücüsü eski. Güncelleyin, sonra `wsl --shutdown` ile WSL'i
yeniden başlatın. **WSL içine sürücü kurmayın.**

**`wsl --install` "geçersiz komut" diyor**
Windows sürümünüz eski. `winver` ile kontrol edin; Windows 10 21H2 altındaysa
önce Windows'u güncelleyin.

**Ollama modeli CPU'da çalışıyor (yavaş)**
`nvidia-smi` GPU'yu gösteriyor mu? Göstermiyorsa Adım 3'e dönün. Gösteriyorsa
`ollama ps` ile hangi işlemcide çalıştığına bakın.

**Model çok yavaş / VRAM taşıyor**
Aynı anda Windows'ta oyun veya GPU kullanan başka uygulama olabilir.
`nvidia-smi` ile kontrol edin. Gerekirse 7B modele düşün.

**Panel Windows tarayıcısında açılmıyor**
`http://localhost:8765` yerine `http://127.0.0.1:8765` deneyin. Olmazsa WSL
içinde `hostname -I` ile IP alıp onu kullanın.

**Ses gelmiyor**
Panel Windows tarayıcısında açıksa ses Windows üzerinden çalar — WSL ses
ayarıyla ilgisi yok. Tarayıcı sekmesinde sustur işareti var mı bakın.

---

## Bundan Sonra

WSL2 ile GPU'ya kavuştunuz. Sırada:

1. **14B modelle gerçek kullanım** — kalite ve hız artık gerçek
2. **STT (faster-whisper)** — GPU olduğu için artık pratik; konuşarak sorma
3. **RAG** — teknik doküman tabanı
4. **Bare-metal kararı** — sensörler gerçekten lazım mı, artık bilgiyle
   karar verirsiniz (`DONANIM-VE-KURULUM-PLANI.md`)
