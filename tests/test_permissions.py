"""Permission layer is the security spine — test it thoroughly."""
from jarvis.security.audit import AuditLog
from jarvis.security.permissions import PermissionManager, RiskLevel


def test_low_and_medium_auto_allow():
    pm = PermissionManager(audit=AuditLog())
    assert pm.check("read", RiskLevel.LOW, {}).allowed
    assert pm.check("write", RiskLevel.MEDIUM, {}).allowed


def test_high_requires_approval():
    approved = PermissionManager(audit=AuditLog(), approver=lambda *a: True)
    denied = PermissionManager(audit=AuditLog(), approver=lambda *a: False)
    assert approved.check("cfg", RiskLevel.HIGH, {}).allowed
    assert not denied.check("cfg", RiskLevel.HIGH, {}).allowed


def test_sound_notice_only_runs_when_approval_is_actually_required():
    notices = []
    pm = PermissionManager(
        audit=AuditLog(), approver=lambda *a: False,
        notifier=lambda: notices.append("sound"),
    )
    pm.check("read", RiskLevel.LOW, {})
    assert notices == []
    pm.check("change", RiskLevel.HIGH, {})
    assert notices == ["sound"]


def test_critical_denied_without_approval():
    pm = PermissionManager(audit=AuditLog(), approver=lambda *a: False)
    assert not pm.check("format_disk", RiskLevel.CRITICAL, {"dev": "/dev/sda"}).allowed


def test_non_interactive_denies_high_and_critical():
    pm = PermissionManager(audit=AuditLog(), non_interactive=True)
    assert not pm.check("cfg", RiskLevel.HIGH, {}).allowed
    assert not pm.check("bios_flash", RiskLevel.CRITICAL, {}).allowed
    # but low/medium still pass
    assert pm.check("read", RiskLevel.LOW, {}).allowed


def test_every_decision_is_audited():
    audit = AuditLog()
    pm = PermissionManager(audit=audit, approver=lambda *a: False)
    pm.check("read", RiskLevel.LOW, {})
    pm.check("danger", RiskLevel.CRITICAL, {})
    decisions = [e.decision for e in audit.entries]
    assert "allowed" in decisions and "denied" in decisions


# ---------------- geçici çıta ----------------
# Eller serbest sohbet için: kimse cümleyi okumadan ajan onu duyuyor. Odada
# başkaları varken yalnızca OKUYAN araçların çalışması istenebilmeli.

def test_the_bar_can_be_raised_for_one_turn():
    pm = PermissionManager(audit=AuditLog(), approver=lambda *a: False)
    with pm.yukselt(RiskLevel.LOW):
        assert not pm.check("uygulama_ac", RiskLevel.MEDIUM, {}).allowed
        assert pm.check("oku", RiskLevel.LOW, {}).allowed
    assert pm.check("uygulama_ac", RiskLevel.MEDIUM, {}).allowed


def test_the_bar_returns_even_when_the_turn_fails():
    """Yükseltilmiş bir çıtanın kalması sonraki her turu sessizce kilitlerdi."""
    pm = PermissionManager(audit=AuditLog(), approver=lambda *a: False)
    try:
        with pm.yukselt(RiskLevel.LOW):
            raise RuntimeError("tur patladı")
    except RuntimeError:
        pass
    assert pm.check("uygulama_ac", RiskLevel.MEDIUM, {}).allowed


def test_the_bar_can_only_go_up():
    """Aksi halde bu, onay gerektiren bir işlemi onaysız çalıştırmanın yolu olurdu."""
    pm = PermissionManager(audit=AuditLog(), approver=lambda *a: False)
    with pm.yukselt(RiskLevel.CRITICAL):
        assert not pm.check("format", RiskLevel.HIGH, {}).allowed
        assert pm.check("uygulama_ac", RiskLevel.MEDIUM, {}).allowed


def test_a_nested_raise_does_not_leak_outward():
    pm = PermissionManager(audit=AuditLog(), approver=lambda *a: False)
    with pm.yukselt(RiskLevel.MEDIUM):
        with pm.yukselt(RiskLevel.LOW):
            assert not pm.check("uygulama_ac", RiskLevel.MEDIUM, {}).allowed
        assert pm.check("uygulama_ac", RiskLevel.MEDIUM, {}).allowed


def test_the_panel_refuses_instead_of_waiting_on_a_terminal():
    """Panel istek iş parçacığında çalışıyor; stdin'den okumak tarayıcıyı dondururdu."""
    from jarvis.security.permissions import panel_approver
    assert panel_approver("format_disk", RiskLevel.CRITICAL, {}, "") is False
