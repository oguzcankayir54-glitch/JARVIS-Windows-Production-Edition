import time

import pytest

from jarvis.agenda.notifier import ReminderService, WindowsNotifier
from jarvis.agenda.store import AgendaError, AgendaStore, parse_datetime
from jarvis.memory.cases import CaseStore
from jarvis.tools.agenda_tools import register_agenda_tools
from jarvis.tools.base import ToolRegistry


def test_create_list_complete_and_persist(tmp_path):
    path = tmp_path / "memory.db"
    store = AgendaStore(path)
    item = store.create("Parçayı teslim et", "teslim", "2030-01-02 14:30",
                        "2030-01-02 13:30", "Ara", None)
    assert store.list()[0].id == item.id
    assert store.set_status(item.id, "tamamlandi").status == "tamamlandi"
    store.close()
    assert AgendaStore(path).list("tamamlandi")[0].title == "Parçayı teslim et"


def test_validation_and_case_link():
    cases = CaseStore()
    agenda = AgendaStore(cases=cases)
    with pytest.raises(AgendaError):
        agenda.create("", "gorev", "2030-01-01")
    with pytest.raises(AgendaError):
        agenda.create("x", "yanlis", "2030-01-01")
    with pytest.raises(AgendaError):
        agenda.create("x", "gorev", "2030-01-01", case_id=99)


def test_reminder_and_case_promise_are_sent_once():
    now = time.time()
    cases = CaseStore()
    case = cases.open_case("Ali", "Laptop", "Açılmıyor", promised_ts=now + 30)
    agenda = AgendaStore(cases=cases)
    item = agenda.create("Ara", "gorev", now + 10, now - 1)
    class Notify:
        available = True
        calls = []
        def notify(self, title, body):
            self.calls.append((title, body)); return True
    notifier = Notify()
    service = ReminderService(agenda, cases, notifier, case_lookahead=60)
    first = service.run_once(now)
    assert {x["kind"] for x in first} == {"agenda", "case"}
    assert agenda.get(item.id).notified_ts == now
    assert case.id in [x["id"] for x in first]
    assert service.run_once(now) == []


def test_failed_agenda_notification_is_retried():
    now = time.time()
    agenda = AgendaStore()
    item = agenda.create("Ara", "gorev", now, now - 1)
    class Fail:
        def notify(self, *_): return False
    service = ReminderService(agenda, notifier=Fail())
    assert service.run_once(now)[0]["notified"] is False
    assert service.run_once(now)[0]["id"] == item.id


def test_tools_and_router_shape():
    registry = register_agenda_tools(ToolRegistry(), AgendaStore())
    assert {x.name for x in registry.all()} == {"ajanda_ekle", "ajanda_listele", "ajanda_durum"}


def test_parse_datetime_and_windows_notifier_non_windows():
    assert parse_datetime("2030-01-01T12:00:00+03:00") > 0
    if not WindowsNotifier.available:
        assert WindowsNotifier().notify("a", "b") is False
