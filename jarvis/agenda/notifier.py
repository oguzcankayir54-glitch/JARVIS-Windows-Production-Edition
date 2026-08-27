from __future__ import annotations

import base64
import os
import platform
import subprocess
import time


class NullNotifier:
    available = False
    def notify(self, title: str, body: str) -> bool:
        return False


_TOAST_SCRIPT = r"""
$t=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:JARVIS_TOAST_TITLE))
$b=[Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:JARVIS_TOAST_BODY))
$xml=New-Object Windows.Data.Xml.Dom.XmlDocument
$safeT=[Security.SecurityElement]::Escape($t);$safeB=[Security.SecurityElement]::Escape($b)
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$safeT</text><text>$safeB</text></binding></visual></toast>")
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('J.A.R.V.I.S.').Show([Windows.UI.Notifications.ToastNotification]::new($xml))
"""


class WindowsNotifier:
    available = platform.system().lower() == "windows"

    def notify(self, title: str, body: str) -> bool:
        if not self.available:
            return False
        env = os.environ.copy()
        env["JARVIS_TOAST_TITLE"] = base64.b64encode(title.encode()).decode("ascii")
        env["JARVIS_TOAST_BODY"] = base64.b64encode(body.encode()).decode("ascii")
        try:
            subprocess.Popen(["powershell.exe", "-NoProfile", "-NonInteractive",
                              "-WindowStyle", "Hidden", "-Command", _TOAST_SCRIPT],
                             env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            return True
        except OSError:
            return False


class ReminderService:
    def __init__(self, agenda, cases=None, notifier=None, case_lookahead: float = 3600) -> None:
        self.agenda, self.cases = agenda, cases
        self.notifier = notifier or WindowsNotifier()
        self.case_lookahead = max(0, case_lookahead)

    def run_once(self, now: float | None = None) -> list[dict]:
        now = time.time() if now is None else now
        sent = []
        for item in self.agenda.due_reminders(now):
            ok = self.notifier.notify("J.A.R.V.I.S. Ajanda", item.title)
            if ok:
                self.agenda.mark_notified(item.id, now)
            sent.append({"kind": "agenda", "id": item.id, "title": item.title, "notified": ok})
        if self.cases is not None:
            for case in self.cases.promised_cases(now + self.case_lookahead):
                key = f"case:{case.id}:{case.promised_ts}"
                if not self.agenda.claim_notification(key, now):
                    continue
                title = f"Vaka #{case.id} teslim zamanı yaklaşıyor"
                ok = self.notifier.notify("J.A.R.V.I.S. Servis", title)
                sent.append({"kind": "case", "id": case.id, "title": title, "notified": ok})
        return sent
