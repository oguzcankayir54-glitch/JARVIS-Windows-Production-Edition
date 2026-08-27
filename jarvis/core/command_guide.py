"""Natural-language command examples shared by the panel and the LLM prompt.

These are examples, not magic phrases.  Keeping them in one module prevents the
panel from advertising a sentence that the model was never taught to interpret.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CommandExample:
    category: str
    text: str
    purpose: str


COMMAND_EXAMPLES: tuple[CommandExample, ...] = (
    CommandExample("Sistem", "Sistem durumu nasıl?", "CPU, RAM, GPU ve diski kontrol eder."),
    CommandExample("Sistem", "CPU sıcaklığı kaç?", "İşlemci sıcaklığını okur."),
    CommandExample("Sistem", "RAM kullanımı ne durumda?", "Bellek kullanımını gösterir."),
    CommandExample("Sistem", "Disk sağlığına bak.", "Disk ve SMART durumunu kontrol eder."),
    CommandExample("Bilgisayar", "Görev yöneticisini aç.", "Görev Yöneticisi'ni açar."),
    CommandExample("Bilgisayar", "Hesap makinesini aç.", "Hesap Makinesi'ni açar."),
    CommandExample("Bilgisayar", "YouTube'u aç.", "YouTube'u tarayıcıda açar."),
    CommandExample("Hafıza", "Bunu hatırla: Ana çalışma diskim C sürücüsü.", "Kalıcı bir bilgi kaydeder."),
    CommandExample("Hafıza", "Benim hakkımda neler biliyorsun?", "Kayıtlı bilgileri getirir."),
    CommandExample("Servis", "Açık vakaları göster.", "Bekleyen servis vakalarını listeler."),
    CommandExample("Servis", "Yeni vaka aç: laptop açılıyor ama görüntü gelmiyor.", "Yeni servis kaydı başlatır."),
    CommandExample("Servis", "Geçmiş vakalarda görüntü gelmiyor sorununu ara.", "Benzer eski vakaları arar."),
    CommandExample("Bilgi", "Bilgi tabanında NVMe sorununu ara.", "Yerel belge arşivini tarar."),
    CommandExample("İnternet", "İnternette RTX 3080 Ti sürücüsünü araştır.", "Güncel web araması yapar."),
    CommandExample("Dosyalar", "Klasörü listele: C:\\Projeler", "Bir klasörün içeriğini gösterir."),
    CommandExample("Git", "GitHub'daki son commitlere bak.", "Yerel depo geçmişini inceler."),
)


def command_guide_prompt() -> str:
    """Compact few-shot guidance for Qwen and other tool-capable providers."""
    lines = [
        "DOĞAL KOMUT REHBERİ:",
        "Aşağıdakiler ezberlenmesi gereken kesin kalıplar değil, kullanıcı niyeti örnekleridir.",
        "Kullanıcı aynı isteği farklı ve kısa bir Türkçe cümleyle söylerse aynı niyeti anla.",
        "Yalnız gerçekten istenen aracı kullan; eksik zorunlu bilgi varsa kısa bir soru sor.",
    ]
    lines.extend(f'- {item.text} → {item.purpose}' for item in COMMAND_EXAMPLES)
    return "\n".join(lines)


def panel_rows() -> list[dict[str, str]]:
    """JSON-ready rows for the panel command guide."""
    return [
        {
            "ad": item.category,
            "deger": item.text,
            "aciklama": item.purpose,
            "komut": item.text,
        }
        for item in COMMAND_EXAMPLES
    ]
