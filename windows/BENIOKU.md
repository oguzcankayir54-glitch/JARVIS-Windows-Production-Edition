# J.A.R.V.I.S. — Windows başlatıcı

> Masaüstündeki simgeye çift tıkla, panel açılsın. Terminal, `cd`, `source`,
> `jarvis-panel` yok.

---

> **Aşağıdaki her kod bloğunun başında nereye yazılacağı yazıyor.** Bir
> Windows yolu ya da ayar dosyası satırını WSL kabuğuna yapıştırmak
> `command not found` verir — komut değiller.

## Yeni sürümü nereden indiririm?

**[INDIRME.md](../INDIRME.md)** — hazır `JARVIS-Setup-2.0.1.exe` indirme
adresi, SHA-256 doğrulaması ve kaynak kurulum seçeneği.

---

## Kurulum

İki yol var; ikisi de aynı şeyi yapar.

### A) WSL kabuğundan (zaten oradaysanız en kısası)

**WSL bash'e yazın:**

```bash
cd ~/jarvis
./windows/kur.sh
```

### B) Windows'tan

**Windows Gezgini'nin adres çubuğuna yapıştırın** (komut satırına değil):

```
\\wsl$\Ubuntu\home\administrator\jarvis\windows
```

`administrator` yerine kendi WSL kullanıcı adınız gelir; bilmiyorsanız WSL
bash'te `whoami` yazın. Açılan klasörde **`Kur.cmd`** dosyasına çift tıklayın.

---

Her iki yolda da sonuç aynı: masaüstünde **JARVIS** simgesi belirir.

Yönetici hakkı gerekmez — her şey kendi kullanıcı profilinize kurulur
(`%LOCALAPPDATA%\Programs\JARVIS`).

Kurulum sadece dosya kopyalamıyor; şunları da yapıyor:

- **WSL dağıtımınızı bulur** (`Ubuntu`, `Ubuntu-22.04`, …) ve ayarlara yazar
- **Proje klasörünü arar** (`~/jarvis`, `~/projeler/jarvis`, `~/Projects/jarvis`)
- **`jarvis-panel` kurulu mu diye bakar** — değilse ne yapmanız gerektiğini söyler

Yani bir şey eksikse bunu ilk çift tıklamada değil, kurulumda öğrenirsiniz.

---

## Kullanım

Simgeye çift tıklayın. Açılan pencerede:

```
============================================================
  J.A.R.V.I.S.  ·  Baslatici
============================================================
  Port     : 8765
  Dagitim  : Ubuntu
  Klasor   : ~/jarvis
============================================================

  Durdurmak icin: bu pencereyi kapatin veya Ctrl-C
  Panel baslatiliyor (ilk acilis biraz surebilir)...

  [panelin kendi çıktısı buradan akar]

  > Panel hazir, tarayici aciliyor...
```

Panel hazır olunca tarayıcı **kendiliğinden** açılır.

**Durdurmak:** pencereyi kapatın veya Ctrl-C. Panel de durur.

**Zaten açıksa:** ikinci kez tıklarsanız yeni bir kopya başlatmaz — sadece
tarayıcıyı açar.

---

## Ayarlar

`%LOCALAPPDATA%\Programs\JARVIS\jarvis.ini`

| Anahtar | Varsayılan | Ne işe yarar |
|---------|------------|--------------|
| `dagitim` | (kurulumda bulunur) | Hangi WSL dağıtımı |
| `klasor` | `~/jarvis` | Proje klasörü (WSL içindeki yol) |
| `port` | `8765` | Panelin portu |
| `tarayici` | `1` | `0` yaparsanız tarayıcı açılmaz |
| `uygulama` | `1` | Kendi penceresinde aç (sekme/adres çubuğu yok) |
| `intro` | `1` | ~10 saniyelik açılış girişi; `0` = doğrudan panel |
| `watchdog` | `0` | `1` yaparsanız çöken paneli arka planda yeniden başlatır |
| `jeton` | (bir kez üretilir) | Erişim jetonu — **sabittir**, değişmez |
| `komut` | (boş) | Başlatma komutunu tamamen değiştirir |

Kamerayı da açarak başlatmak isterseniz, **`jarvis.ini` dosyasını Not
Defteri'yle açıp** içindeki `komut` satırını şöyle yapın — bu bir kabuk
komutu değil, dosyanın içeriği:

```ini
komut = cd ~/jarvis && . .venv/bin/activate && exec jarvis-panel --kamera
```

Dosyayı WSL'den düzenlemek isterseniz **WSL bash'e**:

```bash
nano "$(wslpath "$(cmd.exe /c echo %LOCALAPPDATA% 2>/dev/null | tr -d '\r')")/Programs/JARVIS/jarvis.ini"
```

> `komut` satırında **çift tırnak kullanmayın.** Bütün betik Windows komut
> satırında çift tırnak içinde gidiyor; fazladan bir tane ayrıştırmayı bozar.

Dosyayı değiştirdikten sonra pencereyi kapatıp yeniden başlatın.

---

## Uygulama penceresi

Panel bir tarayıcı sekmesinde değil, **kendi penceresinde** açılıyor: sekme
şeridi yok, adres çubuğu yok, görev çubuğunda kendi girişi ve kendi simgesi
var. Edge veya Chrome'un `--app` kipini kullanıyor — Edge Windows 10/11'de
zaten kurulu olduğu için ek bir şey gerekmiyor.

Kendi profiliyle çalışıyor (`%LOCALAPPDATA%\JARVIS\pencere`), yani normal
gezinmenize, sekmelerinize ve oturumlarınıza hiç dokunmuyor.

Simge panelin sunduğu `/favicon.ico`'dan geliyor; masaüstü kısayoluyla aynı
görsel.

Hiçbir Chromium tarayıcısı bulunamazsa varsayılan tarayıcıda sekme olarak
açılıyor — pencere süslemesi için paneli hiç açmamak saçma olurdu.

Kapatmak için `jarvis.ini` içinde `uygulama = 0`.

---

## Açılış girişi

Simgeye tıkladıktan sonra ~10 saniyelik bir giriş geliyor: J.A.R.V.I.S.
yazısı, dönen halkalar ve bir açılış kaydı.

O kayıt **uydurma değil.** Satırlar panelin sunucudan aldığı gerçek veriden
doluyor:

```
› çekirdek başlatılıyor
› güvenlik katmanı etkin
› sunucu bağlandı
› model qwen2.5:14b-instruct
› araçlar 24 · izinli
› hafıza 3 katman
› bilgi tabanı 81 belge
› ses piper
› sistem HAZIR
```

Panel zaten o sırada sunucuya bağlanıp bunları öğreniyordu; giriş bekleme
süresini gizlemek yerine gösteriyor.

**Geçmek için** tıklayın veya Esc/Enter/boşluk. Hiç istemiyorsanız
`jarvis.ini` içinde `intro = 0`.

---

## Jeton nasıl hallediliyor

`.env` dosyanızda `JARVIS_PANEL_TOKEN` varsa panel jeton istiyor. Başlatıcı
bunu tahmin etmeye çalışmıyor — **kendisi belirliyor:** ilk açılışta bir jeton
üretip `jarvis.ini` içine yazıyor, panele `--jeton` ile veriyor ve aynı değeri
adrese koyuyor. `--jeton`, `.env`'deki değeri geçersiz kıldığı için ikisi her
zaman örtüşüyor.

**Jeton bir kez üretilir ve bir daha değişmez.** Adres sabit: yer imine
ekleyebilirsiniz, tarayıcıda açık duran eski sekme çalışmaya devam eder.
Değiştirmek isterseniz `jarvis.ini` içindeki `jeton =` satırını boşaltın;
bir sonraki açılışta yenisi üretilir.

Paneli **başka bir pencereden** başlattıysanız başlatıcı onun jetonunu
bilemez. O durumda sessizce yanlış adres açmak yerine bunu söylüyor:

```
  ! Calisan panel jeton istiyor ve jetonu bu baslatici uretmedi.
    Paneli baslattiginiz penceredeki adresi kullanin,
    veya o pencereyi kapatip buradan yeniden baslatin.
```

---

## Neden "port açık" yetmiyor

Başlatıcı, panelin hazır olduğunu **portun açık olmasından** değil, `/health`
adresine attığı istekten anlıyor. Sebebi somut:

WSL2'de bayat bir `netsh portproxy` kaydı aynı portu `0.0.0.0` üzerinden
dinlemeye devam ediyor. TCP bağlantısı açılıyor, panel ölü olduğu halde "hazır"
görünüyor — ve tarayıcı boş bir sayfaya açılıyor. Cevabı okumak bu tuzağı
eliyor.

Bu senaryo test edildi: 8765'te cevap vermeyen bir dinleyici varken başlatıcı
"zaten çalışıyor" demiyor, paneli başlatmaya devam ediyor.

---

## Kaldırma

```
Kur.cmd /kaldir
```

Kısayolları ve kurulum klasörünü siler. **WSL içindeki J.A.R.V.I.S. projesine
dokunmaz** — kodunuz, hafızanız ve bilgi tabanınız yerinde kalır.

---

## Sık karşılaşılanlar

**"wsl.exe bulunamadi"**
WSL kurulu değil. Yönetici PowerShell'de: `wsl --install`

**"HATA: ~/jarvis klasoru bulunamadi"**
`jarvis.ini` içindeki `klasor` satırını düzeltin. WSL'de nerede olduğunu
görmek için: `wsl -- bash -lc 'ls -d ~/jarvis'`

**"HATA: jarvis-panel bulunamadi"**
WSL içinde kurulum tamamlanmamış:
```bash
cd ~/jarvis && source .venv/bin/activate && pip install -e .
```

**Pencere hemen kapanıyor**
Kapanmıyor olması gerekir — panel hata verirse pencere bir tuşa basılana kadar
bekler. Yine de kaçırıyorsanız `JARVIS.exe`'yi bir PowerShell penceresinden
çalıştırın, çıktı orada kalır.

**`ERR_CONNECTION_RESET` / "Bu siteye ulaşılamıyor"**
Panel çalışıyor ama Windows ona ulaşamıyor. Neredeyse her zaman sebebi bayat
bir `netsh portproxy` kaydı: WSL'in IP'si her açılışta değişiyor, kural eski
adreste kalıyor, ve `0.0.0.0`'ı dinlediği için **localhost dahil** her isteği
yakalayıp ölü bir adrese gönderiyor.

Başlatıcı bunu ~7 saniyede fark edip söylüyor. Çözüm — **yönetici
PowerShell'e**:

```powershell
netsh interface portproxy delete v4tov4 listenport=8765 listenaddress=0.0.0.0
```

Telefondan da bağlanmak istiyorsanız silmek yerine güncelleyin (yönetici
PowerShell'de, `<kullanıcı>` yerine kendi adınız):

```powershell
powershell -ExecutionPolicy Bypass -File \\wsl$\Ubuntu\home\<kullanıcı>\jarvis\scripts\windows-yonlendirme.ps1
```

**Tarayıcıda "Erişim jetonu gerekli" sayfası çıkıyor**
Panel başka bir pencereden başlatılmış olabilir; başlatıcı onun jetonunu
bilemez. O pencereyi kapatıp simgeden yeniden başlatın, ya da o penceredeki
adresi kullanın.

**Tarayıcı açılmıyor ama panel çalışıyor**
`jarvis.ini` içinde `tarayici = 0` olabilir. Elle: `http://localhost:8765`

**Simge görünmüyor / yanlış simge**
Windows simge önbelleği bazen takılır. Masaüstünde F5, olmazsa:
`ie4uinit.exe -show`

---

## Geliştirici notu — yeniden derlemek

`.exe` depoya derlenmiş olarak konuyor ki kullanan kişi derleyici kurmak
zorunda kalmasın. Kaynağı değiştirirseniz WSL/Linux içinde:

```bash
sudo apt install mingw-w64
cd windows/src
python ikon_yap.py     # logo.svg → jarvis.ico (9 boyut)
./yap.sh               # → windows/JARVIS.exe
```

`ikon_yap.py` her boyutu SVG'den ayrı çiziyor (4× süperörnekleme ile);
tek bir büyük görüntüyü küçültmek 16 pikselde parlamayı gri bulamaca
çeviriyor — ve 16 piksel tam da görev çubuğunun kullandığı boyut.
