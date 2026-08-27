# Nereden indirilir, nasıl kurulur

> Bu dosya tek bir soruyu cevaplamak için var: **"yeni sürümü nereden
> indireceğim?"** Tıklama tıklama aşağıda.

---

## İndirme

> **Depo özel olduğu için kopyalanabilir bir indirme linki yok.** Özel
> depolarda ZIP adresi kişiye özel ve kısa ömürlü bir jeton taşıyor; o
> jetonu ancak GitHub'ın kendi düğmesi üretiyor.
>
> Bu denendi ve iki biçim de tarayıcıda **404 verdi**:
> `github.com/.../archive/refs/heads/DAL.zip` ve
> `codeload.github.com/.../zip/refs/heads/DAL`. İkincisi jetonla yapılan
> testte 200 dönüyordu — tarayıcı o jetonu göndermediği için yanıltıcıydı.

### Düğmeyle indirme (çalışan yol)

1. Şunu tarayıcıda açın:

   ```
   https://github.com/oguzcankayir54-glitch/jarvis
   ```

2. Dosya listesinin sol üstündeki **dal seçicisine** tıklayın
   (üzerinde `main` yazan açılır kutu)

3. Listeden şunu seçin:

   ```
   claude/jarvis-architecture-analysis-40i73f
   ```

4. Sağdaki yeşil **`< > Code`** düğmesine tıklayın

5. Açılan menüde **Download ZIP**

### Daha kolayı

ZIP'i sohbette doğrudan isteyin — hazırlanıp dosya olarak gönderilir,
GitHub'a hiç girmeniz gerekmez.

---

## Kurulum

1. İnen dosyaya **sağ tık → Tümünü ayıkla**
2. Ayıklanan klasörde `windows` klasörünü açın
3. İçindeki **`Kur.cmd`** dosyasına **çift tıklayın**

Terminal açmanız, klasöre gitmeniz, komut yazmanız gerekmiyor.

### Bittiğinde göreceğiniz satırlar

```
✓ jarvis.ini yazildi (mod = windows, port 8765)
...
✓ masaustu: J.A.R.V.I.S.
```

Daha önce F.R.I.D.A.Y. kurduysanız bir de şunu görürsünüz — ikinci
asistan kaldırıldı ve kurulum kendi bıraktığını topluyor:

```
✓ eski F.R.I.D.A.Y. kalintisi silindi: F.R.I.D.A.Y..lnk
✓ eski F.R.I.D.A.Y. kalintisi silindi: friday.ini
```

---

## Güncellerken ne kaybolur?

**Hiçbir şey.** Kurulum kodu `%LOCALAPPDATA%\Programs\JARVIS\app` altına
kopyalıyor ve şunlara **dokunmuyor**:

| | nerede | durumu |
|---|---|---|
| `.env` (Ollama ayarı, anahtarlar) | `...\JARVIS\app\.env` | korunur |
| Erişim jetonu | `...\JARVIS\jarvis.ini` | korunur |
| Hafıza, vakalar, bilgi tabanı | `%USERPROFILE%\.jarvis` | dokunulmaz |
| Sanal ortam | `...\JARVIS\app\.venv` | korunur |

Yani indirip kurmak, ayarlarınızı sıfırlamıyor.

---

## İndirilen klasörler birikiyorsa

Her indirmede `...-40i73f_2`, `_3` diye yeni klasör oluşuyorsa bu normal —
Windows aynı adı ikinci kez kullanmıyor. Kurulum bittikten sonra
**indirilen klasörü silebilirsiniz**; program artık
`%LOCALAPPDATA%\Programs\JARVIS` altında ve masaüstü simgesi oraya
bakıyor.

---

## Kaldırmak

`windows\Kur.cmd` dosyasını `/kaldir` ile çalıştırın, ya da:

**Windows Gezgini'nde `windows` klasöründeyken adres çubuğuna `cmd` yazıp
Enter'a basın**, açılan pencereye:

```
Kur.cmd /kaldir
```

Masaüstü ve Başlat menüsü simgeleri silinir. Hafızanız (`~/.jarvis`)
durur; onu istemiyorsanız elle silin.
