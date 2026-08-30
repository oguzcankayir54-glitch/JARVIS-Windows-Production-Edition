# Yedekleme, log saklama ve watchdog

## Yedek oluşturma

J.A.R.V.I.S. hafıza, servis vakaları, bilgi tabanı ve yerel ayar dosyalarını
varsayılan olarak `%USERPROFILE%\.jarvis` altında tutar. Çalışan SQLite
veritabanları düz kopyalanmaz; SQLite'ın tutarlı snapshot API'si kullanılır.

```text
jarvis-yedek olustur "%USERPROFILE%\Documents\jarvis-yedek.zip"
jarvis-yedek dogrula "%USERPROFILE%\Documents\jarvis-yedek.zip"
```

Yedek manifesti her dosyanın boyutunu ve SHA-256 özetini içerir. Yedekler
kullanıcı bilgisi içerebilir; herkese açık veya bulut klasörüne koymadan önce
veri politikanızı değerlendirin.

## Geri yükleme

Önce J.A.R.V.I.S. penceresini kapatın:

```text
jarvis-yedek geri-yukle "%USERPROFILE%\Documents\jarvis-yedek.zip" --evet
```

Komut manifesti ve tüm özetleri doğrulamadan hiçbir dosya yazmaz. Arşiv içi
yol aşımı reddedilir. Yedekte bulunmayan mevcut dosyalar silinmez.

## Log rotation

Varsayılan olarak `audit.log.jsonl` ve `requests.log.jsonl` 10 MiB sınırına
ulaşınca `.1`–`.5` arşivlerine döndürülür:

```text
JARVIS_LOG_MAX_BYTES=10485760
JARVIS_LOG_BACKUP_COUNT=5
```

`JARVIS_LOG_MAX_BYTES=0` rotation'ı kapatır.

## Windows watchdog

Kurulum kullanıcı Başlangıç klasörüne yönetici gerektirmeyen bir watchdog
kısayolu ekler. Watchdog varsayılan olarak kapalıdır; böylece panel Windows
açılışında kullanıcı istemeden başlamaz. Etkinleştirildiğinde 30 saniyede bir
yerel `/health` uç noktasını denetler. Üç ardışık başarısızlıkta ve en fazla
90 saniyede bir `JARVIS.exe`yi görünür panel/tarayıcı açmadan yeniden başlatır.
Takılmış bir başlatıcı varken ikinci bir süreç oluşturmaz.

Etkinleştirmek için `%LOCALAPPDATA%\Programs\JARVIS\jarvis.ini` içinde:

```ini
watchdog = 1
```
