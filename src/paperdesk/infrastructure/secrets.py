from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .. import APP_ID
from ..ports.secrets import SecretStore


class MemorySecretStore(SecretStore):
    def __init__(self, values: dict[str, str] | None = None) -> None:
        self._values = dict(values or {})

    def get(self, name: str) -> str | None:
        return self._values.get(name)

    def set(self, name: str, value: str) -> None:
        self._values[name] = value

    def delete(self, name: str) -> None:
        self._values.pop(name, None)


class FileSecretStore(SecretStore):
    """JSON file readable only by the current user (0600). Used where no OS keychain is available."""

    def __init__(self, path: Path) -> None:
        self.path = path

    def _load(self) -> dict[str, str]:
        try:
            return json.loads(self.path.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            return {}

    def _save(self, values: dict[str, str]) -> None:
        temporary = self.path.with_suffix(".tmp")
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(values, stream)
        os.replace(temporary, self.path)

    def get(self, name: str) -> str | None:
        return self._load().get(name)

    def set(self, name: str, value: str) -> None:
        values = self._load()
        values[name] = value
        self._save(values)

    def delete(self, name: str) -> None:
        values = self._load()
        if values.pop(name, None) is not None:
            self._save(values)


class KeychainSecretStore(SecretStore):
    """macOS login keychain via the 'security' tool (generic passwords, service = app id)."""

    def __init__(self, service: str = APP_ID, tool: str = "/usr/bin/security") -> None:
        self.service = service
        self.tool = tool

    def _run(self, *args: str) -> subprocess.CompletedProcess:
        return subprocess.run([self.tool, *args], capture_output=True, text=True, timeout=15)

    def get(self, name: str) -> str | None:
        done = self._run("find-generic-password", "-s", self.service, "-a", name, "-w")
        return done.stdout.rstrip("\n") if done.returncode == 0 else None

    def set(self, name: str, value: str) -> None:
        done = self._run("add-generic-password", "-U", "-s", self.service, "-a", name, "-w", value)
        if done.returncode != 0:
            raise OSError(f"키체인에 저장하지 못했어요: {done.stderr.strip()}")

    def delete(self, name: str) -> None:
        self._run("delete-generic-password", "-s", self.service, "-a", name)
