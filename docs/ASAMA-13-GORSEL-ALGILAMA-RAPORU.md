# AŞAMA 13 — Görsel Algılama Raporu

## Sonuç

Aşama 13 tamamlandı. Mevcut yüz, nesne, OCR ve yüz kimliği sağlayıcıları
değiştirilmeden sağlayıcı-bağımsız bir `VisionPipeline` altında birleştirildi.
Masaüstü ekran görüntüsü açık rıza gerektiren, varsayılan kapalı bir kaynak
olarak eklendi. Ham görüntüler diske veya event payload'larına yazılmıyor.

## Önceki mimari

- `/gor`, `/nesne` ve `/ocr` uçları sağlayıcıları doğrudan çağırıyordu.
- Görsel işlemlerin ortak yaşam döngüsü, merkezi state ve event akışı yoktu.
- Masaüstü görüntüsü kaynağı ve LLM'in güvenli biçimde çağırabileceği vision
  aracı bulunmuyordu.
- Sağlayıcılar yereldi ve görüntüleri kalıcılaştırmıyordu; bu davranış korundu.

## Yeni mimari

`kamera / yükleme / masaüstü -> VisionPipeline -> faces | objects | ocr | identity`

- İşler sınırlı bir executor üzerinde çalışır; HTTP/GUI event akışı ağır analizi
  doğrudan yürütmez.
- State sırası `SEEING -> ANALYZING -> STANDBY` şeklindedir.
- `vision.input`, `vision.started`, `vision.finished`, `vision.error` eventleri
  yayımlanır ve panelin mevcut SSE köprüsünden izlenebilir.
- Yeni `/vision/analyze` ortak yükleme ucu ve `/vision/screenshot` masaüstü ucu
  eklendi. Eski uçların yanıt biçimleri korundu.
- `masaustu_analiz` aracı yalnızca screenshot gerçekten kullanılabiliyorsa
  kaydedilir ve `HIGH` risk nedeniyle kullanıcı onayı ister.
- Proaktif takip `vision.error` ve `vision.finished` eventlerine bağlandı.

## Gizlilik ve güvenlik kararları

- `JARVIS_SCREENSHOT_ENABLED=false` varsayılandır.
- Screenshot bellekte PNG olarak taşınır, diske yazılmaz.
- Eventlerde yalnızca kaynak, byte sayısı, görev ve süre bulunur; piksel verisi
  bulunmaz.
- Boyut sınırı mevcut `MAX_FRAME_BYTES` ile ortaktır.
- Vision katmanı LLM sağlayıcısını import etmez; araç katmanı yalnızca pipeline
  sözleşmesine bağlıdır.
- Kullanıcının ek isteğiyle gerçek HIGH/CRITICAL onay kapısında yerel uyarı sesi
  eklendi. `JARVIS_APPROVAL_SOUND_ENABLED=true` varsayılandır.

## Eklenen dosyalar

- `jarvis/vision/pipeline.py`
- `jarvis/vision/screenshot.py`
- `jarvis/tools/vision_tools.py`
- `jarvis/security/approval_notice.py`
- `tests/test_vision_pipeline.py`

## Değiştirilen dosyalar

- `jarvis/web/server.py`
- `jarvis/web/cli.py`
- `jarvis/config.py`
- `jarvis/bootstrap.py`
- `jarvis/security/permissions.py`
- `jarvis/diagnostics/monitor.py`
- `.env.example`
- `profiles/windows-production.env.example`
- `tests/test_config.py`
- `tests/test_permissions.py`

## Testler

- Vision pipeline sağlayıcı yönlendirme, yaşam döngüsü eventleri, merkezi state,
  veri saklamama, boyut/görev doğrulama, worker thread ve screenshot kaynağı.
- Onay sesinin yalnızca gerçekten onay gereken risk seviyelerinde tetiklenmesi.
- Panel regresyonu: `103 passed`.
- WSL uyumluluk düzeltmesi sonrası tam paket: `1142 passed, 6 skipped`
  (`137.26s`).
- `compileall` ve `git diff --check` başarılı.

## Kalan riskler ve teknik borç

- 29 Ağustos 2026 WSL2 donanım smoke testinde Windows `Exclamation` sesi
  PowerShell üzerinden başarıyla tetiklendi.
- İlk testte Pillow/WSLg screenshot sağlayıcısı `X get_image failed: error 8`
  verdi. Bunun için WSL'den Windows `System.Drawing` kullanan, geçici dosyasız
  `windows-powershell` sağlayıcısı eklendi. Gerçek smoke testte 3.045.355
  baytlık geçerli PNG başarıyla yakalandı ve veri kalıcılaştırılmadı.
- Yüz, nesne, OCR ve yüz kimliği opsiyonel bağımlılıkları bu ortamda kurulu
  olmadığı için sağlayıcılar doğru biçimde `available=False` bildirdi.
- Pipeline işleri süreç içinde iptal edilemez; kapanış bekleyen işleri güvenli
  biçimde tamamlar ve sıraya girmemiş işleri iptal eder.
- Kamera/kare üretimi hâlâ istemci sorumluluğundadır; sürekli kamera servisi bu
  aşamanın kapsamında değildir.

## Sonraki öneri

Aşama 14'e geçmeden önce Windows üretim makinesinde screenshot izni, çoklu ekran,
OCR/nesne sağlayıcıları ve onay sesi için kısa bir donanım smoke testi yapılmalı.
Tek-agent mimarisi stabil doğrulanmadan multi-agent etkinleştirilmemelidir.
