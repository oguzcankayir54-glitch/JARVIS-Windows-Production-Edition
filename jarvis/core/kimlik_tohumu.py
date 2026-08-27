"""Boş bir kimliği açılışta dosyadan doldurmak.

Kimlik veritabanında duruyor ve orada durmaya devam ediyor. Sorun kimliğin
oraya NASIL girdiğiydi: tek yol ``jarvis-tanit --kur`` komutunu çalıştırmaktı,
o komut kurulum adımlarının arasında kayboldu, ve J.A.R.V.I.S. aylarca kimseyi
tanımadı. "Beni hâlâ tanımıyor" üç kez geri geldi.

Bir adımın hatırlanmasını beklemek tasarım değil. Artık depoda bir
``kimlik.json`` var; veritabanında kimlik YOKSA ilk açılışta oradan
dolduruluyor.

**Tohum yalnızca boşluğu doldurur.** Veritabanında bir kimlik varsa dosya
hiçbir şey yapmıyor: elle girilmiş bir bilgiyi her açılışta dosyadaki eski
değere geri döndürmek, kullanıcının yaptığı işi sessizce silmek olurdu.
"""
from __future__ import annotations

import json
from pathlib import Path

from .owner import Owner

#: Depo kökündeki tohum dosyası. Kullanıcının kendi kopyası veri klasöründe
#: aranıyor ve depodakinden önce geliyor — kendi makinesindeki bilgi, depoya
#: yazılmış olandan daha doğrudur.
DOSYA_ADI = "kimlik.json"


def tohum_yollari(data_dir: Path | str = "~/.jarvis") -> list[Path]:
    return [
        Path(data_dir).expanduser() / DOSYA_ADI,
        Path(__file__).resolve().parents[2] / DOSYA_ADI,
    ]


def dosyadan_oku(yol: Path) -> Owner | None:
    """Read one seed file. A broken file must not stop J.A.R.V.I.S. starting."""
    try:
        ham = json.loads(yol.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError):
        return None
    if not isinstance(ham, dict):
        return None

    ad = str(ham.get("name", "")).strip()
    if not ad:
        return None

    hitaplar = ham.get("address_forms") or []
    if isinstance(hitaplar, str):
        hitaplar = [hitaplar]

    return Owner(
        name=ad,
        address_forms=[str(h).strip() for h in hitaplar if str(h).strip()],
        role=str(ham.get("role", "")).strip(),
        profession=str(ham.get("profession", "")).strip(),
        response_style=str(ham.get("response_style", "")).strip(),
        notes=str(ham.get("notes", "")).strip(),
        share_with_cloud=bool(ham.get("share_with_cloud", True)),
    )


def tohumu_bul(data_dir: Path | str = "~/.jarvis") -> Owner | None:
    for yol in tohum_yollari(data_dir):
        if not yol.is_file():
            continue
        sahip = dosyadan_oku(yol)
        if sahip is not None:
            return sahip
    return None


def kimligi_tohumla(store, data_dir: Path | str = "~/.jarvis") -> Owner | None:
    """Seed the owner if — and only if — none is set. Returns what was written.

    Called at start-up. Returning ``None`` covers both "already had one" and
    "no seed file": neither is a problem, and neither should print anything.
    """
    try:
        mevcut = store.get_owner()
    except Exception:      # noqa: BLE001 - kimlik yüzünden açılış engellenmez
        return None
    if mevcut.configured:
        return None

    sahip = tohumu_bul(data_dir)
    if sahip is None:
        return None
    try:
        store.set_owner(sahip)
    except Exception:      # noqa: BLE001
        return None
    return sahip
