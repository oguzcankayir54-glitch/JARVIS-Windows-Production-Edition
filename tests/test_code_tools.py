from types import SimpleNamespace

import pytest

from jarvis.tools import code_tools
from jarvis.tools.base import ToolRegistry
from jarvis.tools.code_tools import (
    code_search,
    edit_file,
    inspect_project,
    register_code_tools,
    run_project_tests,
)


def test_project_inspection_measures_stack_and_ignores_generated_secrets(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    (tmp_path / "app.py").write_text("print('ok')", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_app.py").write_text("def test_ok(): pass", encoding="utf-8")
    (tmp_path / "node_modules").mkdir()
    (tmp_path / "node_modules" / "fake.py").write_text("secret", encoding="utf-8")
    (tmp_path / ".env").write_text("TOKEN=secret", encoding="utf-8")

    result = inspect_project(str(tmp_path))

    assert result["file_count"] == 3
    assert result["languages"] == {"Python": 2}
    assert result["manifests"] == ["pyproject.toml"]
    assert result["test_files"] == ["tests/test_app.py"]


def test_code_search_returns_real_paths_lines_and_literal_matches(tmp_path):
    (tmp_path / "a.py").write_text("x = 'Needle'\nprint(x)\n", encoding="utf-8")
    (tmp_path / "b.js").write_text("const needle = 2;\n", encoding="utf-8")

    result = code_search("needle", str(tmp_path))

    assert result["match_count"] == 2
    assert {(item["path"], item["line"]) for item in result["matches"]} == {
        ("a.py", 1), ("b.js", 1),
    }


def test_exact_edit_changes_one_fragment_and_returns_hash_evidence(tmp_path):
    target = tmp_path / "app.py"
    target.write_text("def answer():\n    return 1\n", encoding="utf-8")

    result = edit_file(str(target), "return 1", "return 2")

    assert target.read_text(encoding="utf-8").endswith("return 2\n")
    assert result["edited"] is True
    assert result["before_sha256"] != result["after_sha256"]
    assert str(target) in result["user_message"]


@pytest.mark.parametrize("content, expected", [
    ("nothing here", "bulunan: 0"),
    ("same\nsame\n", "bulunan: 2"),
])
def test_exact_edit_refuses_zero_or_ambiguous_matches(tmp_path, content, expected):
    target = tmp_path / "app.py"
    target.write_text(content, encoding="utf-8")

    with pytest.raises(ValueError, match=expected):
        edit_file(str(target), "same", "changed")


def test_project_test_runner_preserves_real_exit_code(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    test_file = tmp_path / "tests"
    test_file.mkdir()
    (test_file / "test_x.py").write_text("def test_x(): pass", encoding="utf-8")
    seen = {}

    def run(command, **kwargs):
        seen["command"] = command
        seen["kwargs"] = kwargs
        return SimpleNamespace(returncode=0, stdout="1 passed", stderr="")

    monkeypatch.setattr(code_tools.subprocess, "run", run)

    result = run_project_tests(
        str(tmp_path), framework="pytest", target="tests/test_x.py", timeout=30,
    )

    assert result["passed"] is True and result["exit_code"] == 0
    assert seen["command"][-2:] == ["-q", "tests/test_x.py"]
    assert seen["kwargs"]["shell"] is False
    assert seen["kwargs"]["cwd"] == tmp_path


def test_pytest_prefers_the_projects_own_virtual_environment(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    project_python = tmp_path / ".venv" / "bin" / "python"
    project_python.parent.mkdir(parents=True)
    project_python.write_text("", encoding="utf-8")

    framework, command = code_tools._test_command(tmp_path, "pytest", "")

    assert framework == "pytest"
    assert command[:4] == [str(project_python), "-m", "pytest", "-q"]


def test_project_test_target_cannot_escape_project(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    outside = tmp_path.parent / "outside_test.py"
    outside.write_text("", encoding="utf-8")

    with pytest.raises(PermissionError, match="dışına"):
        run_project_tests(str(tmp_path), framework="pytest", target="../outside_test.py")


def test_failing_test_result_fails_tool_verification(tmp_path, monkeypatch):
    (tmp_path / "pyproject.toml").write_text("[project]\nname='x'", encoding="utf-8")
    monkeypatch.setattr(
        code_tools.subprocess,
        "run",
        lambda *_a, **_k: SimpleNamespace(
            returncode=1, stdout="1 failed", stderr="assert 1 == 2",
        ),
    )
    registry = register_code_tools(ToolRegistry())

    result = registry.get("run_project_tests").run(path=str(tmp_path), framework="pytest")

    assert result.ok is False
    assert result.verified is False
    assert result.data["exit_code"] == 1
