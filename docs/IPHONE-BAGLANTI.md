# J.A.R.V.I.S. — iPhone Bağlantısı

> Amaç: Telefondan J.A.R.V.I.S. ile yazışmak, konuşarak sormak ve sesli cevap
> almak. Panel ana ekrana kurulabilen bir web uygulaması olarak çalışır.

---

## Önce: Neden native uygulama değil?

Mimari planda (spec §7) özel bir iOS uygulaması vardı. Şimdilik **panelin
kendisini** kullanıyoruz, çünkü:

- Panel zaten bir web uygulaması; iPhone Safari'de çalışır
- **iOS uygulaması derlemek için Mac gerekir** — sende Windows var
- Apple Developer Program (~$99/yıl) gerekir
- Aynı sonuca bugün, sıfır maliyetle ulaşılıyor

Ana ekrana eklenince neredeyse uygulama gibi durur (tam ekran, kendi simgesi).
Native uygulama, mikrofon ve arka plan çalışma gerektiğinde anlamlı olacak.

---

## ⚠️ Güvenlik: Bu adımı hafife almayın

Panel üzerinden **terminal komutu çalıştırılabiliyor.** Ağa açmak demek,
o ağdaki herkesin makinenizi kontrol edebilmesi demek — misafir cihazlar,
ele geçirilmiş bir IoT cihazı, komşu Wi-Fi'sine sızmış biri dahil.

Bu yüzden ağa açıldığında **erişim jetonu zorunludur**. Panel jetonu
otomatik üretir ve başlarken yazar. Jeton olmadan sayfa açılmaz.

**Kurallar:**
- Jetonu kimseyle paylaşmayın; ekran görüntüsüne almayın
- Yalnızca **kendi ev ağınızda** kullanın; kafe/otel Wi-Fi'sinde açmayın
- İşiniz bitince paneli kapatın (`Ctrl+C`)
- Herkese açık bir ağda kullanmanız gerekirse **VPN** (Tailscale) tercih edin

---

## Adım 1 — Paneli ağa aç (WSL içinde)

```bash
cd ~/jarvis
source .venv/bin/activate
jarvis-panel --host 0.0.0.0
```

Çıktıda jeton görünecek:

```
  Bu adresi kullanın (jeton dahil):
    http://localhost:8765/?token=q8U-2NC9TPA5xDGE

  WSL2 tespit edildi. Telefon bu adrese ULAŞAMAZ —
  WSL'in kendi ağıdır (172.x.x.x). Telefon için
  Windows tarafında port yönlendirme gerekir.
```

**Jetonu bir kenara not edin** — birazdan lazım.

---

## Adım 2 — WSL2 port yönlendirmesi (Windows tarafında)

Bu adım şart. WSL2'nin kendi sanal ağı vardır; telefon doğrudan ulaşamaz.
Windows'un gelen bağlantıyı WSL'e iletmesi gerekir.

### Kolay yol: hazır betik

**PowerShell'i yönetici olarak açın** ve:

```powershell
cd \\wsl$\Ubuntu\home\KULLANICI\jarvis\scripts
powershell -ExecutionPolicy Bypass -File .\windows-yonlendirme.ps1
```

(`KULLANICI` yerine WSL kullanıcı adınız.)

Betik güncel WSL IP'sini kendisi bulur, kuralı yeniler, `iphlpsvc` servisini
kontrol eder, güvenlik duvarı kuralını ekler ve sonucu **sınar.** WSL her
yeniden başladığında aynı komutu çalıştırmanız yeterli.

Kaldırmak için: `.\windows-yonlendirme.ps1 -Kaldir`

### Elle yol

**PowerShell'i yönetici olarak açın:**

```powershell
# 1) WSL'in güncel IP'sini al
$wsl = (wsl hostname -I).Trim().Split(" ")[0]
echo "WSL IP: $wsl"

# 2) Eski kuralı temizle, yenisini kur
netsh interface portproxy delete v4tov4 listenport=8765 listenaddress=0.0.0.0 2>$null
netsh interface portproxy add v4tov4 listenport=8765 listenaddress=0.0.0.0 connectport=8765 connectaddress=$wsl

# 3) Windows Güvenlik Duvarı'nda portu aç
New-NetFirewallRule -DisplayName "JARVIS Panel" -Direction Inbound -LocalPort 8765 -Protocol TCP -Action Allow -Profile Private

# 4) Kontrol
netsh interface portproxy show v4tov4
```

> **Önemli:** `-Profile Private` bilinçli bir seçim — kural yalnızca "özel ağ"
> olarak işaretlenmiş ağlarda (ev ağınız) geçerli olur, halka açık ağlarda
> otomatik kapalı kalır.

> **WSL IP'si her yeniden başlatmada değişir.** Windows'u veya WSL'i yeniden
> başlattıysanız 1. ve 2. adımı tekrar çalıştırın.

---

## Adım 3 — Windows'un IP adresini bul

```powershell
ipconfig | Select-String "IPv4"
```

`192.168.1.x` gibi bir adres göreceksiniz — telefonun bağlanacağı adres bu.

---

## Adım 4 — iPhone'dan aç

iPhone'un **aynı Wi-Fi ağında** olduğundan emin olun. Safari'de:

```
http://192.168.1.X:8765/?token=JETONUNUZ
```

(`192.168.1.X` yerine 3. adımdaki adres, `JETONUNUZ` yerine 1. adımdaki jeton.)

Jeton bir kez girildikten sonra çerez olarak saklanır; sonraki açılışlarda
adresin sade hali yeterlidir.

---

## Adım 5 — Ana ekrana ekle (uygulama gibi görünsün)

Safari'de sayfa açıkken:

1. Alttaki **Paylaş** simgesine dokunun
2. **Ana Ekrana Ekle**
3. İsim: `J.A.R.V.I.S.`

Artık ana ekranda kendi simgesiyle durur, tam ekran açılır ve Safari arayüzü
görünmez.

Kurulan uygulamanın başlangıç adresine erişim jetonu yazılmaz. İlk yetkili
ziyarette kaydedilen çerez kullanılır; çerezin süresi dolarsa uygulamayı
Safari'de jetonlu adresle bir kez yeniden açın.

## Mikrofonla konuşarak sorma

Mikrofon düğmesi yalnızca güvenli tarayıcı bağlamında çalışır. `localhost`
dışındaki düz `http://192.168...` adreslerinde iOS mikrofon izni vermez.
Telefondan konuşarak sormak için paneli Tailscale HTTPS ya da eşdeğer geçerli
bir HTTPS adresi üzerinden açın. Yazışma ve sesli cevap düz ev ağı adresinde
çalışmaya devam eder.

---

## Ses hakkında

iOS ses için **kullanıcı hareketi** ister. İlk cevapta ses gelmezse panelde
**"▶ SESİ ÇAL"** düğmesi çıkar; bir kez dokunduktan sonra sonraki cevaplar
kendiliğinden çalar.

Telefonun **sessiz modda** olmadığından ve ses seviyesinin açık olduğundan
emin olun.

---

## Telefon görünümü

Panel dar ekranda otomatik olarak dikey düzene geçer:

1. Neural Core (durum göstergesi)
2. Konuşma + yazma kutusu
3. Sistem telemetrisi
4. Diagnostic / Brain Monitor

Yatay kokpit düzeni yalnızca geniş ekranlarda kullanılır.

---

## Sık karşılaşılanlar

**`ERR_CONNECTION_RESET` — bilgisayarın kendisinden bile açılmıyor**
Bu "ulaşılamıyor" değil, **kabul edildi sonra koptu** demek. Neredeyse her
zaman **bayat yönlendirme kuralı**: kural `0.0.0.0:8765` dinlediği için
`localhost:8765`'i de o yakalıyor, ama WSL yeniden başladığında IP değiştiği
için artık ölü bir adrese gönderiyor. Panel çalışsa bile ulaşamazsınız.

Düzeltmesi Adım 2'deki betiği yeniden çalıştırmak. Kontrol için:

```powershell
netsh interface portproxy show v4tov4; wsl hostname -I
```

`connectaddress` ile alttaki IP farklıysa teşhis doğrudur.

**Sayfa açılmıyor / zaman aşımı**
- iPhone ve bilgisayar aynı Wi-Fi'de mi?
- Port yönlendirme kuruldu mu? `netsh interface portproxy show v4tov4`
- WSL yeniden mi başladı? IP değişmiştir — Adım 2'yi tekrarlayın
- Windows Güvenlik Duvarı kuralı var mı?
- Ağınız Windows'ta "Genel" olarak işaretliyse kural uygulanmaz; "Özel"e alın
- `iphlpsvc` servisi çalışıyor mu? Durmuşsa kural listede görünür ama hiçbir
  şey yapmaz: `Get-Service iphlpsvc`

**"Erişim jetonu gerekli" sayfası**
Adreste `?token=...` kısmı eksik veya jeton yanlış. Terminaldeki adresi
olduğu gibi kullanın.

**Panel açılıyor ama cevap gelmiyor**
`jarvis-panel` terminalinde hata var mı bakın. Model yüklenirken ilk cevap
10-20 saniye sürebilir.

**Ses yok**
"▶ SESİ ÇAL" düğmesine bir kez dokunun. Telefon sessiz modda olmasın.

---

## İşiniz bitince

```powershell
# Yönlendirmeyi kaldır (isteğe bağlı ama temiz)
netsh interface portproxy delete v4tov4 listenport=8765 listenaddress=0.0.0.0
Remove-NetFirewallRule -DisplayName "JARVIS Panel"
```

Paneli `Ctrl+C` ile kapatmak da erişimi keser.

---

## Mikrofon: neden telefonda henüz çalışmıyor

STT (konuşmayı metne çevirme) **hazır** — kurulumu `docs/MIKROFON.md`
anlatıyor. Masaüstü tarayıcıda `localhost` üzerinden bugün çalışıyor.

Telefonda çalışmamasının tek nedeni **HTTPS**: iOS Safari, güvenli olmayan
bir bağlantıda mikrofonu hiç vermiyor. Panel açılır, yazışma çalışır, ses
cevabı gelir — ama 🎙 düğmesi "güvenli bağlantı gerekli" der.

Kendi imzaladığınız bir sertifika iOS'ta yeterli olmuyor; gerçek bir
sertifika gerekiyor. Pratik yol **Tailscale**, çünkü üç derdi birden
bitiriyor:

1. Tarayıcının güvendiği gerçek HTTPS sertifikası (`tailscale cert`)
2. Bu dosyadaki port yönlendirme adımlarının tamamı gereksiz hale gelir —
   WSL'in her açılışta değişen IP'si de dahil
3. Ev ağı dışından erişim (serviste, yolda) — güvenlik duvarında delik
   açmadan

Bu kurulum ayrı bir adım olarak yapılacak.
