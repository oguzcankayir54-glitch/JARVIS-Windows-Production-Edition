# J.A.R.V.I.S. — Kamera (yerel görüntü analizi)

> Aşama 1: **hedef takibi.** Kamerada yüz var mı, kaç tane, nerede. Görüntü
> **bu makinede** ölçülür; ne diske yazılır ne dışarı çıkar.

---

## Neden yerel, neden varsayılan kapalı

Kamera sistemdeki en tanımlayıcı sinyal. Mikrofonda olduğu gibi burada da ham
veri makineden çıkmıyor: kare çözülür, ölçülür ve atılır. Geriye yalnızca
**kaç yüz ve nerede** bilgisi kalıyor.

Kamera **kendiliğinden açılmaz.** Bir servis tezgâhındaki kamera müşteriyi de,
kuryeyi de, oradan geçen herkesi görür; hiçbiri bir şey kabul etmedi. Açmak
bilinçli bir hareket olmalı — bu yüzden hem sunucu tarafında bir bayrak, hem
panelde bir düğme gerekiyor.

---

## Kurulum

```bash
cd ~/jarvis
source .venv/bin/activate
pip install "opencv-python-headless<5"
```

> **Sürüm neden sabit?** OpenCV 5, yüz kaskadını (`CascadeClassifier`) ve
> birlikte gelen model dosyalarını ana paketten çıkardı. Düz `pip install
> opencv-python-headless` bugün 5.x getiriyor: içeri aktarılıyor ama yüz
> bulamıyor. 4.x ikisini de indirme gerektirmeden getiriyor.
>
> Yanlış sürüm kuruluysa J.A.R.V.I.S. bunu **başlangıçta** söyler, ilk karede
> değil:
> `Kamera : kapalı` + `OpenCV 5.0.0 yüz kaskadını içermiyor`

**OpenCV kurulmazsa J.A.R.V.I.S. yine çalışır**, yalnızca kamera kapalı olur.
Yazmak, konuşmak, ses — hiçbiri etkilenmez.

---

## Açmak

```bash
jarvis-panel --kamera
```

veya kalıcı olarak `.env` içinde:

```
JARVIS_VISION_ENABLED=true
```

Başlangıç çıktısında görmeniz gereken satır:

```
  Kamera   : opencv-haar
```

Panelde **Vision** sekmesine geçin (üstteki modül şeridinde). Aynı kutu kamera
görüntüsüne dönüşür — panelde hiçbir şey yer değiştirmez. **KAMERAYI AÇ**
düğmesine basın, tarayıcı izin ister.

Yüz bulunduğunda çerçevenin köşeleri işaretlenir ve sağ altta `1 yüz · 38 ms`
gibi bir satır çıkar.

---

## Nasıl çalışıyor

```
tarayıcı kamerası
   └─ her 700 ms'de bir kare, 480 px'e küçültülüp JPEG'e çevrilir
        └─ POST /gor  (yalnızca bu makine — panel 127.0.0.1'de)
             └─ OpenCV Haar kaskadı · CPU · birkaç ms
                  └─ dönen: kaç yüz, kare oranı cinsinden nerede
                       └─ kare atılır
```

Üç seçim açıklama istiyor:

**Neden kaskad, sinir ağı değil?** OpenCV 4 tekerleğinin içinde geliyor,
indirme istemiyor, CPU'da birkaç milisaniye sürüyor ve GPU'yu tamamen dil
modeline bırakıyor. Yan açılarda zayıf — "tezgâhta biri oturuyor mu" sorusu
için doğru takas. Yüz **tanıma** aşamasında daha sıkı bir kırpma gerekince
yeniden bakılacak.

**Neden saniyede 1,4 kare?** Asıl maliyet kaskad değil, JPEG kodlaması ve
istek. Eski bir web kamerası için bu hız fazlasıyla yeterli.

**Neden koordinatlar piksel değil, oran?** Panel önizlemeyi kendi seçtiği
boyutta çiziyor. 640×480'lik bir kareden gelen piksel koordinatı, 224 px
genişliğindeki önizlemede yüzün yanına düşerdi.

---

## Sınırlar

| Ne | Değer | Neden |
|----|-------|-------|
| Kare boyutu | 8 MB | Panel ağa açılabiliyor; karşı tarafın gönderdiği veri sınırsız belleğe alınamaz |
| En küçük yüz | karenin %6'sı | Eski kameralarda arka plan desenleri kolayca yanlış pozitif üretiyor |

Sınırı aşan kare **okunmadan** reddediliyor — sınırın amacı belleği
sınırlamak, dolayısıyla önce içeri alıp sonra bakmak anlamsız olurdu.

---

## İsteğe bağlı gelişmiş analiz

Temel yüz konumu dışında üç yerel sağlayıcı vardır ve gizlilik nedeniyle
varsayılan olarak kapalıdır:

- **Nesne algılama** — YOLO ile bilinen nesne sınıflarını, güven puanını ve
  kare içindeki konumunu döndürür. `pip install -e ".[gorsel]"` ardından
  `JARVIS_OBJECT_VISION_ENABLED=true` ile açılır. Model ağırlığı ilk kullanımda
  indirilebilir.
- **OCR** — Tesseract ile karedeki metni okur. Aynı `gorsel` eki ve
  `JARVIS_OCR_ENABLED=true` gerekir; Windows'ta Tesseract uygulamasının ve
  kullanılacak dil paketinin ayrıca kurulu olması gerekir.
- **Yüz kimliği** — yalnızca açık kullanıcı kaydıyla oluşturulan yerel yüz
  embedding'lerini karşılaştırır. Ham fotoğraf saklanmaz. `pip install -e
  ".[yuz]"` ve `JARVIS_FACE_RECOGNITION_ENABLED=true` ile açılır.

Bu sağlayıcıların hiçbiri kamerayı kendiliğinden açmaz. Proaktif karşılama da
henüz yoktur; bir yüzün görülmesi kendi başına asistan turu başlatamaz.

---

## Ayarlar

| Anahtar | Varsayılan | Ne işe yarar |
|---------|------------|--------------|
| `JARVIS_VISION_ENABLED` | `false` | Kamerayı açar |
| `JARVIS_OBJECT_VISION_ENABLED` | `false` | YOLO nesne algılamayı açar |
| `JARVIS_OCR_ENABLED` | `false` | Görüntüden metin okumayı açar |
| `JARVIS_FACE_RECOGNITION_ENABLED` | `false` | İzinli yerel yüz kimliğini açar |

Tek seferlik açmak için: `jarvis-panel --kamera`

---

## Sık karşılaşılanlar

**Panelde KAMERAYI AÇ düğmesi yok**
Sunucuda kamera kapalı. `jarvis-panel --kamera` ile başlatın; sağ altta neden
kapalı olduğu yazar.

**"OpenCV 5.0.0 yüz kaskadını içermiyor"**
Yanlış sürüm kurulu. `pip install "opencv-python-headless<5"` ile 4.x'e inin
ve paneli yeniden başlatın.

**"izin alınamadı: NotAllowedError"**
Tarayıcı kamera iznini reddetmiş. Adres çubuğundaki kilit simgesinden izin
verip sayfayı yenileyin.

**"kamera için HTTPS gerekli"**
Sayfayı bir ağ adresinden `http://` ile açtınız. Tarayıcılar kamerayı yalnızca
güvenli bağlamda veriyor — mikrofonla aynı kural. `localhost` kullanın veya
`docs/MIKROFON.md` içindeki Tailscale yolunu izleyin.

**Yüz bulunmuyor**
Kaskad kontrasta duyarlı. Yüzünüze ışık gelsin, kameraya doğrudan bakın,
karenin en az %6'sını kaplayacak kadar yaklaşın.

**Yüz olmayan yerde kutu çıkıyor**
Haar kaskadının bilinen zayıflığı. Arka planı sadeleştirmek belirgin şekilde
azaltıyor; tanıma aşamasında daha seçici bir dedektöre geçilecek.
