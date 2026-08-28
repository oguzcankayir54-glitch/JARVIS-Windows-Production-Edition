# Ajanda ve yerel bildirimler

J.A.R.V.I.S. görev, randevu ve teslim tarihlerini ana bellek veritabanında
kalıcı olarak saklar. Ajanda sekmesinden kayıt eklenebilir ve tamamlanabilir;
aynı işlemler sohbet içinde `ajanda_ekle`, `ajanda_listele` ve `ajanda_durum`
araçlarıyla yapılır.

Naif ISO tarihleri Windows'un yerel saat diliminde yorumlanır. Hatırlatma
zamanı verilmezse son tarih kullanılır. Açık servis vakalarının `promised_ts`
teslim zamanı bir saat kala ayrıca bildirilir.

Windows bildirimleri yalnızca oturumdaki PowerShell/Windows Toast API üzerinden
gösterilir; başlık ve içerik hiçbir dış servise gönderilmez. Linux geliştirme
ve test ortamında sağlayıcı güvenli biçimde kapalıdır. Bildirim gösterilemezse
ajanda kaydı işaretlenmez ve sonraki turda tekrar denenir.

Hatırlatma tarama aralığı `.env` içinde saniye olarak değiştirilebilir:

```dotenv
JARVIS_REMINDER_INTERVAL=30
```
