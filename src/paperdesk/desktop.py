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


class MacWindowTheme:
    """window.pywebview.api for the page. macOS draws the translucent backdrop behind the page and follows the
    system appearance, so a light theme on a dark system sat on a black backdrop; the page reports its theme."""

    def theme(self, choice: str) -> None:
        from AppKit import NSAppearance, NSAppearanceNameAqua, NSAppearanceNameDarkAqua, NSApplication
        from PyObjCTools.AppHelper import callAfter

        name = {"light": NSAppearanceNameAqua, "dark": NSAppearanceNameDarkAqua}.get(choice)  # "system": follow macOS
        callAfter(lambda: NSApplication.sharedApplication().setAppearance_(NSAppearance.appearanceNamed_(name) if name else None))


class NativeWindowShell(DesktopShell):
    """pywebview: WKWebView on macOS (and Edge WebView2 on Windows later), with the platform's translucency."""

    name = "native"
    blocks = True

    def __init__(self, platform: Platform, storage: Path) -> None:
        self.platform = platform
        self.storage = storage

    @classmethod
    def is_available(cls) -> bool:
        return importlib.util.find_spec("webview") is not None

    def run(self, url: str) -> None:
        import webview  # optional dependency, imported only when a window is requested
        webview.settings['ALLOW_DOWNLOADS'] = True

        self.storage.mkdir(parents=True, exist_ok=True)
        window = webview.create_window(
            APP_NAME,
            url + ("&" if "?" in url else "?") + "shell=native",
            width=1360,
            height=880,
            min_size=(960, 620),
            frameless=False,
            resizable=True,
            text_select=True,  # pywebview disables selection by default; readers need it
            js_api=MacWindowTheme() if self.platform.name == "macos" else None,
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

        webview.start(func=started, menu=menu, private_mode=False, storage_path=str(self.storage), icon=icon)


class BrowserShell(DesktopShell):
    """Development fallback: opens the default browser and keeps serving until Ctrl+C."""

    name = "browser"
    blocks = False

    @classmethod
    def is_available(cls) -> bool:
        return True

    def run(self, url: str) -> None:
        webbrowser.open(url)


def choose_shell(preference: str, platform: Platform, storage: Path) -> DesktopShell:
    if preference in ("auto", "native") and NativeWindowShell.is_available():
        return NativeWindowShell(platform, storage)
    if preference == "native":
        raise RuntimeError("네이티브 창에 필요한 pywebview가 설치되어 있지 않아요.")
    return BrowserShell()
