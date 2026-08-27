"""Bir tur için hangi araçların modele gösterileceği.

Ölçülmüş bir sorun bu, tahmin edilmiş değil. qwen2.5:3b ile aynı sistem
istemi ve aynı sorular, yalnızca gösterilen araç sayısı değiştirilerek:

======================  ==========================  =========================
soru                    26 araç                     6 araç
======================  ==========================  =========================
"Jarvis"                İngilizce, kişiliksiz       "Efendim, dinliyorum."
"sen kimsin"            "I am a language model"     Türkçe, doğru kimlik
"cpu sıcaklığı nedir"   ``run_terminal_command``    ``get_cpu_temperature``
======================  ==========================  =========================

Yirmi altı araç şeması, beş bin karakterlik sistem istemini bastırıyor.
Model "işlev seçme" kipine giriyor; kişilik, hitap ve dil kuralları o kipte
kayboluyor — ve araç seçimi de bozuluyor. Kullanıcının üç ayrı şikâyeti
("İngilizce cevap veriyor", "beni tanımıyor", "söylediğimi anlamıyor") tek
bir sebebe çıkıyor.

**Araçları tamamen kapatmak çözüm değil.** Araçsız denendiğinde model CPU
sıcaklığını UYDURDU ("35°C"). Ölçüm yerine tahmin, bu projede kabul edilen
en son şey. Yani araç lazım; hepsi birden lazım değil.

Bu yüzden her tur için küçük ve ilgili bir alt küme gönderiliyor. Seçim
modele bırakılmıyor — modelin bunalması sorunun kendisi. Kullanıcının
cümlesindeki sözcükler karar veriyor.

Büyük bir modelde bu daraltma gereksiz: ``JARVIS_ARAC_SINIRI=0`` kapatıyor.
"""
from __future__ import annotations

from .metin import katla

#: Kategori → o kategoriyi çağrıştıran sözcükler (katlanmış hâlleriyle
#: karşılaştırılıyor, yani "sıcaklık" ve "SICAKLIK" aynı).
#:
#: Kökler yazılıyor, tam sözcükler değil: Türkçe eklemeli bir dil ve
#: "sıcaklığı", "sıcaklıktan", "sıcaklıkmış" hepsi aynı köke bakıyor.
ANAHTARLAR: dict[str, tuple[str, ...]] = {
    "sistem": ("sicakli", "isin", "derece", "ram", "bellek", "disk", "ssd",
               "hdd", "smart", "islemci", "cpu", "gpu", "ekran kart", "sistem",
               "durum", "performans", "kullani", "donanim", "makine",
               "bilgisayar", "fan", "guc", "gucu", "sogu", "hiz", "yavas", "dolu"),
    "hafiza": ("hatirla", "unutma", "not al", "kaydet", "hafiza", "biliyor",
               "soylemistim", "tercih", "unut", "aklinda"),
    "dosya": ("dosya", "klasor", "dizin", "oku", "yaz", "listele", "kaydet",
              "belge", "yol"),
    "terminal": ("komut", "calistir", "terminal", "konsol", "kabuk"),
    "vaka": ("vaka", "musteri", "servis", "ariza", "onarim", "tamir", "is emri",
             "kayit", "kaydi", "gecmis", "teshis", "playbook", "belirti", "kontrol"),
    "bilgi": ("bilgi taban", "rag", "belge", "dokuman", "proje", "kod", "ara",
              "nerede", "nasil yap", "hangi dosya"),
    "web": ("internet", "web", "site", "guncel", "fiyat", "haber", "arastir",
            "google", "bak bakalim", "sorgula"),
    # Legacy selector compatibility. The Phase-6 ToolRouter is authoritative,
    # but every registered tool still gets a category so older callers never
    # silently drop a newly added capability.
    "git": ("git", "github", "commit", "branch", "dal", "remote", "diff"),
    "uygulama": ("ac", "baslat", "calistir", "youtube", "tarayici", "program",
                 "uygulama", "ayarlar", "not defteri", "hesap makinesi"),
}

#: Araç adı → kategori. Kayıt defterindeki adlarla birebir.
KATEGORILER: dict[str, str] = {
    "get_system_info": "sistem",
    "get_cpu_temperature": "sistem",
    "get_gpu_temperature": "sistem",
    "get_ram_usage": "sistem",
    "get_disk_health": "sistem",
    "windows_system": "sistem",
    "windows_process": "sistem",
    "windows_network": "sistem",
    "windows_service": "sistem",
    "windows_window": "uygulama",
    "windows_audio": "uygulama",
    "windows_power": "sistem",
    "windows_input": "uygulama",
    "remember_fact": "hafiza",
    "recall_facts": "hafiza",
    "forget_fact": "hafiza",
    "read_file": "dosya",
    "list_directory": "dosya",
    "write_file": "dosya",
    "run_terminal_command": "terminal",
    "vaka_ac": "vaka",
    "vaka_notu_ekle": "vaka",
    "vaka_kapat": "vaka",
    "vaka_ara": "vaka",
    "acik_vakalar": "vaka",
    "vaka_detay": "vaka",
    "teshis_playbooklari": "vaka",
    "teshis_baslat": "vaka",
    "teshis_yanitla": "vaka",
    "bilgi_ara": "bilgi",
    "bilgi_durum": "bilgi",
    "web_ara": "web",
    "web_oku": "web",
    "git_status": "git",
    "git_log": "git",
    "git_diff": "git",
    "git_remote": "git",
    "tarayici_ac": "uygulama",
    "arama_ac": "uygulama",
    "uygulama_ac": "uygulama",
    "uygulama_listesi": "uygulama",
}

#: Hiçbir kategori tutmadığında gönderilenler.
#:
#: Boş liste göndermek cazip ama yanlış: araçsız kalan model CPU sıcaklığını
#: uyduruyor. Bunlar "kullanıcı ne sorarsa sorsun yanlış cevaba karşı en
#: ucuz sigorta" olanlar.
#:
#: ``bilgi_ara`` bu listedeydi ve ÇIKARILDI. Hiçbir kategori tutmayan
#: cümleler sohbet cümleleridir — ölçüldü: "Nasılsın Jarvis?", "Canım
#: sıkılıyor.", "Bugün biraz yoruldum.", "Ben senin geliştiricinim."
#: dördü de buraya düşüyor. Belge arama aracını sohbetin ortasında masaya
#: koymak, modele kullanacak bahane aramaktan başka bir şey yaptırmıyordu.
#: Belge sorusu zaten "bilgi" kategorisini tetikliyor; sigortaya gerek yok.
VARSAYILAN = ("get_system_info", "recall_facts")

#: Bir turda gösterilecek en fazla araç.
#:
#: Altı araçla ölçüm temizdi, yirmi altıyla bozuktu; sekiz ikisinin arasında
#: ve bir kategorinin tamamını (sistem: beş araç) artı birkaç komşusunu
#: taşıyacak kadar geniş.
VARSAYILAN_SINIR = 8


def _ad(sema: dict) -> str:
    return (sema.get("function") or {}).get("name", "")


#: Birebir eşleşmesi gereken en kısa kök.
#:
#: Uygulama kataloğunda aynı ders alınmıştı: parça eşlemesine bırakılan kısa
#: bir ad her şeyi yakalıyor. Burada "ac" kökü "acaba", "acil" ve "araç"
#: sözcüklerini de tutardı.
_EN_KISA_KOK = 4


def _tutuyor(kok: str, sozcukler: list[str], tam_metin: str) -> bool:
    """Bu kök cümlede geçiyor mu.

    Boşluklu kökler ("ekran kart") metnin tamamında aranıyor. Tek sözcüklü
    olanlar SÖZCÜK BAŞINDAN eşleşiyor: Türkçe eklemeli bir dil, ve
    "sıcaklıktan" da "sıcaklık" demektir.

    Köklerin sonu bilerek kısa: ünsüz yumuşaması yüzünden "sıcaklık"
    çekimlenince "sıcaklığı" oluyor ve k → ğ dönüşümü tam kökü eşleşmez
    yapıyor. Kök "sicakli" olduğunda her iki hâli de tutuyor.
    """
    if " " in kok:
        return kok in tam_metin
    if len(kok) < _EN_KISA_KOK:
        return kok in sozcukler
    return any(s.startswith(kok) for s in sozcukler)


def kategorileri_bul(metin: str) -> list[str]:
    """Cümlenin çağrıştırdığı kategoriler, en güçlüden zayıfa."""
    aranan = katla(metin or "")
    if not aranan.strip():
        return []
    sozcukler = "".join(c if c.isalnum() else " " for c in aranan).split()
    puanlar: list[tuple[int, str]] = []
    for kategori, kokler in ANAHTARLAR.items():
        puan = sum(1 for k in kokler if _tutuyor(k, sozcukler, aranan))
        if puan:
            puanlar.append((puan, kategori))
    puanlar.sort(key=lambda p: (-p[0], p[1]))
    return [k for _, k in puanlar]


def araclari_sec(semalar: list[dict], metin: str,
                 sinir: int = VARSAYILAN_SINIR) -> list[dict]:
    """Bu tur için gösterilecek şemalar.

    ``sinir`` sıfır ya da negatifse daraltma yapılmıyor: büyük bir model
    yirmi altı aracı sorunsuz taşıyor ve daraltmak orada yalnızca yetenek
    kaybı olurdu.
    """
    if sinir is None or sinir <= 0 or len(semalar) <= sinir:
        return semalar

    sirali = kategorileri_bul(metin)
    secilen: list[dict] = []
    alinan: set[str] = set()

    def ekle(sema: dict) -> None:
        ad = _ad(sema)
        if ad and ad not in alinan:
            alinan.add(ad)
            secilen.append(sema)

    # Once eslesen kategoriler, guclu olandan basliyarak.
    for kategori in sirali:
        for sema in semalar:
            if KATEGORILER.get(_ad(sema)) == kategori:
                ekle(sema)
        if len(secilen) >= sinir:
            break

    # Hicbir sey tutmadiysa ya da yer kaldiysa varsayilanlar.
    for ad in VARSAYILAN:
        if len(secilen) >= sinir:
            break
        for sema in semalar:
            if _ad(sema) == ad:
                ekle(sema)

    return secilen[:sinir]
