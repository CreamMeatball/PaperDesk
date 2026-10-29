from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from .. import KEYCHAIN_SERVICE
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


class CredentialManagerSecretStore(SecretStore):
    """Windows Credential Manager generic credentials (target = '<service>:<name>'), per user on this computer."""

    _GENERIC, _PERSIST_LOCAL_MACHINE, _NOT_FOUND = 1, 2, 1168

    def __init__(self, service: str = KEYCHAIN_SERVICE) -> None:
        import ctypes
        from ctypes import wintypes

        class Credential(ctypes.Structure):
            _fields_ = [("Flags", wintypes.DWORD), ("Type", wintypes.DWORD), ("TargetName", wintypes.LPWSTR),
                        ("Comment", wintypes.LPWSTR), ("LastWritten", wintypes.FILETIME),
                        ("CredentialBlobSize", wintypes.DWORD), ("CredentialBlob", ctypes.POINTER(ctypes.c_ubyte)),
                        ("Persist", wintypes.DWORD), ("AttributeCount", wintypes.DWORD), ("Attributes", ctypes.c_void_p),
                        ("TargetAlias", wintypes.LPWSTR), ("UserName", wintypes.LPWSTR)]

        self.service = service
        self._ctypes, self._Credential = ctypes, Credential
        self._advapi = ctypes.WinDLL("advapi32", use_last_error=True)
        self._advapi.CredReadW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, ctypes.POINTER(ctypes.POINTER(Credential)))
        self._advapi.CredWriteW.argtypes = (ctypes.POINTER(Credential), wintypes.DWORD)
        self._advapi.CredDeleteW.argtypes = (wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD)
        self._advapi.CredFree.argtypes = (ctypes.c_void_p,)

    def _target(self, name: str) -> str:
        return f"{self.service}:{name}"

    def get(self, name: str) -> str | None:
        ctypes = self._ctypes
        found = ctypes.POINTER(self._Credential)()
        if not self._advapi.CredReadW(self._target(name), self._GENERIC, 0, ctypes.byref(found)):
            if ctypes.get_last_error() == self._NOT_FOUND:
                return None
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            item = found.contents
            return ctypes.string_at(item.CredentialBlob, item.CredentialBlobSize).decode("utf-8")
        finally:
            self._advapi.CredFree(found)

    def set(self, name: str, value: str) -> None:
        ctypes = self._ctypes
        blob = value.encode("utf-8")
        buffer = (ctypes.c_ubyte * len(blob)).from_buffer_copy(blob)
        credential = self._Credential(Type=self._GENERIC, TargetName=self._target(name), UserName=name,
                                      CredentialBlobSize=len(blob), CredentialBlob=buffer, Persist=self._PERSIST_LOCAL_MACHINE)
        if not self._advapi.CredWriteW(ctypes.byref(credential), 0):
            raise OSError(f"자격 증명 관리자에 저장하지 못했어요: {ctypes.WinError(ctypes.get_last_error())}")

    def delete(self, name: str) -> None:
        self._advapi.CredDeleteW(self._target(name), self._GENERIC, 0)


class KeychainSecretStore(SecretStore):
    """macOS login keychain via the 'security' tool (generic passwords, service = app id)."""

    def __init__(self, service: str = KEYCHAIN_SERVICE, tool: str = "/usr/bin/security") -> None:
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
