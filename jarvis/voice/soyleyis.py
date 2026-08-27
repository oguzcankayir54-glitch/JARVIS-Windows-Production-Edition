"""Kısaltmaları sese vermeden önce Türkçe okunuşuna çevirmek.

Şikâyet şuydu: *"türkçe terimleri söyleyemiyor."* Bir kısmı sesin suçuydu,
ama ölçünce görüldü ki iyi ses de aynı yerde tökezliyor — çünkü hata metinde.

Bir Türkçe seslendirici ``BIOS`` gördüğünde onu Türkçe bir sözcük sanıp
"boz" diye okuyor. ``S.M.A.R.T.`` noktalarla yazıldığı için başka bir şeye
dönüşüyor. ``SSD'nin`` ise hem kısaltma hem ek taşıyor. Bunların hiçbiri
seslendiricinin çözebileceği bir şey değil; okunuşu metinde vermek gerekiyor.

Ölçüm (aynı cümle, sentezle → Whisper ile yazıya dök → kaynakla karşılaştır):

===================================  ==============
ses                                  anlaşılırlık
===================================  ==============
piper tr_TR-dfki (okunuş düzeltmesiz)     0.65
edge tr-TR-Ahmet (okunuş düzeltmesiz)     0.82
edge tr-TR-Ahmet (okunuş düzeltmeli)      0.94
===================================  ==============

Bu katman yalnızca **sese giden** metni değiştiriyor. Panelde ve kayıtta
yazılış olduğu gibi kalıyor: ekrana "es es de" yazmak okumayı zorlaştırırdı.
"""
from __future__ import annotations

import re

#: Türk alfabesinde harflerin adı. Tabloda olmayan bir kısaltma harf harf
#: bununla okunuyor — İngilizce harf adları ("es-es-di") Türkçe bir ses için
#: yanlış, ve seslendirici zaten onları bilmiyor.
HARF_ADLARI = {
    "A": "a", "B": "be", "C": "ce", "Ç": "çe", "D": "de", "E": "e",
    "F": "fe", "G": "ge", "Ğ": "yumuşak ge", "H": "ha", "I": "ı", "İ": "i",
    "J": "je", "K": "ka", "L": "le", "M": "me", "N": "ne", "O": "o",
    "Ö": "ö", "P": "pe", "Q": "ku", "R": "re", "S": "se", "Ş": "şe",
    "T": "te", "U": "u", "Ü": "ü", "V": "ve", "W": "çift ve", "X": "iks",
    "Y": "ye", "Z": "ze",
}

#: Sözcük gibi okunan ya da yerleşik bir söylenişi olan kısaltmalar.
#: Harf harf hecelemek bunları BOZAR: "bayos" doğru, "be i o se" değil.
#: Anahtarlar büyük harfle; arama büyük/küçük ayrımı olmadan yapılıyor.
OKUNUS: dict[str, str] = {
    # --- donanım ---
    "BIOS": "bayos",
    "UEFI": "yuefi",
    "CMOS": "simos",
    "POST": "post",
    "SSD": "es es de",
    "HDD": "ha de de",
    "NVME": "en vi em i",
    "SATA": "sata",
    "PCIE": "pi si ay i",
    "PCI": "pi si ay",
    "RAM": "ram",
    "ROM": "rom",
    "ECC": "e ce ce",
    "IDE": "i de e",
    "ACPI": "a ce pe i",
    "UPS": "yu pe es",
    "OLED": "oled",
    "AMD": "a em de",
    "ESD": "e es de",
    "DDR": "de de re",
    "CPU": "işlemci",
    "GPU": "ekran kartı",
    "PSU": "güç kaynağı",
    "SMART": "smart",
    "TPM": "te pe em",
    "LED": "led",
    "RGB": "er ge be",
    "USB": "u es be",
    "HDMI": "ha de em i",
    "VGA": "ve ge a",
    "DVI": "de ve i",
    "ATX": "atiks",
    "ARM": "arm",
    "OEM": "o e em",
    "SN": "seri numarası",

    # --- yazılım / sistem ---
    "OS": "işletim sistemi",
    "EXE": "ekse",
    "DLL": "de le le",
    "ISO": "iso",
    "GPT": "ge pe te",
    "MBR": "em be re",
    "NTFS": "en te ef es",
    "FAT": "fat",
    "RAID": "reyd",
    "VM": "sanal makine",
    "SFC": "es ef ce",
    "CMD": "komut istemi",
    "PS": "pe se",

    # --- ağ ---
    "IP": "ay pi",
    "DNS": "de en es",
    "DHCP": "de ha ce pe",
    "LAN": "yerel ağ",
    "WAN": "geniş alan ağı",
    "WIFI": "vayfay",
    "WI-FI": "vayfay",
    "VPN": "ve pe en",
    "URL": "u er el",
    "HTTP": "ha te te pe",
    "HTTPS": "ha te te pe es",
    "API": "a pe i",
    "SSH": "es es ha",
    "FTP": "ef te pe",
    "MAC": "mak",

    # --- birimler ---
    "KB": "kilobayt",
    "MB": "megabayt",
    "GB": "gigabayt",
    "TB": "terabayt",
    "MHZ": "megahertz",
    "GHZ": "gigahertz",
    "MBPS": "megabit",
    "GBPS": "gigabit",
    "RPM": "devir",
    "°C": "santigrat derece",
}

#: Harf harf hecelemenin uygulanacağı en uzun kısaltma. Bunun üstü büyük
#: ihtimalle bağırılan bir cümledir, kısaltma değil.
EN_UZUN_HECELEME = 5

#: Noktalı kısaltma: S.M.A.R.T. / A.B.D. — en az iki "harf+nokta".
_NOKTALI = re.compile(r"\b(?:[A-ZÇĞİÖŞÜ]\.){2,}")

#: Kısaltma gövdesi + isteğe bağlı Türkçe ek: SSD'nin, RAM'i, BIOS'u.
#: Ek ayrı tutuluyor; "es es de'nin" doğru okunuyor, "es es denin" okunmuyor.
_KISALTMA = re.compile(
    r"\b([A-ZÇĞİÖŞÜ][A-ZÇĞİÖŞÜ0-9\-]{1,%d})('[a-zçğıöşü]+)?\b" % (EN_UZUN_HECELEME - 1)
)

#: Sayıya yapışık birim: 500GB, 3.5GHz, 67°C.
_BIRIMLI_SAYI = re.compile(r"(\d)\s?(°C|[KMGT]B|[MG]Hz|[MG]bps)\b", re.IGNORECASE)


def _hecele(kisaltma: str) -> str:
    """Bilinmeyen bir kısaltmayı Türk alfabesinin harf adlarıyla oku."""
    parcalar = [HARF_ADLARI.get(h, h) for h in kisaltma if h != "-"]
    return " ".join(p for p in parcalar if p)


def _cozumle(kisaltma: str) -> str | None:
    """Bir kısaltmanın okunuşu; okunmaması gerekiyorsa None."""
    anahtar = kisaltma.upper().replace(".", "")
    if anahtar in OKUNUS:
        return OKUNUS[anahtar]
    # Rakam içeren bir şey (X570, RTX4090) model adıdır; seslendirici bunu
    # zaten makul okuyor, hecelemek anlaşılmaz yapardı.
    if any(k.isdigit() for k in anahtar):
        return None
    if len(anahtar) > EN_UZUN_HECELEME:
        return None
    # Türkçede sesli harfsiz bir dizi sözcük olamaz; kesin kısaltmadır.
    # Sesli harf içerenler (POST, RAID) tabloda yoksa bırakılıyor: büyük
    # ihtimalle vurgu için büyük yazılmış gerçek bir sözcüktür.
    if any(h in "AEIİOÖUÜ" for h in anahtar):
        return None
    return _hecele(anahtar)


def okunusa_cevir(metin: str) -> str:
    """Kısaltmaları Türkçe okunuşlarıyla değiştir.

    Yalnızca seslendiriciye giden kopyada çağrılıyor. Ekrandaki yazı
    değişmiyor — "SSD" yazısı okunaklı, "es es de" değil.
    """
    if not metin:
        return metin

    # Tamamı büyük harfle yazılmış bir metin bağırmadır, kısaltma listesi
    # değil; harf harf hecelemek onu tamamen anlaşılmaz yapardı.
    harfler = [k for k in metin if k.isalpha()]
    hepsi_buyuk = bool(harfler) and all(k.isupper() for k in harfler)

    def noktali(eslesme: re.Match[str]) -> str:
        ham = eslesme.group(0).replace(".", "")
        return _cozumle(ham) or _hecele(ham)

    metin = _NOKTALI.sub(noktali, metin)

    def birim(eslesme: re.Match[str]) -> str:
        okunus = OKUNUS.get(eslesme.group(2).upper())
        return f"{eslesme.group(1)} {okunus}" if okunus else eslesme.group(0)

    metin = _BIRIMLI_SAYI.sub(birim, metin)

    if hepsi_buyuk:
        return metin

    def kisaltma(eslesme: re.Match[str]) -> str:
        okunus = _cozumle(eslesme.group(1))
        if okunus is None:
            return eslesme.group(0)
        return okunus + (eslesme.group(2) or "")

    return _KISALTMA.sub(kisaltma, metin)
