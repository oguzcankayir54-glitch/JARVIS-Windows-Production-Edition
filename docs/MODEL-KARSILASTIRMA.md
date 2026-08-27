# Büyük model gerçekten daha mı iyi?

> 62.000 TL'lik ekran kartı kararını tahminle değil, ölçümle vermek için.

---

## Neden bu test

Donanım raporunda (`JARVIS-Donanim-Butce-Raporu.pdf`) şunu savundum:
70B, 32B'den **ölçülebilir şekilde** daha iyi olmalı ki 70.000 TL fazlayı
hak etsin. Aynı mantık bir kademe aşağıda da geçerli: **32B, hâlihazırda
çalışan 14B'den 62.000 TL edecek kadar iyi mi?**

Bunu bugün, hiç para harcamadan ölçebilirsiniz.

## Kartınıza sığmayan modeli nasıl test ediyoruz

12 GB'lık bir kartta 32B modeli çalıştırırsanız Ollama modelin bir kısmını
sistem RAM'ine taşır. Sonuç **çok yavaş** olur — cevap başına dakikalar.

Ama burada ölçtüğümüz şey hız değil. Yavaşlık kartın yetmemesinden;
**üretilen cevap, 3090'da alacağınızla birebir aynıdır.** Yani 62.000 TL'yi
harcamadan, o parayla alacağınız kaliteyi bugün görebiliyorsunuz.

---

## Önce araç testi — 2 dakika

Prose karşılaştırmasına girmeden önce bunu çalıştırın:

```bash
jarvis-karsilastir MODEL1 MODEL2 --araclar
```

J.A.R.V.I.S. telemetriyi, terminali ve servis defterini **araç çağırarak**
kullanır. Araç çağıramayan bir model, Türkçesi ne kadar güzel olursa olsun bu
iş için gerilemedir: güzel konuşur, hiçbir şey yapamaz.

Bu test her modele 4 istek yollar; hepsi araç kullanmadan cevaplanamaz.

| Oran | Anlamı |
|---|---|
| %75+ | Güvenilir, prose karşılaştırmasına geçin |
| %40-75 | Değişken — günlük kullanımda bazen uydurma cevap alırsınız |
| %40 altı | Bu iş için kullanılamaz, modeli eleyin |

**Uydurma araç adı sessizlikten kötüdür.** Ajan onu çağırmayı dener, başarısız
olur ve adım yakar. Tablo bunu ayrıca gösterir.

Bir saatlik kör karşılaştırmayı çalıştırıp sonunda modelin araç çağıramadığını
öğrenmek, o saatin boşa gitmesidir.

---

## Kurulum

```bash
ollama pull qwen2.5:32b-instruct-q4_K_M
```

**Yer:** ~20 GB. İnmeden önce diskte yeriniz olduğundan emin olun:
`df -h ~`

---

## Çalıştırma

```bash
cd ~/jarvis && source .venv/bin/activate
jarvis-karsilastir qwen2.5:14b-instruct qwen2.5:32b-instruct-q4_K_M
```

12 soru × 2 model = 24 cevap. 32B taşarak çalışacağı için
**bir-iki saat sürebilir** — başlatıp başka işe bakın.

İki dosya üretir:

| Dosya | İçerik |
|---|---|
| `karsilastirma/kor-karsilastirma.md` | Cevaplar — **model adı geçmez** |
| `karsilastirma/cevap-anahtari.md` | Hangi harf hangi model + süreler |

---

## Neden kör

Bir cevabın büyük modelden geldiğini bilmek, o cevabı **daha iyi okumanıza**
yol açar. Bu iyi belgelenmiş bir yanlılık ve tam olarak gereksiz bir alımı
haklı çıkaracak şey.

Bu yüzden:

- Cevaplar her soruda **yeniden karıştırılmış** A/B olarak sunulur
- Model adları kör sayfada hiç geçmez
- Süreler de geçmez — yavaş olan hangisiyse o, büyük olandır

**Önce kör sayfayı doldurun.** Her soruda bir tercih yapın ve *neden*
seçtiğinizi bir cümleyle yazın. Sonra anahtara bakın.

---

## Nasıl değerlendirmeli

Uzun cevap iyi cevap değildir. Bakılacak şeyler:

- **Doğru mu?** Servis tecrübenizle çelişen bir şey var mı?
- **Sıra mantıklı mı?** En olası nedenden mi başlıyor, yoksa rastgele mi sayıyor?
- **Ne eliyor?** İyi bir teşhis her adımda bir şeyi eler; kötüsü liste sayar.
- **Uydurma var mı?** Olmayan bir BIOS ayarı, yanlış bir LED anlamı?
- **Kullanılabilir mi?** Müşterinin karşısında bu cevapla ilerleyebilir misiniz?

---

## Kararı nasıl okumalı

| Sonuç | Anlamı |
|---|---|
| 32B **belirgin** üstün (8+/12) | Kart almaya değer — Yol A'yı uygulayın |
| Başa baş (5-7/12) | **Almayın.** 14B işinizi görüyor, para başka yere |
| 14B üstün | Beklenmedik ama olabilir — soru setini gözden geçirelim |

---

## Kendi vakalarınızı ekleyin

Asıl kıymetli test hazır sorular değil, **sizin gerçek vakalarınız.**
`docs/karsilastirma-sorulari.txt` dosyasına satır satır ekleyin — geçen ay
uğraştığınız, kolay çözülmeyen vakalar en ayırt edici olanlardır.

Kendi dosyanızı kullanmak için:

```bash
jarvis-karsilastir MODEL1 MODEL2 --sorular kendi-sorularim.txt
```

---

## Diğer seçenekler

Karşılaştırmaya ikiden fazla model verebilirsiniz (C, D… harflerini alır):

```bash
jarvis-karsilastir qwen2.5:14b-instruct qwen2.5:32b-instruct-q4_K_M gemma3:27b
```

| Bayrak | İşlevi |
|---|---|
| `--sorular DOSYA` | Kendi soru listeniz |
| `--cikti KLASÖR` | Sonuçların yazılacağı yer (varsayılan `karsilastirma/`) |
| `--zaman-asimi SN` | Cevap başına üst sınır (varsayılan 600) |
| `--kimliksiz` | Kişisel kimlik bilgisi olmadan sorar |

> `--kimliksiz` olmadan modeller sizi tanıyan sistem istemiyle çalışır —
> yani günlük kullanımdaki hâlleriyle. Karşılaştırmanın gerçekçi olması için
> varsayılan budur.

---

## Zaman aşımı alırsam

```
ReadTimeout / Ollama'ya ulaşılamadı
```

32B çok taşıyorsa 600 saniye yetmeyebilir:

```bash
jarvis-karsilastir MODEL1 MODEL2 --zaman-asimi 1200
```

Hâlâ olmuyorsa daha küçük bir nicemleme deneyin (`q3_K_M`, ~15 GB) — kalite
biraz düşer ama karşılaştırma için yeterli fikir verir.
