"""File tools: normal use, secret protection, and system-path escalation."""
import os
from pathlib import Path

import pytest

from jarvis.security.audit import AuditLog
from jarvis.security.permissions import PermissionManager, RiskLevel
from jarvis.tools.base import ToolRegistry
from jarvis.tools.file_tools import read_file, register_file_tools, write_file
from jarvis.tools.manager import ToolManager


def test_write_then_read(tmp_path):
    target = tmp_path / "not.txt"
    write_file(str(target), "merhaba dünya")
    assert read_file(str(target))["icerik"] == "merhaba dünya"


def test_append_mode(tmp_path):
    target = tmp_path / "log.txt"
    write_file(str(target), "bir\n")
    write_file(str(target), "iki\n", append=True)
    assert read_file(str(target))["icerik"] == "bir\niki\n"


def test_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        read_file(str(tmp_path / "yok.txt"))


@pytest.mark.parametrize("name", ["id_rsa", "server.pem", ".env", "my.key", "credentials.json"])
def test_secret_files_are_refused(tmp_path, name):
    secret = tmp_path / name
    secret.write_text("gizli")
    with pytest.raises(PermissionError):
        read_file(str(secret))
    with pytest.raises(PermissionError):
        write_file(str(secret), "x")


def test_ssh_directory_is_refused(tmp_path):
    ssh = tmp_path / ".ssh"
    ssh.mkdir()
    keyfile = ssh / "anything.txt"
    keyfile.write_text("gizli")
    with pytest.raises(PermissionError):
        read_file(str(keyfile))


def test_list_directory(tmp_path):
    (tmp_path / "a.txt").write_text("a")
    (tmp_path / "sub").mkdir()
    from jarvis.tools.file_tools import list_directory
    out = list_directory(str(tmp_path))
    names = {e["ad"] for e in out["icerik"]}
    assert {"a.txt", "sub"} <= names


def _mgr(approver):
    reg = register_file_tools(ToolRegistry())
    return ToolManager(reg, PermissionManager(audit=AuditLog(), approver=approver))


def test_user_path_write_is_medium_and_auto_allowed(tmp_path):
    mgr = _mgr(lambda *a: False)   # would deny if it were asked
    res = mgr.dispatch("write_file", {"path": str(tmp_path / "x.txt"), "content": "veri"})
    assert res.ok


def test_secret_file_refused_even_when_user_approves(tmp_path):
    secret = tmp_path / "id_rsa"
    secret.write_text("PRIVATE KEY")
    asked = []

    def approver(tool, risk, args, prompt):
        asked.append(args)
        return True

    res = _mgr(approver).dispatch("read_file", {"path": str(secret)})
    assert not res.ok and "Reddedildi (politika)" in res.error
    assert asked == [], "gizli dosya onaya sunulmamalıydı"


def test_system_path_write_requires_approval():
    seen = {}

    def approver(tool, risk, args, prompt):
        seen["risk"] = risk
        return False

    root = Path(os.environ.get("SystemRoot", "C:/Windows")) if os.name == "nt" else Path("/etc")
    target = root / "jarvis-test.conf"
    res = _mgr(approver).dispatch("write_file", {"path": str(target), "content": "x"})
    assert not res.ok
    assert seen["risk"] is RiskLevel.HIGH
