"""Which addresses J.A.R.V.I.S. may reach, and which it must never.

This is the security core of the internet layer, and the reason it exists is
concrete: once the model can fetch a URL, **the instruction to fetch it can
come from a web page rather than from the owner.** A page that says "for more
detail see http://localhost:8765/ask?text=..." is asking J.A.R.V.I.S. to turn
its own control panel — which runs terminal commands — against the machine it
runs on. The same trick reaches a router at 192.168.1.1, a cloud metadata
service at 169.254.169.254, or another machine on the owner's Tailscale
network.

So the rule is an allowlist of *shapes*, not a blocklist of strings:

* only ``http`` and ``https`` — no ``file://``, ``ftp://``, UNC paths
* the resolved address must be a public one, checked per hop
* redirects are followed by hand so every hop is checked, not just the first

The last point matters most. A URL that resolves to a public address on the
first request can redirect to ``127.0.0.1``, and a check that only looks at
what the owner typed would wave it through.
"""
from __future__ import annotations

import ipaddress
import socket
import urllib.parse

#: Buradan sonrasi tartisilmaz: yalnizca bu iki sema.
IZINLI_SEMALAR = ("http", "https")

#: Python surumune gore is_private bu araligi kapsamiyor (3.13'e kadar).
#: Onemli, cunku Tailscale tam da burayi kullaniyor: 100.64.0.0/10 uzerinden
#: sahibinin diger makinelerine ulasilabilir.
_EK_OZEL_AGLAR = (
    ipaddress.ip_network("100.64.0.0/10"),      # CGNAT / Tailscale
    ipaddress.ip_network("192.0.0.0/24"),       # IETF protokol atamalari
    ipaddress.ip_network("198.18.0.0/15"),      # kiyaslama
    ipaddress.ip_network("::ffff:0:0/96"),      # IPv4-mapped IPv6
)


class AdresReddedildi(ValueError):
    """Raised with a Turkish message the tool layer can hand straight back."""


def ozel_adres_mi(ham: str) -> bool:
    """Whether this literal IP is anything other than a public internet host."""
    try:
        ip = ipaddress.ip_address(ham)
    except ValueError:
        return False
    if (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved
            or ip.is_multicast or ip.is_unspecified):
        return True
    # IPv4-mapped IPv6 (::ffff:127.0.0.1) kendi basina "private" gorunmuyor;
    # icindeki IPv4'e bakmak gerekiyor.
    eslenen = getattr(ip, "ipv4_mapped", None)
    if eslenen is not None and ozel_adres_mi(str(eslenen)):
        return True
    return any(ip in ag for ag in _EK_OZEL_AGLAR if ip.version == ag.version)


def _cozumle(makine: str) -> list[str]:
    """Every address this hostname resolves to. Empty when it resolves to none."""
    try:
        bilgiler = socket.getaddrinfo(makine, None, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError, OSError):
        return []
    return [b[4][0] for b in bilgiler]


def url_denetle(url: str, coz: bool = True) -> str:
    """Return the URL if it is safe to request, else raise :class:`AdresReddedildi`.

    ``coz=False`` skips DNS — useful when the caller only needs the shape
    checked (opening a link in the owner's own browser, where the browser does
    its own resolution and the owner sees the address).
    """
    url = (url or "").strip()
    if not url:
        raise AdresReddedildi("Boş adres.")

    parca = urllib.parse.urlsplit(url)
    if parca.scheme.lower() not in IZINLI_SEMALAR:
        raise AdresReddedildi(
            f"Yalnızca http ve https adresleri açılabilir "
            f"('{parca.scheme or 'şemasız'}' reddedildi)."
        )
    makine = parca.hostname
    if not makine:
        raise AdresReddedildi("Adreste sunucu adı yok.")

    # Adin kendisi bir IP ise dogrudan bak; degilse cozumleyip her adrese bak.
    if ozel_adres_mi(makine):
        raise AdresReddedildi(
            f"'{makine}' yerel/özel bir adres. J.A.R.V.I.S. kendi ağına veya "
            "kendi paneline istek atmaz."
        )
    if makine.lower() in ("localhost", "localhost.localdomain", "ip6-localhost"):
        raise AdresReddedildi("'localhost' açılamaz — bu makinenin kendisi.")

    if coz:
        adresler = _cozumle(makine)
        if not adresler:
            raise AdresReddedildi(f"'{makine}' çözümlenemedi.")
        for adres in adresler:
            if ozel_adres_mi(adres):
                raise AdresReddedildi(
                    f"'{makine}' yerel bir adrese ({adres}) çözümleniyor; "
                    "istek gönderilmedi."
                )
    return url


def alan_adi(url: str) -> str:
    """Host without the ``www.``, for showing where a result came from."""
    ad = (urllib.parse.urlsplit(url).hostname or "").lower()
    return ad[4:] if ad.startswith("www.") else ad
