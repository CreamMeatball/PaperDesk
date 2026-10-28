"""Application updates. The macOS backend delegates download, verification and installation to Sparkle."""
from __future__ import annotations

from .. import __version__
from ..domain.errors import InvalidInput, ProviderUnavailable
from ..i18n import _, translate
from ..ports.updates import UpdateBackend, UpdateState


class UnavailableUpdates(UpdateBackend):
    def state(self) -> UpdateState:
        return UpdateState(False, False, message=_("앱 업데이트는 배포용 macOS 앱에서 사용할 수 있어요."))

    def check(self) -> None:
        raise ProviderUnavailable(self.state().message)

    def set_automatic_checks(self, enabled: bool) -> None:
        raise ProviderUnavailable(self.state().message)


class UpdateService:
    def __init__(self, backend: UpdateBackend | None = None) -> None:
        self._backend = backend or UnavailableUpdates()

    def attach(self, backend: UpdateBackend) -> None:
        self._backend = backend

    def view(self, language: str = "ko") -> dict:
        state = self._backend.state()
        return {"version": __version__, "available": state.available, "can_check": state.can_check,
                "automatic_checks": state.automatic_checks, "message": translate(state.message, language)}

    def check(self) -> dict:
        state = self._backend.state()
        if not state.available:
            raise ProviderUnavailable(state.message)
        if not state.can_check:
            raise InvalidInput(_("업데이트 확인이 진행 중이에요. 잠시 후 다시 시도해 주세요."))
        self._backend.check()
        # This means the native update window opened, not that this version is current.
        return {"opened": True}

    def configure(self, automatic_checks: bool) -> None:
        if not isinstance(automatic_checks, bool):
            raise InvalidInput(_("자동 업데이트 확인 설정을 확인해 주세요."))
        self._backend.set_automatic_checks(automatic_checks)
