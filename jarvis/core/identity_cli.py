"""``jarvis-tanit`` — set, view or clear the owner identity.

The identity lives in the local database, not in this repository: the code is
public, the person using it is not. Run this once and J.A.R.V.I.S. knows who it
works for from then on.
"""
from __future__ import annotations

import argparse
import sys

from ..config import load_config
from ..memory.store import MemoryStore
from .owner import Owner


def _print_owner(owner: Owner) -> None:
    if not owner.configured:
        print("Kimlik ayarlanmamış. Ayarlamak için:  jarvis-tanit --kur")
        return
    print("J.A.R.V.I.S. sizi şöyle tanıyor:\n")
    print(f"  Ad          : {owner.name}")
    print(f"  Hitap       : {', '.join(owner.address_forms) or '—'}")
    print(f"  Rol         : {owner.role or '—'}")
    print(f"  Meslek      : {owner.profession or '—'}")
    print(f"  Cevap tarzı : {owner.response_style or '—'}")
    if owner.notes:
        print(f"  Not         : {owner.notes}")
    print(f"  Buluta gider: {'evet' if owner.share_with_cloud else 'hayır (yalnızca yerel)'}")


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    try:
        value = input(f"{prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise SystemExit(1)
    return value or default


def _interactive(current: Owner) -> Owner:
    print("J.A.R.V.I.S. kimlik kurulumu — boş bırakırsanız köşeli parantezdeki değer kalır.\n")
    name = _ask("Adınız ve soyadınız", current.name)
    forms_raw = _ask("Size nasıl hitap etsin? (virgülle ayırın)",
                     ", ".join(current.address_forms))
    role = _ask("Bu sistemdeki rolünüz", current.role or "tasarımcısı ve geliştiricisi")
    profession = _ask("Mesleğiniz", current.profession or "bilgisayar teknik servisi")
    style = _ask("Cevap tercihi", current.response_style
                 or "Teknik ve ayrıntılı; basit sorularda kısa ve net.")
    cloud = _ask("Kimlik bulut modele gönderilsin mi? (e/h)",
                 "e" if current.share_with_cloud else "h")

    return Owner(
        name=name,
        address_forms=[f.strip() for f in forms_raw.split(",") if f.strip()],
        role=role,
        profession=profession,
        response_style=style,
        notes=current.notes,
        share_with_cloud=cloud.lower().startswith("e"),
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="jarvis-tanit",
        description="J.A.R.V.I.S.'in sizi tanıması için kimlik bilgilerini ayarlayın.",
    )
    parser.add_argument("--kur", action="store_true", help="Soru-cevap ile kimliği ayarla")
    parser.add_argument("--sil", action="store_true", help="Kimliği tamamen sil")
    parser.add_argument("--ad", help="Ad soyad")
    parser.add_argument("--hitap", help="Hitap şekilleri, virgülle ayrılmış")
    parser.add_argument("--rol", help="Bu sistemdeki rolünüz")
    parser.add_argument("--meslek", help="Mesleğiniz")
    parser.add_argument("--tarz", help="Cevap tercihi")
    parser.add_argument("--not", dest="notlar", help="Serbest not")
    parser.add_argument("--bulut", choices=["evet", "hayir"],
                        help="Kimlik bulut modele gönderilsin mi")
    args = parser.parse_args(argv)

    cfg = load_config()
    store = MemoryStore(cfg.memory_db_path)
    current = store.get_owner()

    if args.sil:
        store.clear_owner()
        print("Kimlik silindi.")
        return 0

    if args.kur:
        store.set_owner(_interactive(current))
        print()
        _print_owner(store.get_owner())
        return 0

    # Flag-driven update: only the fields given are changed.
    fields = {
        "name": args.ad, "role": args.rol, "profession": args.meslek,
        "response_style": args.tarz, "notes": args.notlar,
    }
    changed = {k: v for k, v in fields.items() if v is not None}
    if args.hitap is not None:
        changed["address_forms"] = [f.strip() for f in args.hitap.split(",") if f.strip()]
    if args.bulut is not None:
        changed["share_with_cloud"] = args.bulut == "evet"

    if not changed:
        _print_owner(current)
        return 0

    updated = Owner(**{**current.__dict__, **changed})
    store.set_owner(updated)
    _print_owner(updated)
    return 0


if __name__ == "__main__":
    sys.exit(main())
