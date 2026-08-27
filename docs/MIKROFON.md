# J.A.R.V.I.S. — Mikrofon (yerel STT)

> Konuşarak sormak. Ses kaydı **bu makinede** çözümlenir; hiçbir buluta
> gönderilmez.

---

## Neden yerel?

Cevap gerektiğinde bulut modeline gidebilir, ama **ham ses gitmez.** Sesiniz
sistemdeki en kişisel veri; onu dışarı çıkarmamak bilinçli bir seçim
(mimari §6). Çözümlemeyi `faster-whisper` yapıyor: Whisper modelinin
CTranslate2 üzerinde çalışan, PyTorch gerektirmeyen sürümü.

---

## Kurulum

```bash
cd ~/jarvis
source .venv/bin/activate
pip install faster-whisper
```

Bu kadar. Model dosyası ilk kullanımda kendiliğinden iner (birkaç yüz MB) ve
`~/.cache/huggingface` altında saklanır — sonraki açılışlarda tekrar inmez.

**faster-whisper kurulmazsa J.A.R.V.I.S. yine çalışır**, yalnızca mikrofon
kapalı olur ve panel bunu söyler. Yazarak sormak etkilenmez.

---

## Doğrulama

```bash
jarvis-panel
```

Başlangıç çıktısında görmeniz gereken satır:

```
  Mikrofon : faster-whisper · small · cuda
```

`kapalı` yazıyorsa hemen altındaki not nedenini söyler.

Panelde yazı kutusunun solunda **🎙** düğmesi çıkar.

---

## İki kip, tek düğme

### Sohbet — tıkla

Düğmeye **bir kez** dokunun (**◉** olur) ve konuşmaya başlayın. Sustuğunuzda
cevap gelir; konuşmaya devam edin, sohbet sürer. Bitirmek için tekrar dokunun.

Söyledikleriniz **yazı kutusuna yazılmaz** ve tuşa basmanız gerekmez. Cümlenin
bittiğini sessizlik belirliyor — yaklaşık bir saniye.

J.A.R.V.I.S. konuşurken mikrofon kapalı. Açık bırakmak, kendi cevabını duyup
kendine cevap vermesi demek olurdu.

### Yazdır — Shift+tıkla

Eski davranış: konuşun, tekrar dokunun (düğme **■**), duyulan cümle yazı
kutusuna düşer. Göndermeden önce okuyup düzeltebilirsiniz. Gürültülü bir
ortamda ya da uzun bir komutu tam olarak vermek istediğinizde daha iyi.

---

## Sohbet kipi neyi feda ediyor?

Açıkça söylemek gerekiyor: sohbet kipinde **cümleyi kimse ajana ulaşmadan
önce okumuyor.** Yazdır kipinin koruması buydu.

Koruma kaldırılmadı, yerine üç şey kondu:

1. **Duyulan cümle cevaptan önce ekranda görünüyor.** Yanlış duyulmuş bir
   cümle görünmez değil, yalnızca önceden onaylanmamış oluyor.
2. **Yıkıcı hiçbir şey sesle çalışmıyor.** HIGH ve CRITICAL seviyesindeki
   işlemler onay istiyor, panel de onları reddediyor (onay penceresi henüz
   yok; reddetmek dürüst olan).
3. **Çıta yükseltilebilir.** Odada başkaları konuşuyorsa:

   ```
   JARVIS_SESLI_TABAN=low
   ```

   O zaman sesle yalnızca **okuyan** araçlar çalışır; bir şeyi değiştiren
   her araç — "YouTube aç" dahil — reddedilir.

Varsayılan `medium`, yani yazarken olduğu gibi. MEDIUM bu projede zaten
"görünür ve geri alınabilir" demek; "YouTube aç" orada, ve mikrofondan
söylendiğinde çalışmaması istenen şeyin tam tersi olurdu.

---

## Model seçimi ve VRAM

12 GB'lık RTX 3080 Ti'de 14B model Q4 olarak zaten **~9 GB** tutuyor. Whisper
onun yanına sığmalı:

| Model      | VRAM (int8_float16) | Türkçe kalitesi        |
|------------|---------------------|------------------------|
| `tiny`     | ~0.2 GB             | zayıf                  |
| `base`     | ~0.3 GB             | idare eder             |
| `small`    | ~0.5 GB             | **iyi — varsayılan**   |
| `medium`   | ~1.5 GB             | belirgin şekilde daha iyi |
| `large-v3` | ~3 GB               | en iyi · 14B ile birlikte sığmaz |

`.env` içinden değiştirilir:

```
JARVIS_STT_MODEL=medium
```

`medium` denemeye değer: 14B modelin yanında hâlâ ~1.5 GB boşluk kalıyor.
`large-v3` için 14B yerine 7B modele inmek gerekir.

### Ölçülen fark

Aynı kayıt ("Jarvis, sistem durumu nedir?"), CPU üzerinde:

| Model    | Duyulan                         | Süre  |
|----------|---------------------------------|-------|
| `tiny`   | "Cerviz sistem durumu nedir?"   | 4.1 s |
| `base`   | "Jarvis sistem durumun nedir?"  | 3.3 s |
| `small`  | "Cervis sistem durumu nedir?"   | 6 s   |
| `medium` | "Jarvis sistem durumu nedir?"   | 20 s  |

Tek bir örnek — sıralama olarak okunmamalı; `small`'ın `base`'ten kötü
çıkması bu yüzden. Söylediği tek net şey şu: **cümlenin kendisi her boyutta
doğru anlaşılıyor, özel isimler karışıyor.** "Jarvis" gibi bir sözcüğü ancak
`medium` tutturdu.

Süreler bu ölçümde CPU'da; **sizde GPU var**, orada birkaç kat hızlı olacak.

---

## `libcublas.so.12 is not found` — GPU kütüphaneleri

En sık karşılaşılan durum. NVIDIA sürücüsü kurulu, `nvidia-smi` çalışıyor,
panel `cuda` yazıyor — ama çözümleme anında bu hata geliyor.

Sebebi şu: CTranslate2 (Whisper'ı çalıştıran motor) **CUDA hesaplama
kütüphanelerini ayrıca ister.** Sürücü onları getirmez. Üstelik bunları
modeli kurarken değil, **ilk hesaplamada** açar — bu yüzden model GPU'da
sorunsuz kurulur ve hata ancak konuştuğunuzda ortaya çıkar.

**J.A.R.V.I.S. bu durumda kendiliğinden CPU'ya düşer**, terminale yazar ve
çözümlemeye devam eder. Yani mikrofon çalışır, sadece yavaşlar.

GPU hızını istiyorsanız iki paket yeter:

```bash
pip install nvidia-cublas-cu12 nvidia-cudnn-cu12
```

`LD_LIBRARY_PATH` ayarlamanız gerekmez — J.A.R.V.I.S. bu paketleri
site-packages içinden bulup açıyor.

Kurduktan sonra paneli yeniden başlatın.

> Başlangıçtaki `Mikrofon : … · cuda` satırı **niyeti** gösterir, sonucu
> değil. Gerçekten CPU'ya düşüldüyse ilk çözümlemede terminale bir satır
> düşer.

## Kalıcı olarak CPU

Uğraşmak istemiyorsanız:

```
JARVIS_STT_DEVICE=cpu
```

5 saniyelik bir kayıt `small` modelinde ~3-4 saniye sürer. Yazmaktan hâlâ
hızlı.

---

## Ayarlar

| Anahtar                | Varsayılan | Ne işe yarar |
|------------------------|------------|--------------|
| `JARVIS_STT_ENABLED`   | `true`     | Mikrofonu tamamen kapatır |
| `JARVIS_STT_MODEL`     | `small`    | Model boyutu |
| `JARVIS_STT_DEVICE`    | `auto`     | `auto` · `cuda` · `cpu` |
| `JARVIS_STT_COMPUTE`   | `auto`     | Nicemleme (`int8`, `int8_float16`, `float16`) |
| `JARVIS_STT_LANGUAGE`  | `tr`       | Dil ipucu — boş bırakılırsa otomatik algılar |

Tek seferlik kapatmak için: `jarvis-panel --mikrofonsuz`

---

## iPhone'dan mikrofon

Telefondan konuşmak için **HTTPS şart** — iOS Safari, güvenli olmayan bir
bağlantıda mikrofonu hiç vermez. `http://192.168.2.77:8765` üzerinden panel
açılır, yazışma çalışır, ama 🎙 düğmesine dokununca "güvenli bağlantı gerekli"
uyarısı alırsınız.

Çözüm: **Tailscale.** Üç şeyi birden hallediyor:

1. HTTPS sertifikası (`tailscale cert` ile, tarayıcının güvendiği gerçek bir
   sertifika — kendi imzaladığınız sertifikayı iOS reddediyor)
2. WSL'in her açılışta değişen IP'si derdi bitiyor — sabit bir ad
3. Ev ağı dışından da erişim (serviste, yolda) — port yönlendirme veya
   güvenlik duvarı deliği açmadan

Kurulumu ayrı bir adım; bunu yapana kadar mikrofon **masaüstü tarayıcıda
`localhost` üzerinden** çalışır (localhost güvenli bağlam sayılır, sertifika
gerekmez).

---

## Sık karşılaşılanlar

**"Mikrofon izni alınamadı: NotAllowedError"**
Tarayıcı izni reddetmiş. Adres çubuğundaki kilit simgesinden mikrofona izin
verin, sayfayı yenileyin.

**"Mikrofon için güvenli bağlantı (HTTPS) gerekli"**
Sayfayı `http://` ile bir ağ adresinden açtınız. `localhost` kullanın veya
yukarıdaki Tailscale yolunu izleyin.

**"Bir şey duyulmadı"**
Kayıtta konuşma bulunamadı. Sessizlik filtresi (VAD) devrede olduğu için çok
kısık ses tamamen elenebilir; mikrofona biraz daha yakın konuşun.

**İlk kayıt çok uzun sürdü**
Model ilk kullanımda iniyor ve yükleniyor. Sonrakiler hızlı.

**"Ses çözümlenemedi: Library libcublas.so.12 is not found"**
Yukarıdaki GPU kütüphaneleri bölümüne bakın. Bu sürümde kendiliğinden CPU'ya
düşülüyor; hatayı görüyorsanız eski sürümdesiniz, `git pull` yapın.

**Türkçe yanlış anlaşılıyor**
`JARVIS_STT_MODEL=medium` deneyin. Teknik terimler (anakart modeli, hata
kodları) her boyutta zorlanır — onları yazmak daha güvenilir.
