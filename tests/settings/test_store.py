# ruff: noqa: S101

import json
import stat
from pathlib import Path

import pytest

from media_manager.settings.store import RuntimeSettingsStore


def test_runtime_settings_store_writes_atomically_with_private_permissions(
    tmp_path: Path,
) -> None:
    settings_path = tmp_path / "ui-settings.json"
    store = RuntimeSettingsStore(settings_path)

    store.write({"indexers": {"prowlarr": {"api_key": "private"}}})

    assert store.read() == {
        "indexers": {"prowlarr": {"api_key": "private"}}
    }
    assert stat.S_IMODE(settings_path.stat().st_mode) == 0o600
    assert not list(tmp_path.glob("*.tmp"))


def test_runtime_settings_store_rejects_non_object_json(tmp_path: Path) -> None:
    settings_path = tmp_path / "ui-settings.json"
    settings_path.write_text(json.dumps(["not", "an", "object"]), encoding="utf-8")
    store = RuntimeSettingsStore(settings_path)

    with pytest.raises(TypeError, match="JSON object"):
        store.read()
