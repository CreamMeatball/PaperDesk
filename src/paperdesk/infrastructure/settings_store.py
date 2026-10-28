from __future__ import annotations

import json
import os
from pathlib import Path

from ..ports.settings import Settings, SettingsStore


class JsonSettingsStore(SettingsStore):
    def __init__(self, path: Path, defaults: Settings) -> None:
        self.path = path
        self.defaults = defaults

    def load(self) -> Settings:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return Settings.from_dict({}, defaults=self.defaults)
        return Settings.from_dict(data if isinstance(data, dict) else {}, defaults=self.defaults)

    def save(self, settings: Settings) -> None:
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(settings.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temporary, self.path)


class MemorySettingsStore(SettingsStore):
    def __init__(self, settings: Settings | None = None) -> None:
        self._settings = settings or Settings()

    def load(self) -> Settings:
        return Settings.from_dict(self._settings.to_dict())

    def save(self, settings: Settings) -> None:
        self._settings = Settings.from_dict(settings.to_dict())

