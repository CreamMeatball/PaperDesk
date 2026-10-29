"""Base class for providers that run a CLI the user installed and signed in to themselves."""

from __future__ import annotations

import os
import shutil
import tempfile
import re
from abc import abstractmethod
from pathlib import Path
from typing import Callable, ClassVar

from ..domain.errors import (ProviderFailed, ProviderUnavailable, ReaderError, ProviderAuthRequired,
                             ProviderLimitReached, UnsupportedModel)
from ..domain.models import Completion, Prompt, ProviderStatus
from ..ports.ai import AIProvider, CommandResult, OptionField, ProviderContext
from ..i18n import _

WINDOWS = os.name == "nt"
# GUI-launched apps get a short PATH, so also look where installers usually put CLIs.
COMMON_BIN_DIRS = (("%APPDATA%/npm", "~/.local/bin", "%LOCALAPPDATA%/Microsoft/WinGet/Links") if WINDOWS else
                   ("/opt/homebrew/bin", "/usr/local/bin", "~/.local/bin", "~/.npm-global/bin", "~/bin"))
# npm's .cmd shim for a CLI that ships a native binary only starts that .exe.
_SHIM_EXE = re.compile(r'"%dp0%\\([^"%]+\.exe)"', re.I)


def _folders(entries) -> list[Path]:
    """Expand ~, %VARS% and versioned folders such as .../bin/* (most recently installed first)."""
    folders = []
    for entry in entries:
        path = Path(os.path.expandvars(entry)).expanduser()
        if "*" not in path.name:
            folders.append(path)
        elif path.parent.is_absolute():
            folders += sorted((p for p in path.parent.glob(path.name) if p.is_dir()), key=lambda p: p.stat().st_mtime, reverse=True)
    return folders


def _names(executable: str) -> tuple[str, ...]:
    # On Windows a bare name is npm's POSIX shell script, which CreateProcess cannot run.
    return (executable + ".exe", executable + ".cmd") if WINDOWS else (executable,)


def direct(path: str) -> str:
    """Run the .exe behind an npm shim directly, so arguments never pass through cmd.exe."""
    if not path.lower().endswith(".cmd"):
        return path
    try:
        match = _SHIM_EXE.search(Path(path).read_text(encoding="utf-8", errors="replace"))
    except OSError:
        return path
    target = Path(path).parent.joinpath(*match.group(1).split("\\")) if match else None
    return str(target) if target and target.is_file() else path


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
            return direct(str(path)) if path.is_file() and os.access(path, os.X_OK) else None
        found = self._which(self.executable)
        if found:
            return direct(found)
        for path in self._installed():
            if os.access(path, os.X_OK):
                return direct(str(path))
        return None

    def _installed(self) -> list[Path]:
        return [folder / name for folder in _folders((*self.extra_dirs, *COMMON_BIN_DIRS))
                for name in _names(self.executable) if (folder / name).is_file()]

    def discover(self) -> dict:
        paths = []
        located = self.locate()
        for candidate in [located, *(direct(str(path)) for path in self._installed())]:
            if candidate and candidate not in paths and Path(candidate).is_file():
                paths.append(candidate)
        candidates = []
        for path in paths:
            try:
                with tempfile.TemporaryDirectory(prefix='paperdesk-version-') as folder:
                    done = self.context.runner.run([path, '--version'], input_text='', cwd=Path(folder), timeout=5)
                match = re.search(r'\d+\.\d+(?:\.\d+)?', done.stdout)
                if done.returncode == 0 and match:
                    version = match.group()
                    candidates.append({'path': path, 'version': version})
            except ReaderError:
                continue
        candidates.sort(key=lambda c: tuple(int(n) for n in c['version'].split('.')), reverse=True)
        selected = self.option('binary') or (candidates[0]['path'] if candidates else located)
        models = self.context.runner.codex_models(direct(selected)) if selected and self.id == 'codex-cli' else []
        return {'candidates': candidates, 'selected': selected, 'models': models}

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
            return ProviderStatus(False, _("{path} · 로그인 상태를 확인하지 못했어요", path=path))
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
                raise self.failure(result)
            text = self.parse_output(result, workdir).strip()
        if not text:
            raise ProviderFailed(_("{name}가 빈 응답을 돌려줬어요.", name=self.label))
        return Completion(text, self.id, self.model)

    def stdin_text(self, prompt: Prompt) -> str:
        return prompt.as_single_text()

    def failure(self, result: CommandResult) -> ReaderError:
        detail = (result.stderr + '\n' + result.stdout).lower()
        if 'model_not_found' in detail or 'model is not supported' in detail or ('model' in detail and 'not supported' in detail):
            return UnsupportedModel(_("선택한 모델을 사용할 수 없어요. 설치·모델 확인에서 지원 모델을 고르고 연결 시험을 해 주세요."))
        if any(word in detail for word in ('hit your', 'rate_limit', 'rate limit', 'usage limit', 'quota')):
            reset = re.search(r'resets\s+([0-9:apm. ]+(?:\([A-Za-z_/]+\))?)', result.stdout + result.stderr, re.I)
            if reset:
                return ProviderLimitReached(_("AI 사용 한도에 도달했어요. 초기화 안내: {reset}", reset=reset.group(1).strip()[:80]))
            return ProviderLimitReached(_("AI 사용 한도에 도달했어요. 해당 AI에서 한도를 확인한 뒤 다시 시도해 주세요."))
        if any(word in detail for word in ('authenticate', 'authentication', 'not logged', 'unauthorized', 'oauth', 'session expired')):
            return ProviderAuthRequired(_("AI 로그인이 만료되었거나 필요해요. 해당 CLI에서 다시 로그인한 뒤 연결 시험을 해 주세요."))
        return ProviderFailed(_("{name} 요청에 실패했어요 (코드 {code}). 연결 시험과 네트워크 상태를 확인해 주세요.",
                                name=self.label, code=result.returncode))

    @abstractmethod
    def build_command(self, path: str, prompt: Prompt, workdir: Path) -> list[str]: ...

    @abstractmethod
    def parse_output(self, result: CommandResult, workdir: Path) -> str: ...

