"""Terminal command tool — allowlisted, never through a shell.

This is the most dangerous capability J.A.R.V.I.S. has, so it is built to fail
closed at every step:

1. **No shell.** Commands are parsed with :func:`shlex.split` and executed as
   an argv list. Nothing is ever handed to ``/bin/sh``, so ``ls; rm -rf /``
   cannot chain — and shell metacharacters are rejected up front anyway.
2. **Allowlist.** A command whose binary is not in :data:`READ_ONLY`,
   :data:`MUTATING` or :data:`DESTRUCTIVE` is refused outright. Unknown
   binaries never run, which is the main defence against a "run this" request
   smuggled in through a document, a web page, or a model hallucination.
3. **Argument screening.** Specific argument shapes that turn a benign binary
   destructive (``find -delete``, ``rm -rf /``, writing to a raw disk) are
   refused even though the binary itself is allowed.
4. **Per-command risk.** Reading is MEDIUM (auto-allowed, audited), changing
   the system is HIGH (approval), and destructive operations are CRITICAL
   (typed confirmation).
"""
from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

from ..security.permissions import RiskLevel
from .base import Param, Tool, ToolRegistry

#: Reading state: safe to run without asking, but still audited.
READ_ONLY = {
    "ls", "cat", "head", "tail", "pwd", "df", "du", "free", "uname", "uptime",
    "whoami", "id", "date", "hostname", "env", "which", "stat", "file", "wc",
    "grep", "find", "ps", "lsblk", "lscpu", "lsusb", "lspci", "lsmod",
    "sensors", "nvidia-smi", "smartctl", "dmidecode", "journalctl", "dmesg",
    "ip", "ss", "ping", "dig", "nslookup", "echo", "printenv", "top", "df",
}

#: Changing the system: requires explicit approval.
MUTATING = {
    "systemctl", "service", "mount", "umount", "apt", "apt-get", "dnf", "yum",
    "pacman", "pip", "pip3", "npm", "kill", "pkill", "chmod", "chown", "ln",
    "mv", "cp", "mkdir", "rmdir", "rm", "touch", "modprobe", "sysctl", "ufw",
    "iptables", "crontab", "docker", "tar", "unzip", "git",
}

#: Irreversible / hardware-level: requires typed confirmation.
DESTRUCTIVE = {
    "mkfs", "mkfs.ext4", "mkfs.xfs", "mkfs.btrfs", "mkfs.vfat", "fdisk",
    "parted", "gdisk", "sgdisk", "dd", "shred", "wipefs", "blkdiscard",
    "flashrom", "efibootmgr", "cryptsetup", "badblocks", "mkswap",
}

# --------------------------------------------------------------- Windows
# Yukaridaki liste Unix icin. Windows'a tasinirken hicbiri bulunmuyor ve
# terminal araci sessizce kullanilamaz hale geliyordu: her komut "izin
# listesinde degil" ile reddediliyor, teknisyenin en cok isine yarayan
# yetenek de kayboluyor. Ayni siniflandirma, Windows'un kendi komutlariyla.
#
# Kabuk YOK burada da: komutlar argv listesi olarak calisiyor, ve
# powershell/cmd bilerek listede degil — ikisi de bu katmanin butun
# denetimlerini atlatmanin yolu olurdu.

#: Durum okuyan Windows komutlari.
WIN_READ_ONLY = {
    "systeminfo", "hostname", "whoami", "ver", "vol", "date", "time",
    "tasklist", "driverquery", "ipconfig", "ping", "tracert", "nslookup",
    "netstat", "arp", "route", "getmac", "wmic", "dir", "type", "where",
    "chcp", "set", "fsutil", "powercfg", "nvidia-smi", "smartctl",
    "dxdiag", "msinfo32", "query", "openfiles", "gpresult", "wevtutil",
}

#: Sistemi degistiren Windows komutlari — onay ister.
WIN_MUTATING = {
    "sfc", "dism", "chkdsk", "net", "netsh", "sc", "reg", "schtasks",
    "taskkill", "bcdedit", "icacls", "attrib", "copy", "xcopy", "robocopy",
    "move", "mkdir", "md", "rmdir", "rd", "del", "erase", "ren", "rename",
    "pip", "pip3", "npm", "winget", "choco", "git", "tar",
}

#: Geri donusu olmayan Windows komutlari — yazili onay ister.
WIN_DESTRUCTIVE = {
    "format", "diskpart", "cipher", "bootrec", "bcdboot", "recimg",
    "wbadmin", "clean", "convert", "label",
}

#: Rejected before parsing — these only make sense with a shell.
_METACHARS = (";", "|", "&", ">", "<", "`", "$(", "${", "\n", "\r")

#: Raw block devices must never be a command target.
_RAW_DEVICE_PREFIXES = ("/dev/sd", "/dev/nvme", "/dev/hd", "/dev/vd", "/dev/mmcblk", "/dev/disk")


@dataclass
class CommandVerdict:
    allowed: bool
    risk: RiskLevel
    reason: str


def _targets_raw_device(tokens: list[str]) -> bool:
    """True if any argument names a raw block device.

    The device path is not always the whole token: ``dd`` takes ``of=/dev/sda``,
    so each token is also split on ``=`` and ``:`` before matching.
    """
    for token in tokens:
        candidates = [token]
        for sep in ("=", ":", ","):
            candidates.extend(part for part in token.split(sep) if part)
        if any(c.startswith(_RAW_DEVICE_PREFIXES) for c in candidates):
            return True
    return False


def _is_root_target(token: str) -> bool:
    """True for arguments that mean 'everything', like / or /*."""
    return token.strip() in {"/", "/*", "//", "~", "~/", "/home", "/etc", "/usr", "/var", "/boot"}


def classify_command(command: str) -> CommandVerdict:
    """Decide whether ``command`` may run, and at what risk level."""
    text = command.strip()
    if not text:
        return CommandVerdict(False, RiskLevel.CRITICAL, "Boş komut.")

    for meta in _METACHARS:
        if meta in text:
            return CommandVerdict(
                False, RiskLevel.CRITICAL,
                f"Kabuk operatörü içeren komut reddedildi ({meta!r}). "
                "Komutlar zincirlenemez; tek bir komut gönderin.",
            )

    try:
        tokens = shlex.split(text)
    except ValueError as exc:
        return CommandVerdict(False, RiskLevel.CRITICAL, f"Komut ayrıştırılamadı: {exc}")
    if not tokens:
        return CommandVerdict(False, RiskLevel.CRITICAL, "Boş komut.")

    binary, args = tokens[0], tokens[1:]

    if binary in {"sudo", "su", "doas", "pkexec"}:
        return CommandVerdict(
            False, RiskLevel.CRITICAL,
            "Yetki yükseltme (sudo/su) J.A.R.V.I.S. üzerinden kullanılamaz. "
            "Böyle bir işlemi kendiniz yapın.",
        )

    # --- argument screening: benign binaries with destructive arguments ---
    if binary == "rm":
        recursive = any(a.startswith("-") and "r" in a.lower() for a in args)
        paths = [a for a in args if not a.startswith("-")]
        if recursive and any(_is_root_target(p) for p in paths):
            return CommandVerdict(False, RiskLevel.CRITICAL,
                                  "Kök dizini özyinelemeli silme reddedildi.")
        if not paths:
            return CommandVerdict(False, RiskLevel.CRITICAL, "Hedefsiz 'rm' reddedildi.")

    if binary == "find" and any(a in {"-delete", "-exec", "-execdir", "-ok"} for a in args):
        return CommandVerdict(False, RiskLevel.CRITICAL,
                              "'find' ile silme/komut çalıştırma reddedildi.")

    if binary == "chmod" and any(_is_root_target(a) for a in args):
        return CommandVerdict(False, RiskLevel.CRITICAL, "Kök dizinde izin değişimi reddedildi.")

    if _targets_raw_device(tokens) and binary not in {"smartctl", "lsblk", "ls", "stat", "file"}:
        return CommandVerdict(False, RiskLevel.CRITICAL,
                              "Ham disk aygıtına yazma/işlem reddedildi.")

    # --- allowlist classification ---
    # Iki liste de her zaman gecerli: WSL'de bir Windows komutu (.exe ile)
    # gercekten calisabiliyor, ve Windows'ta da bir Unix araci kurulu
    # olabiliyor. Siniflandirmayi ortama gore KISITLAMAK, calisabilen bir
    # komutu denetimsiz birakmak degil, calisan bir komutu reddetmek olurdu.
    ad = binary[:-4] if binary.endswith(".exe") else binary
    if ad in DESTRUCTIVE or ad in WIN_DESTRUCTIVE:
        return CommandVerdict(True, RiskLevel.CRITICAL, f"'{binary}' geri döndürülemez bir işlem.")
    if ad in MUTATING or ad in WIN_MUTATING:
        return CommandVerdict(True, RiskLevel.HIGH, f"'{binary}' sistemi değiştirebilir.")
    if ad in READ_ONLY or ad in WIN_READ_ONLY:
        return CommandVerdict(True, RiskLevel.MEDIUM, f"'{binary}' salt-okunur bir komut.")

    return CommandVerdict(
        False, RiskLevel.CRITICAL,
        f"'{binary}' izin listesinde değil. Güvenlik gereği bilinmeyen komutlar çalıştırılmaz.",
    )


def _risk_for_command(args: dict[str, Any]) -> RiskLevel:
    """Argument-aware risk used by the permission layer."""
    return classify_command(str(args.get("command", ""))).risk


def _precheck_command(args: dict[str, Any]) -> str | None:
    """Absolute policy gate: refused commands never reach the approver."""
    verdict = classify_command(str(args.get("command", "")))
    return None if verdict.allowed else verdict.reason


def run_terminal_command(command: str, timeout: float = 15.0) -> dict[str, Any]:
    """Run one allowlisted command without a shell and return its output."""
    verdict = classify_command(command)
    if not verdict.allowed:
        raise PermissionError(verdict.reason)

    tokens = shlex.split(command.strip())

    # ``echo`` is an executable on Unix but only a cmd.exe builtin on
    # Windows.  Implementing this harmless command directly keeps the same
    # no-shell guarantee on both platforms.
    if tokens[0].lower().removesuffix(".exe") == "echo":
        return {
            "calisti": True,
            "komut": command.strip(),
            "risk": verdict.risk.label,
            "cikis_kodu": 0,
            "stdout": " ".join(tokens[1:]),
            "stderr": "",
        }

    try:
        proc = subprocess.run(
            tokens, capture_output=True, text=True, errors="replace",
            timeout=timeout, check=False,
        )
    except FileNotFoundError:
        return {"calisti": False, "hata": f"Komut bulunamadı: {tokens[0]}"}
    except subprocess.TimeoutExpired:
        return {"calisti": False, "hata": f"Komut {timeout}s içinde bitmedi ve durduruldu."}

    def _clip(text: str, limit: int = 4000) -> str:
        text = text.strip()
        return text if len(text) <= limit else text[:limit] + f"\n… (çıktı kısaltıldı, {len(text)} karakter)"

    return {
        "calisti": True,
        "komut": command.strip(),
        "risk": verdict.risk.label,
        "cikis_kodu": proc.returncode,
        "stdout": _clip(proc.stdout),
        "stderr": _clip(proc.stderr, 1000),
    }


def register_shell_tools(registry: ToolRegistry) -> ToolRegistry:
    registry.register(Tool(
        name="run_terminal_command",
        description=(
            "İzin listesindeki tek bir terminal komutunu kabuk kullanmadan çalıştır. "
            "Komut zincirleme (; | &&) ve sudo desteklenmez."
        ),
        # MEDIUM is the floor; the classifier raises it to HIGH/CRITICAL per command.
        risk=RiskLevel.MEDIUM,
        func=run_terminal_command,
        risk_for=_risk_for_command,
        precheck=_precheck_command,
        params=[
            Param("command", "string", "Çalıştırılacak tek komut, ör. 'df -h'", required=True),
            Param("timeout", "number", "Saniye cinsinden zaman aşımı (varsayılan 15)"),
        ]))
    return registry
