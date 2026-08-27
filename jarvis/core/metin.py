"""Turkish text handling shared by everything that searches.

Folding lives here rather than beside one caller because the service log and
the knowledge base have to agree: a case found by searching "ışık yok" and a
document found by searching the same words must be folded identically, or the
two halves of memory answer the same question differently.
"""
from __future__ import annotations

#: Türkçe harfleri, insanların fiilen yazdığı biçimlerin hepsinin birbirine
#: denk düştüğü tek bir forma indirger.
#:
#: İki ayrı sorunu birden çözüyor. Birincisi noktalı/noktasız I: Python'da
#: ``"IŞIK".casefold()`` → ``"işik"`` ama ``"ışık"`` olduğu gibi kalır, yani
#: aynı kelime kendisiyle eşleşmez. İkincisi, herkesin aceleyle "goruntu yok"
#: yazması — arama bunu "görüntü yok" ile buluşturamazsa kimse kullanmaz.
TR_KATLAMA = str.maketrans({
    "ı": "i", "I": "i", "İ": "i",
    "ş": "s", "Ş": "s", "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u", "ö": "o", "Ö": "o", "ç": "c", "Ç": "c",
    "â": "a", "Â": "a", "î": "i", "Î": "i", "û": "u", "Û": "u",
})


def katla(metin: str) -> str:
    """Fold text so the ways a Turkish keyboard produces a word all agree."""
    return metin.translate(TR_KATLAMA).casefold()


#: Aramada elenecek çok kısa parçalar. "yok", "var" gibi iki-üç harfli
#: kelimeler teknik metinlerin her yerinde geçiyor; hepsini eşleştirmek
#: puanı anlamsızlaştırıyor.
EN_KISA = 3

#: Belirtiyi anlatırken herkesin kullandığı, hiçbir şey ayırt etmeyen kelimeler.
ETKISIZ = frozenset(katla(k) for k in (
    "ama", "ancak", "bir", "bu", "çok", "daha", "değil", "gibi", "hiç",
    "için", "ile", "olarak", "sonra", "şey", "ve", "veya", "yine",
))

#: Yalnızca serbest soru metinlerinde elenen kalıplar. Vaka aramasında
#: kullanılmıyor: oraya belirti girilir, soru cümlesi değil. "ElevenLabs'ı
#: nasıl bağlamıştık" sorusunda ayırt edici olan "bağlamak", "nasıl" değil.
SORU_KALIPLARI = frozenset(katla(k) for k in (
    "nasıl", "neden", "nedir", "hangi", "kaç", "acaba", "lütfen",
    "the", "and", "for", "with", "that", "this", "what", "how", "why",
))


def kelimeler(metin: str, sorular_da: bool = False) -> list[str]:
    """Query words worth matching on, folded the way Turkish needs.

    ``sorular_da`` additionally drops question words — right for a sentence
    someone typed at J.A.R.V.I.S., wrong for a symptom field where the words
    were chosen deliberately.
    """
    elenecek = ETKISIZ | SORU_KALIPLARI if sorular_da else ETKISIZ
    parcalar = "".join(c if c.isalnum() else " " for c in katla(metin)).split()
    return [p for p in parcalar if len(p) >= EN_KISA and p not in elenecek]


#: Bir metnin ağırlıklı olarak İngilizce olup olmadığını anlamak için işlev
#: sözcükleri. Konu sözcükleri değil bunlar: "motherboard" iki dilde de
#: geçebilir, ama "the" geçtiği metin İngilizcedir.
_INGILIZCE_ISARETLER = frozenset((
    "the", "and", "of", "to", "is", "are", "for", "with", "this", "that",
    "you", "from", "was", "were", "have", "has", "not", "but", "can", "will",
    "your", "which", "when", "there", "their", "would", "should", "about",
))
_TURKCE_ISARETLER = frozenset((
    "ve", "bir", "bu", "icin", "ile", "olarak", "daha", "gibi", "ama",
    "veya", "cok", "sonra", "once", "kadar", "ise", "yok", "var", "olan",
    "degil", "hangi", "nasil", "neden", "sistem", "sunu", "onu",
))

#: Kaç işlev sözcüğü görülmeden karar verilmesin. Kısa bir metinde bir "the"
#: rastlantıdır; sekiz işaret bir dil demektir.
_EN_AZ_ISARET = 8


def ingilizce_agirlikli(metin: str) -> bool:
    """Whether this text is mostly English.

    Used to decide when the model needs reminding that its *sources* being in
    English does not make its *answer* English. That drift is the single most
    common way a Turkish-only assistant slips: a fetched page or a code
    comment arrives in English and the next reply mirrors it.

    Deliberately blunt. A wrong answer here costs one extra sentence of
    instruction, not a wrong reply — so it errs toward saying "no".
    """
    if not metin:
        return False
    parcalar = "".join(c if c.isalnum() else " " for c in katla(metin)).split()
    ing = sum(1 for p in parcalar if p in _INGILIZCE_ISARETLER)
    tur = sum(1 for p in parcalar if p in _TURKCE_ISARETLER)
    if ing + tur < _EN_AZ_ISARET:
        return False
    return ing > tur * 2
