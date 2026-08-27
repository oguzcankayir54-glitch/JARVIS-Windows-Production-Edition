# J.A.R.V.I.S. — saf Windows kurulumu

> WSL yok. Ne dağıtım, ne interop, ne her yeniden başlatmada değişen sanal ağ,
> ne portproxy. Python doğrudan Windows'ta, panel doğrudan Windows'ta.

---

## Neden WSL'den çıkıyoruz

WSL çalışıyordu ama üç şeyi sürekli geri getiriyordu:

1. **Ağ.** WSL2'nin IP'si her yeniden başlatmada değişiyor. Eskimiş bir
   `netsh portproxy` kaydı `localhost`'u yakalayıp `ERR_CONNECTION_RESET`
   veriyor. Bu sorun bu projede dört kez teşhis edildi.
2. **Interop.** Windows programlarını açmak `/etc/wsl.conf` içindeki bir
   ayara bağlıydı. Kapalıysa "YouTube aç" sessizce çalışmıyordu.
3. **İki sistem.** Python WSL'de, program Windows'ta. Her hata "hangi
   taraftaydı" sorusuyla başlıyordu.

Windows kurulumunda üçü de yok.

---

## Gereken tek şey: Python

```
winget install Python.Python.3.12
```

Ya da <https://www.python.org/downloads/windows/> — kurulum sırasında
**"Add python.exe to PATH"** kutusunu işaretleyin.

> Microsoft Store'un `python.exe` kısayolu gerçek bir Python değil, Store'u
> açan bir saplama. Kurulum onu tanıyıp atlıyor.

---

## Kurulum

Hazır dağıtım paketinde **`JARVIS-Setup-2.0.1.exe`** dosyasına çift
tıklayın. Standart Windows kurulum sihirbazı mevcut kurulum denetimlerini
çalıştırır ve kaldırıcıyı kaydeder.

Setup dosyası henüz derlenmemiş bir kaynak kopyası kullanıyorsanız,
`windows` klasöründeki **`Kur.cmd`** aynı kurulumu doğrudan başlatmaya devam
eder. Bu yol geriye dönük uyumluluk ve hata ayıklama için korunmuştur.

| Komut | Ne yapar |
|---|---|
| `Kur.cmd` | Windows'a kurar (varsayılan) |
| `Kur.cmd /wsl` | Eski WSL kurulumu |
| `Kur.cmd /kaldir` | Kaldırır (hafıza ve notlar kalır) |

### Setup paketini oluşturma

Windows'ta [Inno Setup](https://jrsoftware.org/isinfo.php) 6 veya 7 kurulu olmalıdır:

```bat
winget install JRSoftware.InnoSetup
windows\Setup-Olustur.cmd
```

Çıktı `windows\release\JARVIS-Setup-2.0.1.exe` olur. Setup yalnızca gerekli
uygulama kaynaklarını paketler ve mevcut `kur-windows.ps1` kurulumunu çağırır;
Linux dosyalarını veya uygulamanın çalışma kodunu değiştirmez.

Kurulum sırasıyla şunları yapıyor:

1. Python'u bulur — yoksa nereden alınacağını söyler ve durur
2. Projeyi `%LOCALAPPDATA%\Programs\JARVIS\app` altına kopyalar
3. Kendi `.venv`'ini kurar, bağımlılıkları yükler
4. Ses (`edge-tts`) ve mikrofonu (`faster-whisper`) kurar — biri olmazsa
   kurulum devam eder, yalnızca o özellik kapalı kalır
5. `.env` ve `jarvis.ini` yazar (varsa **dokunmaz**)
6. Masaüstüne ve Başlat menüsüne kısayol koyar
7. **Kurulumun gerçekten çalıştığını doğrular**

Son adım isteğe bağlı değil. Bu projede iki kez "kurulum bitti" denip ilk
çift tıklamada hata alındı; kurulum kendi işini kendi denetlemezse denetimi
kullanıcı yapıyor demektir.

---

## Dil modeli — bunu atlamayın

Kurulum bittiğinde J.A.R.V.I.S. açılır ama **sizi anlamaz**. Sebebi şu:
varsayılan sağlayıcı `mock`, yani anahtar kelime eşleyen sahte bir model.
Sistem istemini okumaz, sizi tanımaz, bağlamı görmez.

"Beni tanımıyor" ve "söylediğim hiçbir şeyi algılamıyor" şikâyetlerinin
sebebi buydu. **Sesle ilgisi yok** — seslendirme çıkıştır, anlamayla ilgisi
olmaz.

Gerçek model için:

```
winget install Ollama.Ollama
ollama pull qwen2.5:14b-instruct
```

Sonra `%LOCALAPPDATA%\Programs\JARVIS\app\.env` içinde:

```
JARVIS_LLM_PROVIDER=ollama
JARVIS_OLLAMA_MODEL=qwen2.5:14b-instruct
```

(Kurulum bu iki satırı zaten yazıyor; Ollama kurulu değilse uyarıyor.)

Modeli küçültmek gerekirse `qwen2.5:7b-instruct` de çalışır, ama Türkçesi
belirgin biçimde zayıflar ve İngilizceye kayması artar.

---

## Panel

Masaüstündeki simgeye çift tıklayın. Panel **1920×1080 tam ekran** açılır.

| Ayar | Varsayılan | Nerede |
|---|---|---|
| `tamekran` | `1` | `%LOCALAPPDATA%\Programs\JARVIS\jarvis.ini` |
| `genislik` / `yukseklik` | `1920` / `1080` | aynı dosya |
| `intro` | `1` | aynı dosya |
| `port` | `8765` | aynı dosya |

Tam ekrandan çıkmak için **F11**.

---

## Kimlik

J.A.R.V.I.S. artık sahibini kurulumdan itibaren tanıyor: bilgiler depodaki
`kimlik.json` dosyasında ve veritabanı boşsa ilk açılışta oradan doldurulur.

Değiştirmek için ya o dosyayı düzenleyin ya da:

```
jarvis-tanit --kur
```

Veritabanında bir kimlik varsa dosya hiçbir şey yapmaz — elle girdiğiniz
bilgi her açılışta eski değere dönmez.

---

## Neler değişti, neler aynı

| | WSL kurulumu | Windows kurulumu |
|---|---|---|
| Python | WSL içinde | Windows'ta |
| Program açma | interop + `cmd.exe` | doğrudan (`os.startfile`) |
| Tarayıcı açma | `wslview` | varsayılan tarayıcı |
| Terminal komutları | Unix araçları | Windows komutları |
| Ağ | portproxy zinciri | yok |
| Panel penceresi | Edge `--app` | Edge `--app`, tam ekran |

Panel hâlâ bir web arayüzü ve pencereyi Edge'in `--app` kipi çiziyor: sekme
yok, adres çubuğu yok, görev çubuğunda kendi simgesi var. Bu Windows'ta
yaygın bir yaklaşım — birçok masaüstü uygulaması da içeride aynı motoru
kullanıyor.

---

## Sık karşılaşılanlar

**"Python bulunamadi"** — PATH'e eklenmemiş. Python'u yeniden kurup "Add
python.exe to PATH" kutusunu işaretleyin, ya da `jarvis.ini` içindeki
`python` satırına `python.exe`'nin tam yolunu yazın.

**Panel açılıyor ama sorulara saçma cevaplar veriyor** — `mock` model
çalışıyor. Panel açılışında büyük bir uyarı kutusu yazıyor; yukarıdaki
Ollama adımlarını yapın.

**Ses yok** — `jarvis-ses --kontrol` çalıştırın (proje klasöründen).

**Mikrofon yok** — `faster-whisper` kurulamamış olabilir. Kurulum bunu
uyarıyla geçiyor; elle: `.venv\Scripts\pip install faster-whisper`.
