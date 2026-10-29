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

    def ensure(self) -> "AppPaths":
        self.root.mkdir(parents=True, exist_ok=True)
        os.chmod(self.root, 0o700)
        self.blobs.mkdir(exist_ok=True)
        return self


def language_name(code: str | None) -> str | None:
    """'ko-KR', 'ko_KR.UTF-8', 'zh-Hans' -> display name used in prompts, or None if unknown."""
    if not code:
        return None
    return LANGUAGES.get(code.replace("_", "-").split("-")[0].split(".")[0].lower())


def environment_language() -> str | None:
    """POSIX locale variables, skipping the neutral C/POSIX locale."""
    for name in ("LC_ALL", "LC_MESSAGES", "LANG"):
        value = os.environ.get(name, "")
        if value and value not in ("C", "POSIX") and not value.startswith("C."):
            return language_name(value)
    return language_name(locale.getlocale()[0])


def system_language() -> str:
    from .platforms import current_platform

    return current_platform().preferred_language()

