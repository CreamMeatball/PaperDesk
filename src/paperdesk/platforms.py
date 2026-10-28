"""Everything that differs per operating system lives here.

macOS is the supported target today. Windows/Linux classes exist so adding them later means filling in one class,
not hunting through the codebase.
"""

from __future__ import annotations

import os
import shutil
import sys
from abc import ABC, abstractmethod
from pathlib import Path

from . import APP_ID, APP_NAME
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

