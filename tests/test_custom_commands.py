import json

import pytest

from jarvis.core.custom_commands import CustomCommandStore


def test_custom_command_is_persistent_and_turkish_case_insensitive(tmp_path):
    path = tmp_path / "commands.json"
    store = CustomCommandStore(path)
    store.teach("Bakım Modu", "Sistem durumunu göster.")

    assert CustomCommandStore(path).resolve("bakım modu") == "Sistem durumunu göster."
    assert json.loads(path.read_text(encoding="utf-8"))[0]["phrase"] == "Bakım Modu"


def test_custom_command_update_and_delete():
    store = CustomCommandStore()
    store.teach("kontrol", "CPU kullanımını göster.")
    store.teach("Kontrol", "RAM kullanımını göster.")
    assert len(store.all()) == 1
    assert store.resolve("KONTROL") == "RAM kullanımını göster."
    assert store.delete("kontrol") is True
    assert store.resolve("kontrol") is None


@pytest.mark.parametrize("phrase, expansion", [("x", "geçerli"), ("geçerli", "x"),
                                                  ("aynı", "aynı")])
def test_invalid_custom_commands_are_rejected(phrase, expansion):
    with pytest.raises(ValueError):
        CustomCommandStore().teach(phrase, expansion)
