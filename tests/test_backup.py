from __future__ import annotations

import json
import sqlite3
import zipfile

import pytest

from jarvis.maintenance.backup import (BackupError, MANIFEST, create_backup,
                                       restore_backup, verify_backup)


def _database(path, value="merhaba"):
    connection = sqlite3.connect(path)
    connection.execute("CREATE TABLE note (value TEXT)")
    connection.execute("INSERT INTO note VALUES (?)", (value,))
    connection.commit()
    return connection


def test_backup_snapshots_live_sqlite_and_restores_files(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    live = _database(data / "memory.sqlite3")
    (data / "custom-commands.json").write_text('[{"ad":"deneme"}]', encoding="utf-8")
    archive = create_backup(data, tmp_path / "yedek.zip")
    live.close()

    manifest = verify_backup(archive)
    assert {item["path"] for item in manifest["files"]} == {
        "memory.sqlite3", "custom-commands.json"}

    restored = tmp_path / "restored"
    assert restore_backup(archive, restored) == 2
    db = sqlite3.connect(restored / "memory.sqlite3")
    assert db.execute("SELECT value FROM note").fetchone()[0] == "merhaba"
    db.close()
    assert "deneme" in (restored / "custom-commands.json").read_text(encoding="utf-8")


def test_backup_detects_tampering(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "note.txt").write_text("ilk", encoding="utf-8")
    archive = create_backup(data, tmp_path / "yedek.zip")
    with pytest.warns(UserWarning, match="Duplicate name"):
        with zipfile.ZipFile(archive, "a") as output:
            output.writestr("note.txt", "değişti")
    with pytest.raises(BackupError):
        verify_backup(archive)


def test_restore_rejects_path_traversal(tmp_path):
    archive = tmp_path / "evil.zip"
    body = b"bad"
    manifest = {"format": 1, "created_at": 0, "files": [
        {"path": "../outside.txt", "size": len(body),
         "sha256": __import__("hashlib").sha256(body).hexdigest()}]}
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(MANIFEST, json.dumps(manifest))
        output.writestr("../outside.txt", body)
    with pytest.raises(BackupError):
        restore_backup(archive, tmp_path / "data")
    assert not (tmp_path / "outside.txt").exists()


def test_output_inside_data_directory_is_not_backed_up_recursively(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    (data / "note.txt").write_text("x", encoding="utf-8")
    output = create_backup(data, data / "backups" / "one.zip")
    assert output.is_file()
    names = {entry["path"] for entry in verify_backup(output)["files"]}
    assert "backups/one.zip" not in names
