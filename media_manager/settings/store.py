import fcntl
import json
import os
import tempfile
from pathlib import Path
from typing import Any

from media_manager.config import runtime_config_path


class RuntimeSettingsStore:
    """Small atomic JSON store for the UI-managed configuration overlay."""

    def __init__(self, path: Path = runtime_config_path) -> None:
        self.path = path
        self.lock_path = path.with_suffix(f"{path.suffix}.lock")

    def read(self) -> dict[str, Any]:
        if not self.path.exists():
            return {}
        with self.path.open(encoding="utf-8") as settings_file:
            payload = json.load(settings_file)
        if not isinstance(payload, dict):
            msg = "The UI settings file must contain a JSON object"
            raise TypeError(msg)
        return payload

    def write(self, payload: dict[str, Any]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.lock_path.open("a+", encoding="utf-8") as lock_file:
            self.lock_path.chmod(0o600)
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
            temporary_path: Path | None = None
            try:
                file_descriptor, raw_path = tempfile.mkstemp(
                    prefix=f".{self.path.name}.",
                    suffix=".tmp",
                    dir=self.path.parent,
                )
                temporary_path = Path(raw_path)
                with os.fdopen(file_descriptor, "w", encoding="utf-8") as output:
                    os.fchmod(output.fileno(), 0o600)
                    json.dump(payload, output, indent=2, sort_keys=True)
                    output.write("\n")
                    output.flush()
                    os.fsync(output.fileno())
                temporary_path.replace(self.path)
                self.path.chmod(0o600)
            finally:
                if temporary_path is not None and temporary_path.exists():
                    temporary_path.unlink()
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
