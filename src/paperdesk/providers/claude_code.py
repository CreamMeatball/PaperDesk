from __future__ import annotations

import json
from pathlib import Path

from ..domain.models import Prompt
from ..ports.ai import CommandResult, OptionField
from .cli import CliProvider, binary_option
from ..i18n import _


class ClaudeCodeProvider(CliProvider):
    """Runs the user's own, unmodified Claude Code binary in print mode (claude -p).

    Anthropic's terms: third-party apps must not offer Claude.ai login or handle plan credentials, but an end user
    may sign in to the unmodified Claude Code binary with their own subscription. So PaperDesk only spawns the
    binary the user installed and logged in to; it never reads or stores Claude credentials.
    """

    id = "claude-code"
    label = "Claude Code"
    description = _("내 컴퓨터에 설치·로그인된 Claude Code(claude -p)를 도구 없이 실행합니다. 사용량은 본인 Claude 로그인(요금제 또는 API 키)에 집계됩니다.")
    docs_url = "https://code.claude.com/docs/en/legal-and-compliance"
    executable = "claude"
    extra_dirs = ("~/.claude/local",)
    login_args = ("auth", "status")
    options = (
        OptionField("model", _("모델"), placeholder=_("비워 두면 Claude Code 기본 모델")),
        binary_option("claude"),
    )

    def available_models(self) -> list[str]:
        # Official CLI aliases resolve to the account's supported versions.
        # https://code.claude.com/docs/en/model-config#model-aliases
        return ["sonnet", "opus", "haiku"]

    def interpret_login(self, result: CommandResult) -> tuple[bool, str]:
        try:
            data = json.loads(result.stdout)
        except ValueError:
            data = {}
        if data.get("loggedIn"):
            return True, _("로그인됨 ({method})", method=data.get('authMethod', ''))
        return False, _("Claude Code에 로그인되어 있지 않아요. 터미널에서 'claude'를 실행해 /login 하세요.")

    def build_command(self, path: str, prompt: Prompt, workdir: Path) -> list[str]:
        argv = [
            path, "-p",
            "--output-format", "json",
            "--no-session-persistence",
            "--tools", "",
            "--system-prompt", prompt.system,
        ]
        if self.model:
            argv += ["--model", self.model]
        return argv

    def stdin_text(self, prompt: Prompt) -> str:
        return prompt.user

    def parse_output(self, result: CommandResult, workdir: Path) -> str:
        try:
            data = json.loads(result.stdout)
        except ValueError:
            return result.stdout
        if data.get("is_error"):
            raise self.failure(result)
        return str(data.get("result") or "")

