import subprocess

from jarvis.core.intent_router import Intent, IntentDecision
from jarvis.core.tool_router import ToolRouter
from jarvis.tools.base import ToolRegistry
from jarvis.tools.git_tools import register_git_tools, git_diff, git_log, git_remote, git_status


def _repo(tmp_path):
    p = tmp_path / "repo"
    p.mkdir()
    subprocess.run(["git", "init", "-q", str(p)], check=True)
    subprocess.run(["git", "-C", str(p), "config", "user.email", "test@example.com"], check=True)
    subprocess.run(["git", "-C", str(p), "config", "user.name", "Tester"], check=True)
    (p / "a.txt").write_text("ilk\n")
    subprocess.run(["git", "-C", str(p), "add", "a.txt"], check=True)
    subprocess.run(["git", "-C", str(p), "commit", "-qm", "ilk commit"], check=True)
    return p


def test_git_status_and_log_are_read_only(tmp_path):
    p = _repo(tmp_path)
    assert git_status(str(p))["branch"]
    assert git_log(str(p), 5)["commits"][0]["subject"] == "ilk commit"


def test_git_diff_reads_worktree(tmp_path):
    p = _repo(tmp_path)
    (p / "a.txt").write_text("ilk\nikinci\n")
    assert "+ikinci" in git_diff(str(p))["diff"]


def test_remote_credentials_are_redacted(tmp_path):
    p = _repo(tmp_path)
    subprocess.run(["git", "-C", str(p), "remote", "add", "origin",
                    "https://user:secret@example.com/x/y.git"], check=True)
    out = git_remote(str(p))["remotes"]
    assert "secret" not in out
    assert "REDACTED" in out


def test_github_intent_gets_only_dedicated_git_tools():
    reg = register_git_tools(ToolRegistry())
    selected = ToolRouter().select(reg.schemas(), IntentDecision(Intent.GITHUB, .99),
                                   "GitHub'daki son commit'e bak")
    names = {(s.get("function") or {}).get("name") for s in selected}
    assert names == {"git_status", "git_log", "git_diff", "git_remote"}
    assert "run_terminal_command" not in names
