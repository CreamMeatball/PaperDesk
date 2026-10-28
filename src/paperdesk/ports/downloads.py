from __future__ import annotations

from abc import ABC, abstractmethod


class FileDownloader(ABC):
    @abstractmethod
    def download(self, url: str, *, max_bytes: int, timeout: float) -> bytes: ...

