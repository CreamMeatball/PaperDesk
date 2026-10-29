"""Updates for source installs (scripts/install_source.py).

The install keeps its own git clone of the repository, installed in editable mode, so a code update is
only a checkout. New commits are fetched in the background while the app runs and applied the next time it
opens, before any window or server starts; dependencies are reinstalled only when the pinned locks change.
The user's own git and credentials are used as-is; git never prompts (no terminal or login window).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Callable

from ..domain.models import utcnow
from ..i18n import _
from ..ports.updates import UpdateBackend, UpdateState

CONFIG = "paperdesk-source.json"
WINDOWS = os.name == "nt"


def find_git() -> str | None:
    found = shutil.which("git")
    if found or not WINDOWS:
        return found
    # A Start-menu launch may not have Git for Windows on PATH.
    for base in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("LOCALAPPDATA") and os.path.join(os.environ["LOCALAPPDATA"], "Programs")):
        candidate = Path(base) / "Git" / "cmd" / "git.exe" if base else None
        if candidate and candidate.is_file():
            return str(candidate)
    return None


def git_environment() -> dict:
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    env.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return env


def git_command(git: str, *args: str) -> list[str]:
    # Same bytes on every system: Git for Windows would otherwise check out CRLF line endings.
    return [git, "-c", "core.autocrlf=false", "-c", "credential.interactive=false", *args]


def run_git(git: str, *args: str, cwd: Path | None = None, timeout: float = 30,
            run: Callable = subprocess.run) -> subprocess.CompletedProcess:
    options = {"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS else {}
    return run(git_command(git, *args), cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace",
               timeout=timeout, env=git_environment(), stdin=subprocess.DEVNULL, **options)


def lock_digest(source: Path, locks: list[str]) -> str:
    digest = hashlib.sha256()
    for name in sorted(locks):
        digest.update(name.encode() + b"\0" + (source / name).read_bytes() + b"\0")
    return digest.hexdigest()


class SourceInstall:
    """The install's clone and its record (CONFIG next to the virtual environment)."""

    def __init__(self, prefix: Path, data: dict, *, git: str | None = None, run: Callable = subprocess.run) -> None:
        self.prefix = prefix
        self.data = data
        self.source = Path(data["source"])
        self.branch = data.get("branch") or "main"
        self.git = git
        self._run = run

    @classmethod
    def current(cls) -> "SourceInstall | None":
        if sys.prefix == sys.base_prefix:
            return None
        return cls.load(Path(sys.prefix).parent)

    @classmethod
    def load(cls, prefix: Path, **options) -> "SourceInstall | None":
        try:
            data = json.loads((prefix / CONFIG).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        if not isinstance(data, dict) or not data.get("source"):
            return None
        options.setdefault("git", find_git())
        return cls(prefix, data, **options)

    @property
    def auto_update(self) -> bool:
        """Automatic checks: fetch from GitHub in the background. Fetched commits apply on launch either way."""
        return bool(self.data.get("auto_update")) and self.git is not None

    def save(self, **changes) -> None:
        self.data.update(changes)
        temporary = self.prefix / (CONFIG + ".tmp")
        temporary.write_text(json.dumps(self.data, indent=1, ensure_ascii=False), encoding="utf-8")
        os.replace(temporary, self.prefix / CONFIG)

    def set_auto_update(self, enabled: bool) -> None:
        self.save(auto_update=bool(enabled))

    def _git(self, *args: str, timeout: float = 30) -> subprocess.CompletedProcess:
        return run_git(self.git, *args, cwd=self.source, timeout=timeout, run=self._run)

    def _ok(self, *args: str, timeout: float = 30) -> str | None:
        try:
            done = self._git(*args, timeout=timeout)
        except (OSError, subprocess.TimeoutExpired):
            return None
        return done.stdout.strip() if done.returncode == 0 else None

    def fetch(self, timeout: float = 60) -> bool:
        """Download new commits only (git transfers the difference); nothing changes until the next launch."""
        if self.git is None:
            return False
        ok = self._ok("fetch", "--quiet", "--no-tags", "origin", self.branch, timeout=timeout) is not None
        # A check reports only its own result. apply_failed and local_changes stay visible in Settings until an
        # update applies; the automatic check right after launch would otherwise hide them every time.
        error = self.data.get("error") or ""
        if error in ("", "fetch_failed"):
            error = "" if ok else "fetch_failed"
        self.save(checked_at=utcnow(), error=error)
        return ok

    def target(self) -> str | None:
        return self._ok("rev-parse", "--verify", "--quiet", f"origin/{self.branch}^{{commit}}") if self.git else None

    def pending(self) -> str | None:
        target = self.target()
        return target if target and target != self.data.get("commit") else None

    def behind(self) -> int:
        target = self.target()
        count = self._ok("rev-list", "--count", f"{self.data.get('commit')}..{target}") if target else None
        return int(count) if count and count.isdigit() else 0

    def apply(self, python: str = sys.executable) -> bool:
        """Check out fetched commits; reinstall dependencies only when their locks changed. False keeps the current version."""
        target = self.pending()
        if not target:
            # Nothing left to apply (for example upstream went back to the installed commit): drop stale notices.
            if self.data.get("error") in ("apply_failed", "local_changes"):
                self.save(error="")
            return False
        if self._ok("status", "--porcelain", "--untracked-files=no") != "":
            self.save(error="local_changes")
            return False
        previous = self.data.get("commit")
        locks = list(self.data.get("lock_files") or [])
        if self._ok("reset", "--quiet", "--hard", target) is None:
            self.save(error="apply_failed")
            return False
        try:
            digest = lock_digest(self.source, locks)
            if digest != self.data.get("locks") and not self._pip(python, locks):
                raise RuntimeError("dependencies")
            # Package metadata (entry points) lives outside the editable checkout; refresh it when pyproject changes.
            if self._ok("diff", "--quiet", previous, target, "--", "pyproject.toml") is None and not self._pip(python, [], editable=True):
                raise RuntimeError("package")
        except (OSError, RuntimeError):
            # Back to the version that was running, dependencies included (best effort), and say so in Settings.
            self._ok("reset", "--quiet", "--hard", previous)
            if locks:
                self._pip(python, locks)
            self.save(error="apply_failed")
            return False
        self.save(commit=target, locks=digest, error="", updated_at=utcnow())
        return True

    def _pip(self, python: str, locks: list[str], *, editable: bool = False) -> bool:
        command = [python, "-m", "pip", "install", "--disable-pip-version-check", "--require-virtualenv", "--quiet"]
        if editable:
            command += ["--no-deps", "--no-build-isolation", "-e", str(self.source)]
        else:
            command += [arg for lock in locks for arg in ("-r", str(self.source / lock))]
        options = {"creationflags": subprocess.CREATE_NO_WINDOW} if WINDOWS else {}
        try:
            return self._run(command, capture_output=True, text=True, encoding="utf-8", errors="replace",
                             timeout=1800, stdin=subprocess.DEVNULL, **options).returncode == 0
        except (OSError, subprocess.TimeoutExpired):
            return False

    def summary(self) -> str:
        commit = str(self.data.get("commit") or "")[:7]
        error = self.data.get("error")
        if error == "local_changes":
            return _("앱의 소스 사본에 바뀐 파일이 있어 자동 업데이트를 건너뛰었어요. 설치 스크립트를 다시 실행해 주세요.")
        if error == "apply_failed":
            return _("업데이트를 적용하지 못해 이전 버전({commit})으로 실행 중이에요. 다음에 앱을 열 때 다시 시도해요.", commit=commit)
        behind = self.behind() if self.pending() else 0
        if behind:
            return _("새 버전(커밋 {n}개)을 받아 두었어요. 앱을 다시 열면 적용돼요.", n=behind)
        if error == "fetch_failed":
            return _("업데이트 서버(GitHub)에 연결하지 못했어요. 지금 버전({commit})으로 실행 중이에요.", commit=commit)
        if not self.auto_update:
            return _("소스 설치 · 현재 버전({commit})이에요. 자동 확인이 꺼져 있어 '업데이트 확인'을 누를 때만 새 커밋을 받아요.", commit=commit)
        return _("소스 설치 · 최신 버전({commit})이에요. 앱을 열 때 GitHub에서 새 커밋을 확인해요.", commit=commit)


class SourceUpdates(UpdateBackend):
    """Settings → updates for a source install: manual checks fetch now; updates apply on the next launch."""

    def __init__(self, install: SourceInstall) -> None:
        self.install = install

    def state(self) -> UpdateState:
        if self.install.git is None:
            return UpdateState(False, False, message=_("git을 찾지 못해 자동 업데이트를 할 수 없어요. git을 설치한 뒤 설치 스크립트를 다시 실행해 주세요."))
        return UpdateState(True, True, automatic_checks=self.install.auto_update, message=self.install.summary())

    def check(self) -> None:
        self.install.fetch(timeout=30)

    def set_automatic_checks(self, enabled: bool) -> None:
        self.install.set_auto_update(enabled)
