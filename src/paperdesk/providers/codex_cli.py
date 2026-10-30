from __future__ import annotations

from pathlib import Path
import json

from ..domain.models import Prompt
from ..ports.ai import CommandResult, OptionField
from .cli import WINDOWS, CliProvider, binary_option
from ..i18n import _


class CodexCliProvider(CliProvider):
    """Runs the user's own Codex CLI non-interactively (codex exec), an integration path OpenAI documents.

    Uses whatever login the CLI already has (ChatGPT plan or API key). PaperDesk never sees the credentials.
    Later upgrade path: drive 'codex app-server' over JSON-RPC for streaming and multi-turn threads.
    """

    id = "codex-cli"
    label = "Codex CLI"
    description = _("내 컴퓨터에 설치·로그인된 Codex CLI(codex exec)를 실행합니다. Codex 로그인(ChatGPT 요금제 또는 API 키) 사용량으로 처리됩니다.")
    docs_url = "https://developers.openai.com/codex/noninteractive"
    executable = "codex"
    supports_images = True
    # The Codex desktop app's own CLI; on Windows it lives in a per-version folder.
    extra_dirs = (("%LOCALAPPDATA%/OpenAI/Codex/bin/*",) if WINDOWS else
                  ("/Applications/ChatGPT.app/Contents/Resources/codex-cli/CodexCLI.app/Contents/MacOS",
                   "/Applications/Codex.app/Contents/Resources"))
    login_args = ("login", "status")
    options = (
        OptionField("model", _("모델"), placeholder=_("비워 두면 Codex 기본 모델")),
        binary_option("codex"),
    )

    def available_models(self) -> list[str]:
        path = self.locate()
        return self.context.runner.codex_models(path) if path else []

    def interpret_login(self, result: CommandResult) -> tuple[bool, str]:
        line = (result.stdout or result.stderr).strip().splitlines()[:1]
        if result.returncode == 0 and line:
            return True, line[0]
        return False, _("Codex에 로그인되어 있지 않아요. 터미널에서 'codex login'을 실행하세요.")

    def build_command(self, path: str, prompt: Prompt, workdir: Path) -> list[str]:
        argv = [
            path, "exec",
            "--ignore-user-config",
            "--disable", "shell_tool",
            "--disable", "unified_exec",
            "--disable", "multi_agent",
            "--disable", "shell_snapshot",
            "--skip-git-repo-check",
            "--ephemeral",
            "--sandbox", "read-only",
            "--color", "never",
            "--output-last-message", str(workdir / "last-message.txt"),
        ]
        if self.model:
            argv += ["--model", self.model]
        if prompt.response_schema:
            schema = workdir / "response-schema.json"
            schema.write_text(json.dumps(prompt.response_schema), encoding="utf-8")
            argv += ["--output-schema", str(schema)]
        for number, image in enumerate(prompt.images, start=1):
            path_ = workdir / f"image-{number}.{'jpg' if image.media_type == 'image/jpeg' else 'png'}"
            path_.write_bytes(image.data)
            argv.append(f"--image={path_}")  # '=' form: --image takes several values and would swallow '-'
        argv.append("-")  # prompt comes from stdin
        return argv

    def parse_output(self, result: CommandResult, workdir: Path) -> str:
        last = workdir / "last-message.txt"
        if last.exists() and last.read_text(encoding="utf-8").strip():
            return last.read_text(encoding="utf-8")
        return result.stdout

