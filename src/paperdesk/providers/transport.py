"""Default process and HTTP adapters (stdlib only)."""

from __future__ import annotations

import json
import os
import subprocess
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator, Mapping

from .. import APP_ID, __version__
from ..domain.errors import ProviderFailed, ProviderUnavailable
from ..ports.ai import CommandResult, CommandRunner, HttpClient
from ..i18n import _


class SubprocessRunner(CommandRunner):
    def run(self, argv: list[str], *, input_text: str, cwd: Path, timeout: float) -> CommandResult:
        try:
            done = subprocess.run(
                argv,
                input=input_text,
                capture_output=True,
                text=True,
                cwd=cwd,
                timeout=timeout,
                env=dict(os.environ, NO_COLOR="1"),
            )
        except subprocess.TimeoutExpired as error:
            raise ProviderFailed(_("{seconds}초 안에 응답이 오지 않았어요.", seconds=f"{timeout:.0f}")) from error
        except OSError as error:
            raise ProviderUnavailable(_("실행하지 못했어요: {error}", error=str(error))) from error
        return CommandResult(done.returncode, done.stdout, done.stderr)


def _error_text(raw: str) -> str:
    try:
        data = json.loads(raw)
    except ValueError:
        return raw.strip()[:400]
    error = data.get("error", data) if isinstance(data, dict) else data
    if isinstance(error, dict):
        code = error.get("code") or error.get("type") or ""
        message = error.get("message") or json.dumps(error, ensure_ascii=False)
        return f"{code}: {message}" if code else str(message)
    return str(error)[:400]


class UrllibHttpClient(HttpClient):
    def _open(self, method: str, url: str, headers: Mapping[str, str], body: dict | None, timeout: float):
        data = None if body is None else json.dumps(body).encode()
        request = urllib.request.Request(
            url,
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "User-Agent": f"{APP_ID}/{__version__}", **headers},
        )
        try:
            return urllib.request.urlopen(request, timeout=timeout)
        except urllib.error.HTTPError as error:
            raw = error.read(4000).decode("utf-8", "replace")
            raise ProviderFailed(f"HTTP {error.code} {_error_text(raw)}") from error
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise ProviderUnavailable(_("연결하지 못했어요: {reason}", reason=str(reason))) from error

    def get_json(self, url: str, *, headers: Mapping[str, str], timeout: float) -> Any:
        with self._open("GET", url, headers, None, timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def post_json(self, url: str, *, headers: Mapping[str, str], body: dict, timeout: float) -> Any:
        with self._open("POST", url, headers, body, timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def stream_sse(self, url: str, *, headers: Mapping[str, str], body: dict, timeout: float) -> Iterator[dict]:
        with self._open("POST", url, {"Accept": "text/event-stream", **headers}, body, timeout) as response:
            lines: list[str] = []
            for raw in response:
                line = raw.decode("utf-8").rstrip("\r\n")
                if line:
                    if line.startswith("data:"):
                        lines.append(line[5:].lstrip())
                    continue
                if lines:
                    payload = "\n".join(lines)
                    lines = []
                    if payload != "[DONE]":
                        yield json.loads(payload)
            if lines and "\n".join(lines) != "[DONE]":
                yield json.loads("\n".join(lines))

