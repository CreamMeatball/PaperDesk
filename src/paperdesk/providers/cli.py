"""Base class for providers that run a CLI the user installed and signed in to themselves."""

from __future__ import annotations

import os
import shutil
import tempfile
from abc import abstractmethod
from pathlib import Path
from typing import Callable, ClassVar

from ..domain.errors import ProviderFailed, ProviderUnavailable, ReaderError
from ..domain.models import Completion, Prompt, ProviderStatus
from ..ports.ai import AIProvider, CommandResult, OptionField, ProviderContext
from ..i18n import _

# GUI-launched apps on macOS get a short PATH, so also look where installers usually put CLIs.
COMMON_BIN_DIRS = ("/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin", "~/.npm-global/bin", "~/bin")


def binary_option(executable: str) -> OptionField:
    return OptionField("binary", _("실행 파일 경로"), kind="path", placeholder=_("자동 탐색 ({name})", name=executable),
                       help=_("비워 두면 PATH와 흔한 설치 위치에서 찾습니다."))


class CliProvider(AIProvider):
    kind = "local-cli"
    executable: ClassVar[str]
    extra_dirs: ClassVar[tuple[str, ...]] = ()
    timeout: ClassVar[float] = 300
    login_args: ClassVar[tuple[str, ...]] = ()  # cheap, token-free login check (e.g. "auth", "status")

    def __init__(self, context: ProviderContext, *, which: Callable[[str], str | None] = shutil.which) -> None:
        super().__init__(context)
        self._which = which

    def locate(self) -> str | None:
        custom = self.option("binary")
        if custom:
            path = Path(custom).expanduser()
            return str(path) if path.is_file() and os.access(path, os.X_OK) else None
        found = self._which(self.executable)
        if found:
            return found
        for folder in (*self.extra_dirs, *COMMON_BIN_DIRS):
            path = Path(folder).expanduser() / self.executable
            if path.is_file() and os.access(path, os.X_OK):
                return str(path)
        return None

    def status(self) -> ProviderStatus:
        path = self.locate()
        if not path:
            return ProviderStatus(False, _("'{name}' 명령을 찾지 못했어요. 설치하고 터미널에서 한 번 로그인한 뒤 다시 확인하세요.", name=self.executable))
        if not self.login_args:
            return ProviderStatus(True, path)
        try:
            with tempfile.TemporaryDirectory(prefix="paperdesk-") as folder:
                result = self.context.runner.run([path, *self.login_args], input_text="", cwd=Path(folder), timeout=10)
        except ReaderError:
            return ProviderStatus(True, _("{path} · 로그인 상태를 확인하지 못했어요", path=path))
        logged_in, detail = self.interpret_login(result)
        return ProviderStatus(logged_in, _("{path} · {detail}", path=path, detail=detail))

    def interpret_login(self, result: CommandResult) -> tuple[bool, str]:
        return result.returncode == 0, _("로그인됨") if result.returncode == 0 else _("로그인이 필요해요")

    def complete(self, prompt: Prompt) -> Completion:
        path = self.locate()
        if not path:
            raise ProviderUnavailable(self.status().detail)
        with tempfile.TemporaryDirectory(prefix="paperdesk-") as folder:
            workdir = Path(folder)
            result = self.context.runner.run(
                self.build_command(path, prompt, workdir),
                input_text=self.stdin_text(prompt),
                cwd=workdir,
                timeout=self.timeout,
            )
            if result.returncode != 0:
                raise ProviderFailed(self.failure_message(result))
            text = self.parse_output(result, workdir).strip()
        if not text:
            raise ProviderFailed(_("{name}가 빈 응답을 돌려줬어요.", name=self.label))
        return Completion(text, self.id, self.model)

    def stdin_text(self, prompt: Prompt) -> str:
        return prompt.as_single_text()

    def failure_message(self, result: CommandResult) -> str:
        tail = " / ".join((result.stderr or result.stdout).strip().splitlines()[-4:])
        return _("{name} 실행 실패 (코드 {code}): {tail}", name=self.label, code=result.returncode, tail=tail[:500])

    @abstractmethod
    def build_command(self, path: str, prompt: Prompt, workdir: Path) -> list[str]: ...

    @abstractmethod
    def parse_output(self, result: CommandResult, workdir: Path) -> str: ...

