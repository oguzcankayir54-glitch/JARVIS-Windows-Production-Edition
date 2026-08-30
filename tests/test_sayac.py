"""Yutulan hataların sayılması.

``except Exception: return None`` kalıyor — bilgi indeksinin çökmesi bir
turu düşürmemeli. Değişen tek şey, o bloğun kaç kez çalıştığının
görünür olması. Aradaki fark ölçülebilir: indeks kırk kez okunamadıysa
JARVIS kırk turda bilgi tabanı yokmuş gibi cevap veriyor ve tek belirti
"bilmiyor" oluyor.
"""
from __future__ import annotations

from jarvis.core.sayac import EN_FAZLA_AD, SAYACLAR, Sayaclar, yut


def test_counting_starts_at_zero():
    s = Sayaclar()
    assert s.adet("bilgi.indeks") == 0
    assert s.dokum() == ()


def test_each_swallowed_error_is_counted():
    s = Sayaclar()
    for _ in range(3):
        s.say("bilgi.indeks")
    assert s.adet("bilgi.indeks") == 3


def test_the_exception_class_is_kept_but_not_its_message():
    """Sınıf adı iki arızayı ayırmaya yetiyor (indeks bozuk mu, disk mi
    dolu). Mesaj tutulmuyor: içinde dosya yolu veya sorgu metni olabilir
    ve buranın işi kullanıcı verisini diske taşımak değil."""
    s = Sayaclar()
    s.say("bilgi.indeks", OSError("/home/deniz/gizli-klasor okunamadı"))
    (kayit,) = s.dokum()
    assert kayit.son_tur == "OSError"
    assert "deniz" not in repr(kayit)


def test_the_dump_is_ordered_by_count():
    """Panelde önce en çok tekrarlayan görünmeli; asıl arıza o."""
    s = Sayaclar()
    s.say("az")
    for _ in range(5):
        s.say("cok")
    assert [d.ad for d in s.dokum()] == ["cok", "az"]


def test_the_time_of_the_last_failure_is_recorded():
    saat = iter([100.0, 200.0])
    s = Sayaclar(clock=lambda: next(saat))
    s.say("x")
    s.say("x")
    assert s.dokum()[0].son_zaman == 200.0


def test_a_nameless_counter_still_lands_somewhere():
    s = Sayaclar()
    s.say("")
    assert s.adet("bilinmeyen") == 1


def test_the_name_space_is_bounded():
    """Sayaç adı yanlışlıkla değişken bir şeyden üretilirse (dosya yolu,
    oturum kimliği) sözlük sınırsız büyür. Sessiz hatayı görünür kılmak
    için eklenen şey, sessiz bir bellek sızıntısı olamaz."""
    s = Sayaclar()
    for i in range(EN_FAZLA_AD + 20):
        s.say(f"ad-{i}")
    assert len(s.dokum()) == EN_FAZLA_AD
    assert s.tasan == 20


def test_a_known_name_keeps_counting_after_the_limit():
    """Sınır YENİ ad açmayı durduruyor; mevcut sayaç çalışmaya devam
    ediyor. Tersi olsaydı sınır, asıl izlemek istediğimiz sayacı
    dondururdu."""
    s = Sayaclar()
    s.say("bilgi.indeks")
    for i in range(EN_FAZLA_AD + 5):
        s.say(f"gurultu-{i}")
    s.say("bilgi.indeks")
    assert s.adet("bilgi.indeks") == 2


def test_reset_clears_everything():
    s = Sayaclar()
    s.say("x", ValueError("v"))
    s.sifirla()
    assert s.dokum() == () and s.toplam() == 0 and s.tasan == 0


def test_the_module_helper_writes_to_the_shared_counters():
    SAYACLAR.sifirla()
    try:
        yut("test.kanal", RuntimeError("bir şey"))
        assert SAYACLAR.adet("test.kanal") == 1
    finally:
        SAYACLAR.sifirla()


def test_counting_is_thread_safe():
    """Sayaçlar arka plan iş parçacıklarından da artıyor (monitor,
    RAG eşitleme). Kilitsiz bir ``+= 1`` burada sessizce eksik sayar."""
    import threading

    s = Sayaclar()

    def calis():
        for _ in range(500):
            s.say("ortak")

    isler = [threading.Thread(target=calis) for _ in range(4)]
    for i in isler:
        i.start()
    for i in isler:
        i.join()
    assert s.adet("ortak") == 2000
