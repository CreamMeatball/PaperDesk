from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from enum import Enum


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


@dataclass(frozen=True)
class Folder:
    """A topic folder. parent_id=None means top level; folders nest to any depth."""

    id: str
    name: str
    parent_id: str | None
    created_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Document:
    id: str
    title: str
    filename: str
    sha256: str
    size_bytes: int
    created_at: str
    folder_id: str | None = None  # None = unfiled
    last_opened_at: str | None = None
    page_count: int = 0
    text_pages: int = 0

    def renamed(self, title: str) -> "Document":
        return replace(self, title=title)

    def moved(self, folder_id: str | None) -> "Document":
        return replace(self, folder_id=folder_id)

    def opened(self, at: str) -> "Document":
        return replace(self, last_opened_at=at)

    def with_text(self, page_count: int) -> "Document":
        return replace(self, page_count=page_count, text_pages=page_count)

    def to_dict(self) -> dict:
        return asdict(self)


class AssistTask(str, Enum):
    TRANSLATE = "translate"
    EXPLAIN = "explain"
    ASK = "ask"
    SUMMARIZE = "summarize"


@dataclass(frozen=True)
class AssistRequest:
    task: AssistTask
    text: str
    question: str = ""
    context: str = ""
    target_language: str = "English"


@dataclass(frozen=True)
class Prompt:
    system: str
    user: str

    def as_single_text(self) -> str:
        """For backends that accept only one message, such as codex exec."""
        return f"{self.system}\n\n---\n\n{self.user}"


@dataclass(frozen=True)
class Completion:
    text: str
    provider_id: str
    model: str = ""
    cached: bool = False

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ProviderStatus:
    available: bool
    detail: str = ""
    models: tuple[str, ...] = ()

