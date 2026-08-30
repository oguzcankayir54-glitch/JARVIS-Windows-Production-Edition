"""Sunucunun yayınladığı her olayın panelde bir karşılığı var mı.

Bu test bir birleştirme kazasından doğdu. Sesli duyuru özelliği iki
parçadan oluşuyor: sunucu ``hub.publish("duyuru", …)`` ile bir ses
kimliği yayınlıyor, panel de onu dinleyip sesi çalıyor. Bir merge
sırasında panel dosyası karşı tarafın hâline geri döndü ve **dinleyici
düştü.** Sunucu konuşmaya devam etti, panel duymadı.

Hiçbir test kırmızı olmadı. ``test_duyuru.py`` politikayı sınıyor,
``test_duyuru_panel.py`` sunucunun olayı yayınladığını sınıyor — ikisi de
kendi tarafında doğru. Kopan şey **aradaki tel**, ve teli kimse
sınamıyordu.

Burada sınanan şey davranış değil, **bağlantının varlığı**. Zayıf bir
test: dinleyicinin doğru şeyi yaptığını göstermiyor, yalnızca var
olduğunu gösteriyor. Ama kaybolan şey tam olarak buydu ve maliyeti
sessizce ölü bir özellikti.

``DINLEYICISIZ`` kümesi bugünkü gerçeği kayda geçiriyor, onaylamıyor:
``agenda`` ve ``diagnostic`` bu kazadan önce de yayınlanıyordu ve
panelde hiçbir karşılıkları yoktu. Kasıtlı mı, unutulmuş mu bilmiyoruz.
Bilinen tek şey artık şu: **dördüncüsü sessizce eklenemez.**
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

KOK = Path(__file__).resolve().parent.parent
SUNUCU = KOK / "jarvis" / "web" / "server.py"
PANEL = KOK / "docs" / "mockups" / "jarvis-panel.html"

#: Sunucunun yayınladığı ama panelin dinlemediği olaylar. Bir olayı
#: buraya eklemek bilinçli bir karar olmalı — testin bütün amacı o kararın
#: sessizce alınamaması.
DINLEYICISIZ = {
    "agenda",      # bu testten önce de dinleyicisi yoktu
    "diagnostic",  # bu testten önce de dinleyicisi yoktu
}


def _yayinlananlar() -> set[str]:
    kaynak = SUNUCU.read_text(encoding="utf-8")
    return set(re.findall(r'hub\.publish\(\s*"([a-z._]+)"', kaynak))


def _dinlenenler() -> set[str]:
    kaynak = PANEL.read_text(encoding="utf-8")
    return set(re.findall(r'es\.addEventListener\(\s*"([a-z._]+)"', kaynak))


def test_the_panel_listens_for_the_spoken_announcement():
    """Kaybolan tel. Bu satır düşerse sesli uyarı sessizce ölür."""
    assert "duyuru" in _dinlenenler(), (
        "Panelde 'duyuru' dinleyicisi yok. Sunucu ses kimliğini yayınlıyor "
        "ama kimse çalmıyor — sesli duyuru özelliği ölü."
    )


def test_every_published_event_has_a_listener_or_is_declared():
    yayinlanan = _yayinlananlar()
    dinlenen = _dinlenenler()
    kopuk = yayinlanan - dinlenen - DINLEYICISIZ
    assert not kopuk, (
        f"Sunucu şu olayları yayınlıyor ama panel dinlemiyor: {sorted(kopuk)}. "
        "Ya panele dinleyici ekleyin ya da bilinçli bir karar olarak "
        "DINLEYICISIZ kümesine yazın."
    )


def test_the_declared_exceptions_are_still_real():
    """Muafiyet listesi kendi kendini temizlesin.

    Bir olaya sonradan dinleyici eklenirse buradan da düşmeli; yoksa
    liste zamanla anlamsız bir kalıntıya dönüşür ve kimse ona bakmaz.
    """
    fazla = DINLEYICISIZ & _dinlenenler()
    assert not fazla, (
        f"Şu olaylar artık dinleniyor, DINLEYICISIZ kümesinden çıkarın: "
        f"{sorted(fazla)}"
    )


def test_the_declared_exceptions_are_still_published():
    fazla = DINLEYICISIZ - _yayinlananlar()
    assert not fazla, (
        f"Şu olaylar artık yayınlanmıyor, DINLEYICISIZ kümesinden çıkarın: "
        f"{sorted(fazla)}"
    )


@pytest.mark.parametrize("yol", [SUNUCU, PANEL])
def test_the_files_this_test_reads_still_exist(yol):
    """İki dosya da taşınırsa yukarıdaki testler boş küme üzerinde
    sessizce yeşil kalırdı — o hâlde test değil, süs olurlardı."""
    assert yol.is_file(), f"{yol} bulunamadı; bu testler artık hiçbir şey ölçmüyor."
