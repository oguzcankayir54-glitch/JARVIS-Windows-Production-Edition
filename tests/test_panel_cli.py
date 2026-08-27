"""Panel launcher — the phone address it prints under WSL2.

Under WSL2 the panel's own address is on a virtual network the phone can
never reach; the phone has to go to the Windows host. WSL can ask Windows
for that address through interop, but interop returns whatever Windows
printed — a warning line, an error, several addresses — so the answer is
validated rather than trusted. An unvalidated string would be pasted
straight into the URL shown to the user.
"""
import subprocess

from jarvis.web import cli


class _Sonuc:
    def __init__(self, stdout: str) -> None:
        self.stdout = stdout


def _stub(monkeypatch, stdout: str = "", exc: Exception | None = None):
    def sahte(*args, **kwargs):
        if exc is not None:
            raise exc
        return _Sonuc(stdout)
    monkeypatch.setattr(cli.subprocess, "run", sahte)


def test_valid_address_is_returned(monkeypatch):
    _stub(monkeypatch, "192.168.2.77\n")
    assert cli._windows_lan_ip() == "192.168.2.77"


def test_surrounding_whitespace_is_trimmed(monkeypatch):
    _stub(monkeypatch, "  192.168.1.34  \r\n")
    assert cli._windows_lan_ip() == "192.168.1.34"


def test_first_line_wins_when_windows_prints_several(monkeypatch):
    _stub(monkeypatch, "192.168.2.77\n10.0.0.5\n")
    assert cli._windows_lan_ip() == "192.168.2.77"


def test_a_warning_line_is_not_mistaken_for_an_address(monkeypatch):
    """This is the case that would put junk in the URL."""
    _stub(monkeypatch, "WARNING: Get-NetIPAddress could not be found\n")
    assert cli._windows_lan_ip() == ""


def test_out_of_range_octet_is_rejected(monkeypatch):
    _stub(monkeypatch, "192.168.1.999\n")
    assert cli._windows_lan_ip() == ""


def test_short_address_is_rejected(monkeypatch):
    _stub(monkeypatch, "192.168.1\n")
    assert cli._windows_lan_ip() == ""


def test_empty_output_is_rejected(monkeypatch):
    _stub(monkeypatch, "   \n")
    assert cli._windows_lan_ip() == ""


def test_missing_interop_degrades_quietly(monkeypatch):
    """No powershell.exe on PATH means not WSL, or interop disabled."""
    _stub(monkeypatch, exc=FileNotFoundError("powershell.exe"))
    assert cli._windows_lan_ip() == ""


def test_a_slow_powershell_does_not_hold_up_startup(monkeypatch):
    _stub(monkeypatch, exc=subprocess.TimeoutExpired("powershell.exe", 6))
    assert cli._windows_lan_ip() == ""


def test_lookup_is_bounded_by_a_timeout(monkeypatch):
    """Startup must not hang on interop; the call always carries a deadline."""
    gorulen = {}

    def sahte(*args, **kwargs):
        gorulen.update(kwargs)
        return _Sonuc("192.168.1.5")

    monkeypatch.setattr(cli.subprocess, "run", sahte)
    cli._windows_lan_ip()
    assert gorulen.get("timeout") and gorulen["timeout"] <= 10
