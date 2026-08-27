import pytest

from jarvis.diagnostics.engine import DiagnosticEngine, DiagnosticError
from jarvis.memory.cases import CaseStore
from jarvis.security.permissions import RiskLevel
from jarvis.tools.base import ToolRegistry
from jarvis.tools.diagnostic_tools import register_diagnostic_tools


@pytest.fixture
def setup():
    store = CaseStore(":memory:")
    case = store.open_case("Deniz", "Masaüstü PC", "güç gelmiyor")
    yield store, case, DiagnosticEngine(store)
    store.close()


def test_builtin_playbooks_are_structured_and_reachable(setup):
    _, _, engine = setup
    listed = engine.list_playbooks()
    assert {p["id"] for p in listed} >= {"guc-yok", "goruntu-yok", "asiri-isinma"}
    for playbook in engine.playbooks.values():
        assert playbook.first_node in playbook.nodes
        for node in playbook.nodes.values():
            for option in node.options:
                assert option.next_node in playbook.nodes


def test_guided_session_branches_and_records_a_conclusion(setup):
    store, case, engine = setup
    step = engine.start(case.id, "guc-yok")
    assert step["durum"] == "aktif" and "adaptör" in step["adim"]["soru"]
    done = engine.answer(step["oturum_no"], "hayir")
    assert done["durum"] == "tamamlandi"
    assert "enerji" in done["sonuc"].lower()
    notes = store.notes_for(case.id)
    assert [note.kind for note in notes] == ["deneme", "deneme", "sonuc"]
    assert done["sonuc"] in notes[-1].text


def test_multi_step_path_persists_current_node(setup):
    store, case, engine = setup
    started = engine.start(case.id, "goruntu-yok")
    second = engine.answer(started["oturum_no"], "evet")
    assert second["adim"]["id"] == "post"
    persisted = store.get_diagnostic(started["oturum_no"])
    assert persisted and persisted.current_node == "post" and persisted.case_id == case.id


def test_session_requires_an_existing_case(setup):
    _, _, engine = setup
    with pytest.raises(DiagnosticError, match="vaka yok"):
        engine.start(999, "guc-yok")


def test_unknown_playbook_and_option_are_rejected(setup):
    _, case, engine = setup
    with pytest.raises(DiagnosticError, match="bulunamadı"):
        engine.start(case.id, "uydurma")
    started = engine.start(case.id, "guc-yok")
    with pytest.raises(DiagnosticError, match="geçersiz yanıt"):
        engine.answer(started["oturum_no"], "uydurma")


def test_completed_session_cannot_be_changed(setup):
    _, case, engine = setup
    started = engine.start(case.id, "guc-yok")
    engine.answer(started["oturum_no"], "hayir")
    with pytest.raises(DiagnosticError, match="tamamlanmış"):
        engine.answer(started["oturum_no"], "evet")


def test_agent_tools_expose_read_and_write_risks(setup):
    store, case, engine = setup
    registry = register_diagnostic_tools(ToolRegistry(), engine)
    assert registry.get("teshis_playbooklari").risk is RiskLevel.LOW
    assert registry.get("teshis_baslat").risk is RiskLevel.MEDIUM
    started = registry.get("teshis_baslat").func(vaka_no=case.id, playbook="guc-yok")
    assert started["durum"] == "aktif"
    answered = registry.get("teshis_yanitla").func(
        oturum_no=started["oturum_no"], secenek="hayir")
    assert answered["durum"] == "tamamlandi"
