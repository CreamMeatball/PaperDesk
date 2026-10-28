from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import Document, Folder, ReadingItem


class DocumentRepository(ABC):
    @abstractmethod
    def add(self, document: Document) -> None: ...

    @abstractmethod
    def get(self, doc_id: str) -> Document | None: ...

    @abstractmethod
    def find_by_sha256(self, digest: str) -> Document | None: ...

    @abstractmethod
    def list(self) -> list[Document]: ...

    @abstractmethod
    def update(self, document: Document) -> None: ...

    @abstractmethod
    def delete(self, doc_id: str) -> None: ...

    @abstractmethod
    def move_all(self, from_folder: str, to_folder: str | None) -> None: ...


class FolderRepository(ABC):
    @abstractmethod
    def add(self, folder: Folder) -> None: ...

    @abstractmethod
    def get(self, folder_id: str) -> Folder | None: ...

    @abstractmethod
    def list(self) -> list[Folder]: ...

    @abstractmethod
    def update(self, folder: Folder) -> None: ...

    @abstractmethod
    def delete(self, folder_id: str) -> None: ...


class ReadingListRepository(ABC):
    @abstractmethod
    def add(self, item: ReadingItem) -> None: ...

    @abstractmethod
    def get(self, item_id: str) -> ReadingItem | None: ...

    @abstractmethod
    def list(self) -> list[ReadingItem]: ...

    @abstractmethod
    def update(self, item: ReadingItem) -> None: ...

    @abstractmethod
    def delete(self, item_id: str) -> None: ...


class PageTextRepository(ABC):
    """Plain text per page, extracted once by the viewer. Used by search, summaries and the MCP server."""

    @abstractmethod
    def replace(self, doc_id: str, pages: list[str]) -> None: ...

    @abstractmethod
    def read(self, doc_id: str, first: int, last: int) -> list[tuple[int, str]]:
        """Return (page_number, text) for 1-based inclusive page numbers."""

    @abstractmethod
    def search(self, query: str, limit: int) -> list[tuple[str, int, str]]:
        """Return (doc_id, page_number, snippet)."""


class CompletionCache(ABC):
    @abstractmethod
    def get(self, key: str) -> str | None: ...

    @abstractmethod
    def put(self, key: str, text: str) -> None: ...

