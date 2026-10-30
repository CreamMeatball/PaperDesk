"""Update mechanisms are platform adapters; services and HTTP never replace application files."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class UpdateState:
    available: bool
    can_check: bool
    automatic_checks: bool = False
    message: str = ""
    ready: bool = False  # an update is downloaded and applies when the app starts again


class UpdateBackend(ABC):
    @abstractmethod
    def state(self) -> UpdateState: ...

    @abstractmethod
    def check(self) -> None: ...

    @abstractmethod
    def set_automatic_checks(self, enabled: bool) -> None: ...
