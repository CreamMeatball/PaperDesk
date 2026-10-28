from __future__ import annotations

from abc import ABC, abstractmethod


class SecretStore(ABC):
    """API keys live here, never in settings.json."""

    @abstractmethod
    def get(self, name: str) -> str | None: ...

    @abstractmethod
    def set(self, name: str, value: str) -> None: ...

    @abstractmethod
    def delete(self, name: str) -> None: ...
