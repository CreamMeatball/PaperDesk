"""Everything that differs per operating system lives here.

macOS is the supported target today. Windows/Linux classes exist so adding them later means filling in one class,
not hunting through the codebase.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from . import APP_ID, APP_NAME
from .config import environment_language, language_name
from .infrastructure.secrets import FileSecretStore, KeychainSecretStore
from .ports.secrets import SecretStore


class Platform(ABC):
    name: str = ""
    supported: bool = False

    @abstractmethod
    def data_dir(self) -> Path: ...

    @abstractmethod
    def secret_store(self, data_dir: Path) -> SecretStore: ...

    def window_options(self) -> dict:
        """Extra pywebview create_window() options (translucency etc.)."""
        return {}

    def extra_bin_dirs(self) -> tuple[str, ...]:
        return ()

    def preferred_language(self) -> str:
        """Default answer/translation language on first run (the user can change it in settings)."""
        return environment_language() or "English"


class MacPlatform(Platform):
    name = "macos"
    supported = True

    def data_dir(self) -> Path:
        return Path.home() / "Library" / "Application Support" / APP_NAME

    def secret_store(self, data_dir: Path) -> SecretStore:
        return KeychainSecretStore(APP_ID) if shutil.which("security") else FileSecretStore(data_dir / "secrets.json")

    def window_options(self) -> dict:
        return {"vibrancy": True, "background_color": "#2c2c2e"}

    def extra_bin_dirs(self) -> tuple[str, ...]:
        return ("/opt/homebrew/bin", "/usr/local/bin")

    def preferred_language(self) -> str:
        # The language chosen in System Settings. Terminal's LANG often differs, and GUI launches may have none.
        for code in self.apple_languages():
            name = language_name(code)
            if name:
                return name
        return super().preferred_language()

    @staticmethod
    def apple_languages() -> list[str]:
        try:
            done = subprocess.run(["defaults", "read", "-g", "AppleLanguages"], capture_output=True, text=True, timeout=5)
        except (OSError, subprocess.TimeoutExpired):
            return []
        return re.findall(r'"?([A-Za-z]{2,3}(?:-[A-Za-z0-9]+)*)"?\s*[,)\n]', done.stdout) if done.returncode == 0 else []


class WindowsPlatform(Platform):
    """Not supported yet. TODO: Credential Manager secret store, Mica backdrop, WebView2 runtime check."""

    name = "windows"

    def data_dir(self) -> Path:
        return Path(os.environ.get("APPDATA") or Path.home() / "AppData" / "Roaming") / APP_NAME

    def secret_store(self, data_dir: Path) -> SecretStore:
        return FileSecretStore(data_dir / "secrets.json")


class LinuxPlatform(Platform):
    """Development and CI only (browser shell)."""

    name = "linux"

    def data_dir(self) -> Path:
        return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / APP_ID

    def secret_store(self, data_dir: Path) -> SecretStore:
        return FileSecretStore(data_dir / "secrets.json")


def current_platform() -> Platform:
    if sys.platform == "darwin":
        return MacPlatform()
    if sys.platform.startswith("win"):
        return WindowsPlatform()
    return LinuxPlatform()

