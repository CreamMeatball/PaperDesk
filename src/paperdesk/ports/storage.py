from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class BlobStore(ABC):
    """Stores raw files (PDFs now; page images or exports later) under opaque keys."""

    @abstractmethod
    def put(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def path(self, key: str) -> Path: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...

    @abstractmethod
    def delete(self, key: str) -> None: ...
