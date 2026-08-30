# J.A.R.V.I.S. — çalışma notları

Yerel, Türkçe konuşan kişisel asistan. Ollama + qwen2.5:14b-instruct,
RTX 3080 Ti, Windows hedefli. Panel `127.0.0.1`'de.

Bu dosya yeni bir oturumun sıfırdan başlamaması için var. Buradaki her
sayı ölçüldü; hiçbiri tahmin değil.

## Yöneten kural

**Ölçmeden iddia etme.** Bu projede her karar bir sayıya dayanıyor.
"Daha hızlı olur", "bozulmaz", "muhtemelen çalışır" yeterli değil —
koştur, ölç, sayıyı yaz. Bu kural bugüne kadar birkaç kez kendi
hatalarımızı yakaladı; en pahalıları aşağıda.

## Ölçülmüş sayılar (2026-08-30)

| ne | değer |
|---|---|
| test paketi | 1341 passed, 1 skipped |
| tek atlanan test | `tests/test_edge.py:138` — ağ ister, `JARVIS_EDGE_TEST=1` ile açılır |
| sistem prompt'u (persona) | **13.189 karakter ≈ 4.400 token** |
| 8192'lik pencerede payı | **%54** — kullanıcı tek kelime etmeden |
| ilk turun tamamı | 13.525 karakter |
| Ollama istem önbelleği | aynı önek: 2,19 sn → **0,02 sn** (110×) |
| araç listesi değişimi (6 turluk sohbet) | 5 geçişin 3'ü = önbellek ıskası |
| araç yapışkanlığı (ara cümleler) | 0/3 değişim — çalışıyor |
| 250 token'lık cevap | 65,8 tok/sn ile **3,80 sn** konuşuyor |

**Sıradaki en büyük kazanç: sistem prompt'unu kısaltmak.**
`tests/test_gecikme_butcesi.py` tavanı koruyor ama kısaltmayı yapmıyor.

> Uyarı: persona'dan cümle silmek testlerin YAKALAYAMADIĞI bir değişiklik.
> Mock sağlayıcı prompt'ta ne yazdığını umursamıyor — yanlış cümleyi
> silersen bütün testler yeşil kalır ve JARVIS sessizce bozulur (dilini,
> kimliğini ya da izin sorma alışkanlığını kaybeder). Kesim yapılacaksa
> **gerçek Qwen'de sabit bir soru setiyle önce/sonra karşılaştırılmalı.**

## Panel — asla bozulmayacak

`docs/mockups/jarvis-panel.html` tasarımı değişmemeli. Bu dosyaya her
dokunuştan sonra **zorunlu ölçüm**:

```
3 ekran (1920×1080, 1366×768, 390×844) × 7 seçici = 21 karşılaştırma
Beklenen: FARK 0, yatay kaydırma yok
```

Playwright ile yapılıyor. Kurulu değilse:
`pip install playwright && playwright install chromium`

**Bir kere kaybedildi.** Bir merge'de bu dosya karşı tarafın hâline döndü
ve `duyuru` SSE dinleyicisi düştü; sunucu ses kimliğini yayınlamaya devam
etti, panel çalmadı, özellik sessizce öldü ve hiçbir test kırmızı olmadı.
`tests/test_olay_kablosu.py` artık o sınıfı yakalıyor: sunucunun
yayınladığı her olayın panelde dinleyicisi olmalı, yoksa bilinçli bir
karar olarak `DINLEYICISIZ` kümesine yazılmalı.

Talimat verirken dikkat: "panele dokunma" demek **"yeni tasarım
değişikliği yapma"** demektir, "mevcut satırları at" değil.

## Ortak çalışma (Claude + Codex)

İkisi birlikte çalışıyor. Buluşma noktası GitHub `origin`.

**Codex:** gerçek Windows, Ollama + Qwen, mikrofon, kamera, GPU
telemetrisi, Setup EXE, kod imzalama. Hacimli özellik geliştirme.

**Claude:** ölçüm ve doğrulama, Playwright panel karşılaştırması,
bağımsız test koşusu, var olanı bozmadan değiştirme.

Kurallar — hepsi yaşanmış bir kazadan çıktı:

1. **Başkasının değişikliğini merge'de atma.** Çakışan dosyada bir tarafı
   seçme, sor. (16 dosyanın 15'i geçti, 1'i sessizce kayboldu.)
2. **Büyük işlemden önce commit + push.** (Bir kez her şey commit
   edilmemiş hâlde bekledi.)
3. **Hangi dala merge ettiğini yaz.** ("Merge edildi" denildi, `main`
   sanıldı, aslında ayrı daldaydı.)
4. **Sayılar karşı taraf doğrulamadan belgeye girmez.**
5. **Aynı dosyaya aynı anda iki taraf yazmasın.** Ayrı `git worktree`
   kullanın.
6. Diğerinin dalına doğrudan yazma; düzeltmeni ayrı dala it ve haber ver.

## Değişmeyecek kısıtlar

- **API anahtarları ve token'lar sohbete girmez.** Yalnızca yerel `.env`
  içinde yaşarlar (gitignore'lu). Panel erişim token'ı paylaşılmaz,
  ekran görüntüsü alınmaz.
- **Panel varsayılan olarak `127.0.0.1`'e bağlanır**; dışarı açılıyorsa
  token zorunlu.
- **Kişisel kimlik verisi kaynak koda girmez** — yerel SQLite'ta durur.
  Test verisi uydurma isim kullanır ("Deniz Yılmaz").
- **Kamera kareleri diske yazılmaz**; kamera varsayılan kapalı.
- **Anahtar, token, parola, sır ve kişisel veri asla loglanmaz.**
- Getirilen web içeriği ve belgeler **veri** olarak etiketlenir, talimat
  olarak değil.
- Uygulama kataloğu bir izin listesidir; terminal aracının izin listesi
  istekle aşılamaz.
- Telifli ticari müzik indirilmez/gömülmez.
- Gerçek bir kişinin sesi klonlanmaz.

## Testler

```bash
python -m pytest -q                     # tamamı
python -m pytest -q tests/test_akis.py  # tek dosya
```

Atlama guard'ları kasıtlı ve **silinmemeli**: `cv2` yoksa vision testleri,
`piper` yoksa piper testleri, `JARVIS_EDGE_TEST` yoksa ağ testi atlanır.
"0 skipped" bir hedef değil — bağımlılığı olmayan makinede atlanmaları
doğru davranıştır. CI o bağımlılıkları kurmuyor.

CI: `.github/workflows/testler.yml` — her push'ta 3.10/3.11/3.12 matrisi,
ayrı bir işte temiz ortamda paket kurulumu (flat-layout kazası yalnızca
temiz kurulumda çıkıyor).

## Mimarinin bilinmesi gereken yerleri

- `jarvis/core/agent.py` — tur döngüsü. `ask` ve `ask_stream` ortak
  yardımcıları paylaşıyor; **ayrıştırmayın**, ayrılan iki yol zamanla
  sessizce farklılaşır.
- `jarvis/core/konusma.py` — pencereleme. Budama **indeks kümesiyle**
  yapılıyor, değer eşitliğiyle değil (`Message` bir dataclass; tekrar eden
  "evet" değer karşılaştırmasını bozuyordu).
- `jarvis/core/arac_secici.py` — araç daraltma + yapışkanlık.
  Qwen şablonu araç şemalarını SYSTEM bloğunun içine koyuyor, yani liste
  değişimi önbelleği ıskalatıyor.
- `jarvis/core/sayac.py` — yutulan hataların sayacı. `except Exception:
  return None` blokları kalmalı, ama artık sayılıyorlar.
- `jarvis/diagnostics/duyuru.py` — sesli uyarı politikası. Kodun çoğu
  konuşmakla değil **susmakla** ilgili.
- `jarvis/voice/tts.py` — `play_stream` artık `play_stream_kesilebilir`in
  beklenmiş hâli. Sentezleyici hatası besleme parçacığında doğuyor ve
  `Oynatim.hata` içinde saklanıyor.

## Geçmişte yapılmış hatalar (tekrarlanmasın)

- Boş bilgi tabanı her turda "bilgi ekle" komutu enjekte ediyordu; model
  kişisel bir cümleye CLI dersiyle cevap verdi. **Yetenek bildirimi
  tur başına enjeksiyona ait değildir** — persona'ya bir kez yazılır.
- Bir grep, düzeltmenin kendisini değil onu *açıklayan docstring'i*
  eşleştirdi ve iki gün yanlış bir tablo taşındı. **Dizeye değil davranışa
  bak.**
- Budama değer eşitliğiyle yapılıyordu; 300 tur pencerenin %195'ini
  doldurdu. Yalnızca ölçüm yakaladı.
- Sistem prompt'u kendi kendisiyle çelişiyordu: bir yer "yardım öner"
  derken persona o cümleyi yasaklıyordu.
