"""Where data lives, and locale-based defaults."""

from __future__ import annotations

import locale
import os
from dataclasses import dataclass
from pathlib import Path

LANGUAGES = {
    "ko": "Korean", "en": "English", "ja": "Japanese", "zh": "Chinese (Simplified)",
    "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese", "vi": "Vietnamese",
}


@dataclass(frozen=True)
class AppPaths:
    root: Path

    @classmethod
    def default(cls) -> "AppPaths":
        override = os.environ.get("PAPERDESK_HOME")
        if override:
            return cls(Path(override).expanduser())
        from .platforms import current_platform

        return cls(current_platform().data_dir())

    @property
    def database(self) -> Path:
        return self.root / "library.sqlite3"

    @property
    def blobs(self) -> Path:
        return self.root / "files"

    @property
    def settings_file(self) -> Path:
        return self.root / "settings.json"

    @property
    def webview_storage(self) -> Path:
        return self.root / "webview"

    def ensure(self) -> "AppPaths":
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.blobs.mkdir(exist_ok=True)
        return self


def system_language() -> str:
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        if value and value not in ("C", "POSIX") and not value.startswith("C."):
            return LANGUAGES.get(value[:2].lower(), "English")
    code = (locale.getlocale()[0] or "en")[:2].lower()
    return LANGUAGES.get(code, "English")

