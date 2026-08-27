"""Panel, intent router tests and LLM prompt share this natural command catalog."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandExample:
    category: str
    text: str
    purpose: str
    intent: str


def _group(category: str, purpose: str, intent: str, *texts: str) -> tuple[CommandExample, ...]:
    return tuple(CommandExample(category, text, purpose, intent) for text in texts)


COMMAND_EXAMPLES: tuple[CommandExample, ...] = (
    *_group("Sistem", "Sistem donanım durumunu kontrol eder.", "system_monitor",
        "Sistem durumu nasıl?", "CPU kullanımı kaç?", "İşlemci sıcaklığı kaç?", "RAM kullanımı ne durumda?",
        "Bellek kullanımını göster.", "Disk kullanımına bak.", "Disk sağlığı nasıl?", "SSD durumunu kontrol et.",
        "GPU kullanımını göster.", "Ekran kartı sıcaklığı kaç?", "Fan durumunu kontrol et.",
        "Donanım durumunu göster.", "Sistem yükü ne durumda?", "Boş RAM miktarını göster.",
        "Diskte ne kadar yer kaldı?", "Bilgisayarın kaynak kullanımını göster."),
    *_group("Bilgisayar", "İstenen güvenli uygulamayı veya siteyi açar.", "computer_control",
        "Görev yöneticisini aç.", "Hesap makinesini aç.", "Not defterini aç.", "Ayarları aç.",
        "Chrome'u aç.", "Tarayıcıyı aç.", "YouTube'u aç.", "Dosya gezginini aç.", "Paint'i aç.",
        "Komut istemini aç.", "PowerShell'i aç.", "Denetim masasını aç.", "Aygıt yöneticisini aç.",
        "Disk yönetimini aç.", "Sistem bilgilerini aç.", "Windows güvenliğini aç."),
    *_group("Hafıza", "Bilgiyi kaydeder veya kayıtlı bilgiyi getirir.", "memory",
        "Bunu hatırla: Ana çalışma diskim C sürücüsü.", "Şunu hatırla: Yedekler D sürücüsünde.",
        "Unutma: Tercih ettiğim dil Türkçe.", "Bunu kaydet: Test bilgisayarı Windows 11 kullanıyor.",
        "Hatırla: Projelerim C:\\Projeler klasöründe.", "Not al: Ana tarayıcım Chrome.",
        "Aklında tut: Sunucu adı JARVIS-SERVER.", "Bunu kaydet: Servis kodum 1042.",
        "Benim hakkımda neler biliyorsun?", "Kayıtlı tercihlerimi hatırlat.",
        "Daha önce sana ne kaydettim?", "Hafızandaki bilgileri göster.",
        "Ana çalışma diskimi hatırlıyor musun?", "Yedeklerin yerini hatırlıyor musun?",
        "Tercih ettiğim dili hatırlıyor musun?", "Projelerimin yerini hatırlat."),
    *_group("Servis", "Servis vakalarını açar, arar veya takip eder.", "task",
        "Açık vakaları göster.", "Bekleyen vakaları listele.", "Son vakaları göster.",
        "Yeni vaka aç: Laptop açılıyor ama görüntü gelmiyor.", "Yeni vaka aç: Bilgisayar çok yavaş çalışıyor.",
        "Yeni vaka aç: SSD sistemde görünmüyor.", "Yeni vaka aç: Cihaz internete bağlanmıyor.",
        "Yeni vaka aç: Fan çok sesli çalışıyor.", "Yeni vaka aç: Windows başlamıyor.",
        "Yeni vaka aç: USB bağlantıları çalışmıyor.", "Geçmiş vakalarda görüntü sorununu ara.",
        "Geçmiş vakalarda SSD sorununu ara.", "Vakalarda aşırı ısınma sorununu ara.",
        "Vakalarda mavi ekran sorununu ara.", "Açık servis vakalarını getir.", "Kapanmamış vakaları göster."),
    *_group("Bilgi", "Yerel bilgi tabanındaki belgeleri arar.", "rag_query",
        "Bilgi tabanında NVMe sorununu ara.", "Bilgi tabanında mavi ekranı ara.",
        "Bilgi tabanında RAM arızasını ara.", "Bilgi tabanında SSD sağlığını ara.",
        "Bilgi tabanında Windows kurulumunu ara.", "Bilgi tabanında sürücü sorunlarını ara.",
        "Bilgi tabanında ağ sorununu ara.", "Bilgi tabanında BIOS güncellemesini ara.",
        "Bilgi tabanında fan temizliğini ara.", "Bilgi tabanında veri kurtarmayı ara.",
        "Belgelerde ekran kartı sorununu ara.", "Dokümanlarda sistem donmasını ara.",
        "Yerel belgelerde yazıcı sorununu ara.", "Bilgi tabanından termal macun bilgisini bul.",
        "Bilgi tabanından disk klonlama bilgisini bul.", "Arşivde batarya sorununu ara."),
    *_group("İnternet", "Güncel bilgi için internette arama yapar.", "web_research",
        "İnternette RTX 3080 Ti sürücüsünü araştır.", "İnternette Windows güncellemesini araştır.",
        "Webde en güncel NVIDIA sürücüsünü ara.", "İnternette bu hata kodunu araştır: 0x80070005.",
        "Webde SSD fiyatlarını araştır.", "İnternette güncel BIOS sürümünü ara.",
        "İnternette bu anakartın özelliklerini araştır.", "Webde işlemci karşılaştırması yap.",
        "İnternette Windows 11 gereksinimlerini ara.", "Webde en son güvenlik haberlerini ara.",
        "İnternette bu cihazın kullanım kılavuzunu bul.", "Webde ağ sürücüsünü araştır.",
        "İnternette bu yazılımın son sürümünü ara.", "Webde güncel RAM fiyatlarını araştır.",
        "İnternette ekran kartı güç tüketimini ara.", "Webde bu hata mesajını araştır."),
    *_group("Dosyalar", "Dosya veya klasör içeriğini güvenli biçimde gösterir.", "coding",
        "Klasörü listele: C:\\Projeler", "Klasörü listele: C:\\Users\\Public", "Klasörü listele: D:\\Yedekler",
        "Dizini listele: C:\\Windows\\Temp", "Dizini listele: C:\\ProgramData",
        "Dosyayı oku: C:\\Projeler\\README.md", "Dosyayı oku: C:\\Temp\\notlar.txt",
        "Dosyayı oku: D:\\Yedekler\\rapor.txt", "Oku: C:\\Projeler\\ayarlar.json",
        "Oku: C:\\Temp\\sonuc.log", "Klasörü listele: C:\\Temp", "Dizini listele: D:\\Projeler",
        "Dosyayı oku: C:\\Projeler\\requirements.txt", "Oku: C:\\Projeler\\pyproject.toml",
        "Klasörü listele: C:\\Users\\Public\\Documents", "Dosyayı oku: C:\\Temp\\hata.txt"),
    *_group("Git", "Git deposunun durumunu ve geçmişini inceler.", "github",
        "GitHub'daki son commitlere bak.", "GitHub repo durumunu göster.", "GitHub deposundaki değişiklikleri göster.",
        "Git commit geçmişini göster.", "Git branch listesini göster.", "GitHub remote adreslerini göster.",
        "GitHub repository durumunu kontrol et.", "Repo içindeki son commitleri göster.",
        "Repository değişikliklerine bak.", "GitHub branch durumuna bak.", "GitHub deposunun farklarını göster.",
        "Repo geçmişini incele.", "GitHub remote bilgisini göster.", "Repository durumunu özetle.",
        "Son Git commitini göster.", "Git branch bilgisini getir."),
)


_CATEGORY_GUIDANCE = {
    "Sistem": "CPU, RAM, disk, GPU, sıcaklık ve donanım durumu",
    "Bilgisayar": "izinli uygulamaları ve siteleri açma",
    "Hafıza": "kullanıcı bilgisini kaydetme ve geri çağırma",
    "Servis": "servis vakası açma, listeleme ve arama",
    "Bilgi": "yerel belge ve bilgi tabanında arama",
    "İnternet": "güncel bilgi için web araştırması",
    "Dosyalar": "açıkça belirtilen dosyayı okuma veya klasörü listeleme",
    "Git": "depo durumu, geçmişi, branch, remote ve değişiklikleri inceleme",
}


def command_guide_prompt() -> str:
    """Keep the full panel catalog out of the model context to avoid prompt bloat."""
    lines = ["DOĞAL KOMUT REHBERİ:",
             "Komutlar kesin kalıplar değildir; kısa ve farklı Türkçe ifadelerde aynı niyeti anla.",
             "Yalnız istenen güvenli aracı kullan; zorunlu bilgi eksikse kısa bir soru sor.",
             "NİYET KATEGORİLERİ:"]
    lines.extend(f"- {name}: {description}." for name, description in _CATEGORY_GUIDANCE.items())
    lines.append("TEMSİLİ ÖRNEKLER:")
    for category in _CATEGORY_GUIDANCE:
        samples = [item for item in COMMAND_EXAMPLES if item.category == category][:2]
        lines.extend(f"- {item.text} → {item.purpose}" for item in samples)
    return "\n".join(lines)


def panel_rows() -> list[dict[str, str]]:
    return [{"ad": item.category, "deger": item.text, "aciklama": item.purpose, "komut": item.text}
            for item in COMMAND_EXAMPLES]
