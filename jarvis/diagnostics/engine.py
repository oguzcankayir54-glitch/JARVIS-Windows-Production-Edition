"""Deterministic diagnostic decision trees linked to service cases."""
from __future__ import annotations

from dataclasses import dataclass

from ..memory.cases import CaseError, CaseStore


class DiagnosticError(ValueError):
    pass


@dataclass(frozen=True)
class Option:
    id: str
    label: str
    next_node: str


@dataclass(frozen=True)
class Node:
    id: str
    prompt: str
    guidance: str
    options: tuple[Option, ...] = ()
    conclusion: str = ""


@dataclass(frozen=True)
class Playbook:
    id: str
    title: str
    description: str
    first_node: str
    nodes: dict[str, Node]


def _option(id: str, label: str, next_node: str) -> Option:
    return Option(id, label, next_node)


PLAYBOOKS: dict[str, Playbook] = {
    "guc-yok": Playbook("guc-yok", "Güç yok / açılmıyor",
        "Hiç tepki vermeyen masaüstü veya dizüstü cihaz", "enerji", {
        "enerji": Node("enerji", "Priz/adaptör çıkışı doğrulandı mı?",
            "Multimetre veya bilinen sağlam priz/adaptör kullanın; kapağı açmadan başlayın.",
            (_option("evet", "Evet, enerji sağlam", "tepki"),
             _option("hayir", "Hayır / enerji yok", "enerji_sonuc"))),
        "enerji_sonuc": Node("enerji_sonuc", "", "", conclusion=
            "Harici enerji yolu arızalı: priz, kablo veya adaptörü değiştirip yeniden doğrulayın."),
        "tepki": Node("tepki", "Güç düğmesine basınca LED, fan veya ses var mı?",
            "Tepkiyi gözleyin; bileşen sökmeden önce sonucu kaydedin.",
            (_option("var", "Kısa da olsa tepki var", "minimal"),
             _option("yok", "Hiç tepki yok", "anakart"))),
        "minimal": Node("minimal", "Minimum donanımla tepki devam ediyor mu?",
            "Depolama ve çevre birimlerini ayırın; tek RAM ve dahili grafikle deneyin.",
            (_option("evet", "Evet", "post_sonuc"), _option("hayir", "Hayır", "cevre_sonuc"))),
        "anakart": Node("anakart", "Güç hattı ve düğme bağlantısı ölçüldü mü?",
            "ATX/dizüstü güç girişini ve düğme hattını ölçün; kısa devre uygulamayın.",
            (_option("normal", "Hatlar normal", "anakart_sonuc"),
             _option("anormal", "Hatlardan biri anormal", "guc_hatti_sonuc"))),
        "post_sonuc": Node("post_sonuc", "", "", conclusion=
            "Cihaz güç alıyor; POST/görüntü yok playbook'u ile devam edin."),
        "cevre_sonuc": Node("cevre_sonuc", "", "", conclusion=
            "Ayrılan çevre birimlerinden biri güç hattını düşürüyor; parçaları tek tek ekleyin."),
        "anakart_sonuc": Node("anakart_sonuc", "", "", conclusion=
            "Anakart üzeri güç yönetimi arızası olası; şema ve akım ölçümüyle kart seviyesinde inceleyin."),
        "guc_hatti_sonuc": Node("guc_hatti_sonuc", "", "", conclusion=
            "Giriş/güç düğmesi hattındaki anormalliği giderip testi baştan tekrarlayın."),
    }),
    "goruntu-yok": Playbook("goruntu-yok", "Görüntü yok / POST sorunu",
        "Güç alan fakat görüntü vermeyen cihaz", "monitor", {
        "monitor": Node("monitor", "Monitör, kablo ve doğru giriş bilinen sağlam mı?",
            "Önce harici görüntü zincirini başka cihazla doğrulayın.",
            (_option("evet", "Evet", "post"), _option("hayir", "Hayır", "monitor_sonuc"))),
        "monitor_sonuc": Node("monitor_sonuc", "", "", conclusion=
            "Harici görüntü zinciri sorunu; monitör/kablo/giriş düzeltildikten sonra yeniden test edin."),
        "post": Node("post", "POST LED veya bip kodu belirli bir bileşeni gösteriyor mu?",
            "Kodun anakart üreticisi belgesindeki karşılığını kullanın.",
            (_option("ram", "RAM", "ram"), _option("gpu", "GPU", "gpu"),
             _option("yok", "Kod yok / belirsiz", "cmos"))),
        "ram": Node("ram", "Tek ve bilinen sağlam RAM ile açılıyor mu?", "Slotları tek tek deneyin.",
            (_option("evet", "Evet", "ram_sonuc"), _option("hayir", "Hayır", "cmos"))),
        "gpu": Node("gpu", "Dahili veya bilinen sağlam GPU ile görüntü var mı?", "Gücü kapatıp GPU yolunu değiştirin.",
            (_option("evet", "Evet", "gpu_sonuc"), _option("hayir", "Hayır", "cmos"))),
        "cmos": Node("cmos", "CMOS sıfırlama ve minimum donanım testi sonucu?",
            "Üretici prosedürünü izleyin; güç kablosu bağlıyken jumper kullanmayın.",
            (_option("acildi", "Açıldı", "bios_sonuc"), _option("acilmadi", "Açılmadı", "kart_sonuc"))),
        "ram_sonuc": Node("ram_sonuc", "", "", conclusion="RAM modülü/slot eşleşmesi arızalı; modülleri ayrı ayrı doğrulayın."),
        "gpu_sonuc": Node("gpu_sonuc", "", "", conclusion="GPU veya GPU güç yolu arızalı; kart ve PSU hattını ayrı doğrulayın."),
        "bios_sonuc": Node("bios_sonuc", "", "", conclusion="BIOS/ayar kaynaklı POST sorunu; kararlı ayarlarla stres testi yapın."),
        "kart_sonuc": Node("kart_sonuc", "", "", conclusion="CPU/anakart/PSU üçlüsü için çapraz parça veya kart seviyesi ölçüm gerekli."),
    }),
    "asiri-isinma": Playbook("asiri-isinma", "Aşırı ısınma / kapanma",
        "Yük altında ısınan, yavaşlayan veya kapanan cihaz", "olcum", {
        "olcum": Node("olcum", "Boşta ve yükte sıcaklıklar ölçüldü mü?", "Sensör adını, sıcaklığı ve yükü kaydedin.",
            (_option("yuksek", "Evet, sıcaklık yüksek", "hava"),
             _option("normal", "Sıcaklık normal", "guc_sonuc"))),
        "hava": Node("hava", "Fanlar ve hava kanalları temiz/çalışır durumda mı?", "Cihaz kapalıyken fiziksel kontrol yapın.",
            (_option("hayir", "Hayır", "temizlik_sonuc"), _option("evet", "Evet", "temas"))),
        "temas": Node("temas", "Soğutucu teması ve termal malzeme uygun mu?", "Montaj basıncını ve ped kalınlıklarını doğrulayın.",
            (_option("hayir", "Hayır", "temas_sonuc"), _option("evet", "Evet", "yuk_sonuc"))),
        "temizlik_sonuc": Node("temizlik_sonuc", "", "", conclusion="Fan/hava yolu bakımını yapıp aynı yük testiyle yeniden ölçün."),
        "temas_sonuc": Node("temas_sonuc", "", "", conclusion="Soğutucu teması veya termal malzemeyi düzeltip sıcaklıkları yeniden ölçün."),
        "yuk_sonuc": Node("yuk_sonuc", "", "", conclusion="Soğutma fiziksel olarak sağlamsa güç limiti, voltaj ve arka plan yükünü inceleyin."),
        "guc_sonuc": Node("guc_sonuc", "", "", conclusion="Kapanma sıcaklık kaynaklı görünmüyor; güç ve olay günlüğü incelemesine geçin."),
    }),
}


class DiagnosticEngine:
    def __init__(self, cases: CaseStore, playbooks: dict[str, Playbook] | None = None) -> None:
        self.cases = cases
        self.playbooks = playbooks or PLAYBOOKS

    def list_playbooks(self) -> list[dict[str, str]]:
        return [{"id": p.id, "baslik": p.title, "aciklama": p.description}
                for p in self.playbooks.values()]

    def start(self, case_id: int, playbook_id: str) -> dict:
        playbook = self._playbook(playbook_id)
        try:
            session = self.cases.start_diagnostic(int(case_id), playbook.id, playbook.first_node)
            self.cases.add_note(session.case_id, f"Teşhis playbook'u başlatıldı: {playbook.title}", "deneme")
        except (CaseError, ValueError) as exc:
            raise DiagnosticError(str(exc)) from exc
        return self._response(session.id)

    def answer(self, session_id: int, option_id: str) -> dict:
        session = self.cases.get_diagnostic(int(session_id))
        if session is None:
            raise DiagnosticError(f"#{session_id} numaralı teşhis oturumu yok.")
        if session.status != "aktif":
            raise DiagnosticError("Bu teşhis oturumu tamamlanmış.")
        playbook = self._playbook(session.playbook)
        node = playbook.nodes.get(session.current_node)
        if node is None:
            raise DiagnosticError("Teşhis düğümü bulunamadı.")
        option = next((item for item in node.options if item.id == option_id), None)
        if option is None:
            raise DiagnosticError("Bu adım için geçersiz yanıt.")
        next_node = playbook.nodes[option.next_node]
        self.cases.add_note(session.case_id,
                            f"Teşhis · {node.prompt} → {option.label}", "deneme")
        if next_node.conclusion:
            self.cases.update_diagnostic(session.id, current_node=next_node.id,
                                         status="tamamlandi", summary=next_node.conclusion)
            self.cases.add_note(session.case_id, f"Teşhis sonucu: {next_node.conclusion}", "sonuc")
        else:
            self.cases.update_diagnostic(session.id, current_node=next_node.id)
        return self._response(session.id)

    def _playbook(self, playbook_id: str) -> Playbook:
        playbook = self.playbooks.get((playbook_id or "").strip())
        if playbook is None:
            raise DiagnosticError("Teşhis playbook'u bulunamadı.")
        return playbook

    def _response(self, session_id: int) -> dict:
        session = self.cases.get_diagnostic(session_id)
        if session is None:
            raise DiagnosticError("Teşhis oturumu bulunamadı.")
        playbook = self._playbook(session.playbook)
        node = playbook.nodes[session.current_node]
        return {
            "oturum_no": session.id, "vaka_no": session.case_id,
            "playbook": playbook.id, "baslik": playbook.title,
            "durum": session.status, "sonuc": session.summary,
            "adim": None if session.status == "tamamlandi" else {
                "id": node.id, "soru": node.prompt, "yonerge": node.guidance,
                "secenekler": [{"id": item.id, "etiket": item.label}
                                for item in node.options],
            },
        }
