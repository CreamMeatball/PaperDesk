"""How the UI is shown. The server and web UI do not know which shell is used."""

from __future__ import annotations

import importlib.util
import webbrowser
from abc import ABC, abstractmethod
from pathlib import Path
from typing import ClassVar
from urllib.parse import urljoin

from . import APP_NAME
from .platforms import Platform
from .services.app_state import PreferenceService


class DesktopShell(ABC):
    name: ClassVar[str]
    blocks: ClassVar[bool]  # True: run() returns when the window closes, so the app can quit

    @classmethod
    @abstractmethod
    def is_available(cls) -> bool: ...

    @abstractmethod
    def run(self, url: str) -> None: ...


def _macos_settings_shortcut() -> None:
    from AppKit import NSApplication, NSEventModifierFlagCommand

    menu = NSApplication.sharedApplication().mainMenu().itemAtIndex_(0).submenu()
    for item in menu.itemArray():
        if item.title() == "Settings…":
            item.setKeyEquivalent_(",")
            item.setKeyEquivalentModifierMask_(NSEventModifierFlagCommand)
            break


MAC_ICON = Path(__file__).resolve().parents[2] / "packaging" / "macos" / "Paperdesk.icns"  # present in source installs


def _macos_app_name() -> None:
    # The process is Python's, so the Dock and the app menu would say "Python". This must run before the window
    # starts: pywebview creates the application and its menus from this dictionary when it loads.
    from Foundation import NSBundle

    bundle = NSBundle.mainBundle()
    (bundle.localizedInfoDictionary() or bundle.infoDictionary())["CFBundleName"] = APP_NAME


def _macos_appearance(theme: str) -> None:
    # macOS draws the title bar and the translucent backdrop behind the page, and they follow the app's appearance:
    # left to the system, the light theme on a dark system sat in a black frame. Main thread only.
    from AppKit import NSAppearance, NSAppearanceNameAqua, NSAppearanceNameDarkAqua, NSApplication

    name = {"light": NSAppearanceNameAqua, "dark": NSAppearanceNameDarkAqua}.get(theme)  # "system": follow macOS
    NSApplication.sharedApplication().setAppearance_(NSAppearance.appearanceNamed_(name) if name else None)


def _macos_follow_theme(preferences: PreferenceService) -> None:
    # The theme is saved by the page; pywebview's JS bridge cannot run under the app's Content-Security-Policy.
    # Called once the app is running: AppKit resets an appearance set while it is still launching.
    from PyObjCTools.AppHelper import callAfter

    callAfter(_macos_appearance, preferences.all()["theme"])
    preferences.watch(lambda values: "theme" in values and callAfter(_macos_appearance, values["theme"]))


class NativeWindowShell(DesktopShell):
    """pywebview: WKWebView on macOS (and Edge WebView2 on Windows later), with the platform's translucency."""

    name = "native"
    blocks = True

    def __init__(self, platform: Platform, storage: Path, preferences: PreferenceService | None = None) -> None:
        self.platform = platform
        self.storage = storage
        self.preferences = preferences
        self.window = None

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("webview") is not None

    def run(self, url: str) -> None:
        import webview  # optional dependency, imported only when a window is requested
        webview.settings['ALLOW_DOWNLOADS'] = True

        self.storage.mkdir(parents=True, exist_ok=True)
        window = self.window = webview.create_window(
            APP_NAME,
            url + ("&" if "?" in url else "?") + "shell=native",
            width=1360,
            height=880,
            min_size=(960, 620),
            frameless=False,
            resizable=True,
            text_select=True,  # pywebview disables selection by default; readers need it
            **self.platform.window_options(),
        )
        menu, icon = [], None
        if self.platform.name == "macos":
            from webview.menu import Menu, MenuAction
            menu = [Menu("__app__", [MenuAction("Settings…", lambda: window.load_url(urljoin(url, "/settings?shell=native")))])]
            _macos_app_name()
            icon = str(MAC_ICON) if MAC_ICON.is_file() else None

        def started():
            if self.platform.name == "macos":
                from PyObjCTools.AppHelper import callAfter
                callAfter(_macos_settings_shortcut)
                if self.preferences is not None:
                    _macos_follow_theme(self.preferences)

        webview.start(func=started, menu=menu, private_mode=False, storage_path=str(self.storage), icon=icon)

    def close(self) -> None:
        """Close the window from any thread; run() then returns."""
        if self.window is not None:
            self.window.destroy()


class BrowserShell(DesktopShell):
    """Development fallback: opens the default browser and keeps serving until Ctrl+C."""

    name = "browser"
    blocks = False

    @classmethod
    def is_available(cls) -> bool:
        return True

    def run(self, url: str) -> None:
        webbrowser.open(url)


def choose_shell(preference: str, platform: Platform, storage: Path, preferences: PreferenceService | None = None) -> DesktopShell:
    if preference in ("auto", "native") and NativeWindowShell.is_available():
        return NativeWindowShell(platform, storage, preferences)
    if preference == "native":
        raise RuntimeError("네이티브 창에 필요한 pywebview가 설치되어 있지 않아요.")
    return BrowserShell()
