"""Permission Layer — risk classification and approval gating.

Every tool declares a :class:`RiskLevel`. The :class:`PermissionManager`
decides whether a call may run:

* ``LOW``      — read-only / harmless      → allowed automatically
* ``MEDIUM``   — reversible local change   → allowed automatically (logged)
* ``HIGH``     — system-level change        → requires explicit user approval
* ``CRITICAL`` — destructive / irreversible → requires two-step explicit approval

The LLM can never change a tool's risk level, and any request — including
one that originates from a document or web page — is gated the same way.
This is the reason the tool layer exists (see docs/REQUIREMENTS_ANALYSIS.md
§2.4 on prompt-injection defence).
"""
from __future__ import annotations

import enum
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .audit import AuditEntry, AuditLog


class RiskLevel(enum.IntEnum):
    LOW = 0
    MEDIUM = 1
    HIGH = 2
    CRITICAL = 3

    @property
    def label(self) -> str:
        return self.name


@dataclass
class Decision:
    allowed: bool
    reason: str


# An approver receives (tool_name, risk, args, prompt_text) and returns True
# to allow. Defaults to a terminal prompt; tests inject their own.
Approver = Callable[[str, RiskLevel, dict[str, Any], str], bool]


def _deny_approver(tool: str, risk: RiskLevel, args: dict[str, Any], prompt: str) -> bool:
    """Non-interactive default: deny anything that needs approval."""
    return False


def terminal_approver(tool: str, risk: RiskLevel, args: dict[str, Any], prompt: str) -> bool:
    """Interactive approver used by the CLI.

    CRITICAL actions require the user to type a confirmation phrase, not just
    'y' — voice/loose confirmation is intentionally not enough (decision D4).
    """
    print(f"\n[İZİN GEREKLİ · {risk.label}] {tool}({args})")
    print(f"  {prompt}")
    if risk >= RiskLevel.CRITICAL:
        phrase = f"ONAYLA {tool}"
        got = input(f"  Bu KRİTİK işlemi onaylamak için aynen yazın → '{phrase}': ").strip()
        return got == phrase
    return input("  Onaylıyor musunuz? [e/H]: ").strip().lower() in {"e", "evet", "y", "yes"}


#: Onaysız geçebilen en yüksek risk. Bunun ÜSTÜ onay ister.
VARSAYILAN_TABAN = RiskLevel.MEDIUM


def panel_approver(tool: str, risk: RiskLevel, args: dict[str, Any], prompt: str) -> bool:
    """Approver for the web panel: refuse, and say where approval can happen.

    The panel had inherited :func:`terminal_approver`, which reads from stdin.
    In a request thread that means the browser waits forever on a question
    printed into a terminal nobody is watching — the request never returns and
    the panel looks frozen.

    Denying is the honest answer until the panel has an approval dialog of its
    own: the refusal reaches the user as text, with the reason and the way to
    do it deliberately.
    """
    print(f"[panel] onay gerektiren işlem reddedildi: {tool} ({risk.label}) {args}",
          flush=True)
    return False


class PermissionManager:
    def __init__(
        self,
        audit: AuditLog | None = None,
        approver: Optional[Approver] = None,
        non_interactive: bool = False,
        taban: RiskLevel = VARSAYILAN_TABAN,
    ) -> None:
        self.audit = audit or AuditLog()
        if approver is not None:
            self.approver = approver
        else:
            self.approver = _deny_approver if non_interactive else terminal_approver
        self.taban = taban

    def yukselt(self, taban: RiskLevel) -> "_TabanKapsami":
        """Temporarily require approval for more than usual.

        Hands-free speech is why this exists. When the panel is listening
        continuously, nobody reads the sentence before it reaches the agent —
        a misheard word becomes an action with no one having confirmed the
        words. So for the duration of a spoken turn the bar goes up: anything
        beyond read-only needs approval.

        The bar can only ever be RAISED. Passing something lower is ignored
        rather than obeyed, so no caller — and nothing a caller was told by a
        web page or a document — can use this to widen what runs unattended.
        """
        return _TabanKapsami(self, taban)

    def check(self, tool: str, risk: RiskLevel, args: dict[str, Any], prompt: str = "") -> Decision:
        """Return an allow/deny :class:`Decision` and write an audit entry."""
        if risk <= self.taban:
            self.audit.record(AuditEntry(tool=tool, risk=risk.label, decision="allowed", args=args))
            return Decision(True, "auto-allowed")

        prompt = prompt or f"'{tool}' {risk.label} seviyesinde bir işlem."
        approved = bool(self.approver(tool, risk, args, prompt))
        decision = "approved" if approved else "denied"
        self.audit.record(AuditEntry(tool=tool, risk=risk.label, decision=decision, args=args, detail=prompt))
        if approved:
            return Decision(True, "user-approved")
        return Decision(False, "Kullanıcı onayı verilmedi.")


class _TabanKapsami:
    """Bir tur boyunca onay çıtasını yükselten bağlam yöneticisi.

    Çıkışta eski değere dönüyor — bir hata da olsa. Yükseltilmiş bir çıtanın
    ortalıkta kalması, sonraki her turu sessizce kilitlerdi.
    """

    def __init__(self, yonetici: PermissionManager, taban: RiskLevel) -> None:
        self._yonetici = yonetici
        self._istenen = taban
        self._onceki = yonetici.taban

    def __enter__(self) -> PermissionManager:
        self._onceki = self._yonetici.taban
        # Yalnızca YÜKSELTME. Daha düşük bir taban istemek, onay gerektiren
        # bir işlemi onaysız çalıştırmanın yolu olurdu.
        self._yonetici.taban = min(self._onceki, self._istenen)
        return self._yonetici

    def __exit__(self, *_hata) -> None:
        self._yonetici.taban = self._onceki
