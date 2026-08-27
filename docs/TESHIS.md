# Diagnostic Brain

Diagnostic Brain, teknisyenin ölçtüğü sonucu deterministik bir karar ağacında
ilerletir. LLM kendi başına ölçüm uydurmaz ve playbook hiçbir sistem komutunu
otomatik çalıştırmaz.

## Hazır playbook'lar

- Güç yok / açılmıyor
- Görüntü yok / POST sorunu
- Aşırı ısınma / kapanma

Her playbook dış zincirden ve düşük riskli kontrolden başlar; bileşen sökme
ve kart seviyesi inceleme daha sonraki dallara bırakılır.

## Panelden kullanım

1. Önce bir servis vakası açın.
2. Panelde **Teşhis** sekmesine geçin.
3. Vaka numarasını yazıp playbook'u seçin.
4. Yalnızca gerçekten gözlediğiniz/ölçtüğünüz seçeneğe basın.
5. Sonuç düğümü vaka defterine `sonuc`, ara cevaplar `deneme` notu olarak yazılır.

## Ajan araçları

| Araç | Risk | Amaç |
|---|---|---|
| `teshis_playbooklari` | LOW | Hazır ağaçları listeler |
| `teshis_baslat` | MEDIUM | Mevcut vakaya kalıcı teşhis oturumu bağlar |
| `teshis_yanitla` | MEDIUM | Doğrulanan cevabı kaydedip ilerler |

Yazma araçlarının MEDIUM olması bilinçlidir: vaka geçmişi sohbet sırasında
sessizce değişmemelidir.

## HTTP API

Panel jetonu korumasının arkasında iki JSON uç noktası bulunur:

```text
POST /teshis/baslat  {"vaka_no": 12, "playbook": "guc-yok"}
POST /teshis/yanit   {"oturum_no": 4, "secenek": "evet"}
```

Geçersiz vaka, playbook, oturum veya seçenek HTTP 400 ile reddedilir.
