"""Everything that differs per operating system lives here.

macOS is the supported target today. Windows/Linux classes exist so adding them later means filling in one class,
not hunting through the codebase.
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from . import DATA_DIR_NAME, STORAGE_ID, KEYCHAIN_SERVICE
from .config import environment_language, language_name
from .infrastructure.secrets import CredentialManagerSecretStore, FileSecretStore, KeychainSecretStore
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
        return Path.home() / "Library" / "Application Support" / DATA_DIR_NAME

    def secret_store(self, data_dir: Path) -> SecretStore:
        return KeychainSecretStore(KEYCHAIN_SERVICE)

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
    """Not supported yet. TODO: Mica backdrop, WebView2 runtime check."""

    name = "windows"

    def data_dir(self) -> Path:
        # Local, not Roaming: PDFs, caches and analysis models are large and must not sync with roaming profiles.
        return Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / DATA_DIR_NAME

    def secret_store(self, data_dir: Path) -> SecretStore:
        return CredentialManagerSecretStore(KEYCHAIN_SERVICE)

    def preferred_language(self) -> str:
        # The display languages chosen in Windows Settings. GUI launches have no LANG, and locale names look like 'Korean_Korea'.
        for code in self.ui_languages():
            name = language_name(code)
            if name:
                return name
        return super().preferred_language()

    @staticmethod
    def ui_languages() -> list[str]:
        try:
            import ctypes
            from ctypes import wintypes

            get = ctypes.WinDLL("kernel32").GetUserPreferredUILanguages
            count, size = wintypes.ULONG(), wintypes.ULONG(0)
            if not get(0x8, ctypes.byref(count), None, ctypes.byref(size)):  # MUI_LANGUAGE_NAME: 'ko-KR'
                return []
            buffer = ctypes.create_unicode_buffer(size.value)
            if not get(0x8, ctypes.byref(count), buffer, ctypes.byref(size)):
                return []
        except (OSError, AttributeError):
            return []
        return [code for code in buffer[:size.value].split("\0") if code]


class LinuxPlatform(Platform):
    """Development and CI only (browser shell)."""

    name = "linux"

    def data_dir(self) -> Path:
        return Path(os.environ.get("XDG_DATA_HOME") or Path.home() / ".local" / "share") / STORAGE_ID

    def secret_store(self, data_dir: Path) -> SecretStore:
        return FileSecretStore(data_dir / "secrets.json")


def current_platform() -> Platform:
    if sys.platform == "darwin":
        return MacPlatform()
    if sys.platform.startswith("win"):
        return WindowsPlatform()
    return LinuxPlatform()

