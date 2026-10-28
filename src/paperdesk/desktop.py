"""How the UI is shown. The server and web UI do not know which shell is used."""

from __future__ import annotations

import importlib.util
import webbrowser
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar

from . import APP_NAME
from .platforms import Platform
from .services.updates import UpdateService


class DesktopShell(ABC):
    name: ClassVar[str]
    blocks: ClassVar[bool]  # True: run() returns when the window closes, so the app can quit

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool: ...

    @abstractmethod
    def run(self, url: str) -> None: ...


class NativeWindowShell(DesktopShell):
    """pywebview: WKWebView on macOS (and Edge WebView2 on Windows later), with the platform's translucency."""

    name = "native"
    blocks = True

    def __init__(self, platform: Platform, storage: Path, updates: UpdateService | None = None) -> None:
        self.platform = platform
        self.storage = storage
        self.updates = updates

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("webview") is not None

    def run(self, url: str) -> None:
        import webview  # optional dependency, imported only when a window is requested

        updater = None
        if self.platform.name == "macos" and self.updates is not None:
            from .infrastructure.macos_updates import SparkleUpdates
            updater = SparkleUpdates()
            self.updates.attach(updater)

        self.storage.mkdir(parents=True, exist_ok=True)
        webview.create_window(
            APP_NAME,
            url + ("&" if "?" in url else "?") + "shell=native",
            width=1360,
            height=880,
            min_size=(960, 620),
            text_select=True,  # pywebview disables selection by default; readers need it
            **self.platform.window_options(),
        )
        webview.start(func=updater.start if updater else None, private_mode=False, storage_path=str(self.storage))


class BrowserShell(DesktopShell):
    """Development fallback: opens the default browser and keeps serving until Ctrl+C."""

    name = "browser"
    blocks = False

    @classmethod
    def is_available(cls) -> bool:
        return True

    def run(self, url: str) -> None:
        webbrowser.open(url)


def choose_shell(preference: str, platform: Platform, storage: Path, updates: UpdateService | None = None) -> DesktopShell:
    if preference in ("auto", "native") and NativeWindowShell.is_available():
        return NativeWindowShell(platform, storage, updates)
    if preference == "native":
        raise RuntimeError("네이티브 창에 필요한 pywebview가 설치되어 있지 않아요.")
    return BrowserShell()
