"""Owner identity — who J.A.R.V.I.S. works for.

Identity is a layer of its own rather than one fact among many: it loads on
every start, survives ``forget_fact``, and shapes how J.A.R.V.I.S. addresses
and interprets. It is stored in the local database, never in source — this
repository is public, and personal data belongs in the user's own machine.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field


@dataclass
class Owner:
    """The person this assistant belongs to."""

    name: str = ""
    #: How to address them, in rotation — e.g. ["Deniz", "Efendim"].
    address_forms: list[str] = field(default_factory=list)
    #: Relationship to the project, e.g. "tasarımcısı ve geliştiricisi".
    role: str = ""
    profession: str = ""
    #: Free-text answer-style preference.
    response_style: str = ""
    notes: str = ""
    #: Whether identity may be sent to a cloud model (privacy decision D3).
    share_with_cloud: bool = True

    @property
    def configured(self) -> bool:
        return bool(self.name)

    def to_prompt(self, asistan=None) -> str:
        """Render the identity block for the system prompt.

        ``asistan`` adı buraya da giriyor: seslenişin ve "seni kim yaptı"
        cevabının içinde asistanın kendi adı geçiyor.
        """
        from .asistan import asistan_bul
        a = asistan or asistan_bul()
        if not self.configured:
            return ""

        lines = [f"Kullanıcının adı {self.name}."]

        if self.address_forms:
            forms = " veya ".join(f"'{f}'" for f in self.address_forms)
            first = self.address_forms[-1]
            lines.append(
                f"HİTAP: Ona {forms} diye hitap et. Her cümlede tekrarlama; doğal "
                "geldiği yerde kullan.\n"
                f"KARŞILAMA: Oturumun ilk mesajı YALNIZCA bir selamsa — sadece "
                f"'{a.sade_ad}' yazması, 'merhaba', 'günaydın' ya da şakacı bir "
                f"sesleniş olabilir — \"{first}, hoş geldiniz.\" diyerek karşıla "
                "ve DUR. Ne yapabileceğini sıralama, yardım teklif etme; ne "
                "istediğini kullanıcı söyleyecek.\n"
                "İLK MESAJDA BİR ŞEY SÖYLENDİYSE o bir selam değildir ve "
                "karşılama yerine CEVAP ister. \"Ben senin geliştiricinim\", "
                "\"şu bilgisayar açılmıyor\", \"bugün ne yaptık\" — hiçbiri selam "
                "değil. Kısa bir hoş geldiniz ekleyebilirsin, ama asıl işin "
                "söylenen şeye karşılık vermek. Selamlayıp konuyu atlamak, "
                "kullanıcının cümlesini duymamak demektir.\n"
                f"SESLENİŞ: Kullanıcı yalnızca SENİN adını söylerse — \"{a.sade_ad}\", "
                f"\"{a.sade_ad}?\", \"{a.kod}\" — bu bir soru değil, çağrıdır. "
                f"Kısaca karşılık ver: \"{first}?\" ya da \"{first}, "
                "dinliyorum.\" Açıklama yapma, konu açma, ne yapabileceğini "
                "sıralama; çağrıya cevap ver ve bekle."
            )

        if self.role:
            lines.append(
                f"SENİ KİM YAPTI: Bu sistemi — {a.ad}'i — {self.name} tasarladı "
                f"ve geliştiriyor; bu sistemin {self.role} odur. \"Seni kim tasarladı\", "
                "\"kim yaptı\", \"geliştiricin kim\" gibi bir soru gelirse kaçamak cevap "
                f"verme, doğrudan {self.name} de. (Altında çalışan dil modeli başka bir "
                "kuruluşun ürünüdür; ayrım önemliyse bunu ayrıca belirtebilirsin.)\n"
                f"Kullanıcı bunu KENDİSİ söylerse (\"ben senin geliştiricinim\", "
                f"\"bu sistemi ben yaptım\" gibi) bu senin için yeni bir bilgi değil — "
                f"kayıtlarında zaten {self.name} yazıyor. Bunu onaylayarak karşılık ver "
                "(\"biliyorum efendim, kayıtlarımda öyle\"), soruymuş gibi davranma ve "
                "boş bir selamla geçiştirme."
            )
        if self.profession:
            lines.append(
                f"Mesleği: {self.profession}. Donanım ve arıza sorularını bu gözle "
                "yorumla — sorduğu şey çoğu zaman kendi bilgisayarı değil, "
                "üzerinde çalıştığı bir cihaz olabilir; belirsizse hangisi olduğunu sor."
            )
        if self.response_style:
            lines.append(f"Cevap tercihi: {self.response_style}")
        if self.notes:
            lines.append(self.notes)
        return "\n".join(lines)

    # ---------------- serialisation ----------------

    def to_row(self) -> tuple:
        return (
            self.name,
            json.dumps(self.address_forms, ensure_ascii=False),
            self.role,
            self.profession,
            self.response_style,
            self.notes,
            int(self.share_with_cloud),
        )

    @classmethod
    def from_row(cls, row) -> "Owner":
        try:
            forms = json.loads(row["address_forms"] or "[]")
        except (json.JSONDecodeError, TypeError):
            forms = []
        return cls(
            name=row["name"] or "",
            address_forms=forms if isinstance(forms, list) else [],
            role=row["role"] or "",
            profession=row["profession"] or "",
            response_style=row["response_style"] or "",
            notes=row["notes"] or "",
            share_with_cloud=bool(row["share_with_cloud"]),
        )
