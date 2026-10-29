"""Sparkle 2 adapter for the packaged WKWebView application.

All Cocoa/Sparkle calls execute on the Cocoa main thread. Imports are lazy so source builds and
other platforms work without Sparkle or PyObjC. An unconfigured build never checks the network.
"""
from __future__ import annotations

import base64
import logging
import threading
from concurrent.futures import Future, TimeoutError
from pathlib import Path
from urllib.parse import urlsplit

from ..domain.errors import ProviderUnavailable
from ..i18n import _
from ..ports.updates import UpdateBackend, UpdateState

log = logging.getLogger(__name__)


def valid_update_configuration(feed: str, public_key: str) -> bool:
    try:
        url = urlsplit(feed)
        return (url.scheme == "https" and bool(url.hostname) and not url.username and not url.password
                and not url.fragment and len(base64.b64decode(public_key, validate=True)) == 32)
    except (ValueError, TypeError):
        return False


class SparkleUpdates(UpdateBackend):
    def __init__(self) -> None:
        self._controller = None
        self._dispatch = None
        self._message = _("앱 업데이트를 준비하는 중이에요.")

    def start(self) -> None:
        """Called by pywebview after its main event loop has started."""
        try:
            from PyObjCTools.AppHelper import callAfter
            self._dispatch = callAfter
            self._on_main(self._initialize)
        except Exception:
            log.exception("Could not initialize the native updater")
            self._message = _("앱 업데이트를 시작하지 못했어요.")

    def _initialize(self) -> None:
        from Foundation import NSBundle, NSClassFromString
        bundle = NSBundle.mainBundle()
        if not str(bundle.bundlePath()).endswith(".app"):
            self._message = _("앱 업데이트는 배포용 macOS 앱에서 사용할 수 있어요.")
            return
        info = bundle.infoDictionary()
        if not valid_update_configuration(str(info.get("SUFeedURL", "")), str(info.get("SUPublicEDKey", ""))):
            self._message = _("이 앱에는 업데이트 배포 주소와 서명 키가 아직 설정되지 않았어요.")
            return
        framework = Path(str(bundle.bundlePath())) / "Contents" / "Frameworks" / "Sparkle.framework"
        sparkle = NSBundle.bundleWithPath_(str(framework))
        if sparkle is None or not sparkle.load():
            raise RuntimeError("Sparkle.framework could not be loaded")
        cls = NSClassFromString("SPUStandardUpdaterController")
        if cls is None:
            raise RuntimeError("SPUStandardUpdaterController was not registered")
        # Defaults (manual checks, no silent installation) are supplied by Info.plist.
        self._controller = cls.alloc().initWithStartingUpdater_updaterDelegate_userDriverDelegate_(True, None, None)
        self._message = ""

    def _on_main(self, action):
        if threading.current_thread() is threading.main_thread():
            return action()
        if self._dispatch is None:
            raise ProviderUnavailable(self._message)
        future = Future()

        def invoke():
            # Do not execute a timed-out action later (e.g. opening an unexpected update window).
            if not future.set_running_or_notify_cancel():
                return
            try:
                future.set_result(action())
            except Exception as error:
                future.set_exception(error)

        self._dispatch(invoke)
        try:
            return future.result(timeout=10)
        except TimeoutError as error:
            future.cancel()
            raise ProviderUnavailable(_("업데이트 창이 응답하지 않아요. 잠시 후 다시 시도해 주세요.")) from error

    def state(self) -> UpdateState:
        if self._controller is None:
            return UpdateState(False, False, message=self._message)
        try:
            return self._on_main(lambda: UpdateState(True, bool(self._controller.updater().canCheckForUpdates()),
                                                      bool(self._controller.updater().automaticallyChecksForUpdates())))
        except Exception:
            return UpdateState(False, False, message=_("업데이트 창이 응답하지 않아요. 잠시 후 다시 시도해 주세요."))

    def check(self) -> None:
        if self._controller is None:
            raise ProviderUnavailable(self._message)
        self._on_main(lambda: self._controller.checkForUpdates_(None))

    def set_automatic_checks(self, enabled: bool) -> None:
        if self._controller is None:
            raise ProviderUnavailable(self._message)
        self._on_main(lambda: self._controller.updater().setAutomaticallyChecksForUpdates_(enabled))
