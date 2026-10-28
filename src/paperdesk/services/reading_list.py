from __future__ import annotations

import re
import uuid
from typing import Callable

from ..domain.errors import InvalidInput, NotFound
from ..domain.models import Document, ReadingItem, utcnow
from ..ports.downloads import FileDownloader
from ..ports.repositories import ReadingListRepository
from .library import MAX_PDF_BYTES, LibraryService
from .references import ReferenceParser, clean_citation

MAX_CITATION = 2000


def _title_key(title: str) -> str:
    return re.sub(r"[^0-9a-z]+", "", title.casefold())


class ReadingListService:
    """'읽어볼 논문': papers saved from citations, later turned into library PDFs."""

    def __init__(self, items: ReadingListRepository, library: LibraryService, downloader: FileDownloader, *,
                 parser: ReferenceParser | None = None, new_id: Callable[[], str] = lambda: uuid.uuid4().hex,
                 clock: Callable[[], str] = utcnow) -> None:
        self._items = items
        self._library = library
        self._downloader = downloader
        self._parser = parser or ReferenceParser()
        self._new_id = new_id
        self._clock = clock

    def list(self) -> list[ReadingItem]:
        return self._items.list()

    def get(self, item_id: str) -> ReadingItem:
        item = self._items.get(item_id)
        if item is None:
            raise NotFound("읽어볼 논문을 찾지 못했어요.")
        return item

    def add(self, citation: str, *, source_doc_id: str | None = None, title: str = "") -> tuple[ReadingItem, bool]:
        """Return (item, created). The same paper saved twice (same arXiv id, DOI or title) returns the existing item."""
        text = clean_citation(citation)
        if len(text) < 8:
            raise InvalidInput("논문 정보가 너무 짧아요.")
        if len(text) > MAX_CITATION:
            raise InvalidInput("인용문이 너무 길어요. 한 논문만 선택해 주세요.")
        if source_doc_id:
            self._library.get(source_doc_id)
        parsed = self._parser.parse(text)
        clean_title = " ".join((title or parsed.title or text[:200]).split())[:300]
        for existing in self._items.list():
            same_id = (parsed.arxiv_id and existing.arxiv_id == parsed.arxiv_id) or (parsed.doi and existing.doi.lower() == parsed.doi.lower())
            if same_id or _title_key(existing.title) == _title_key(clean_title):
                return existing, False
        item = ReadingItem(
            id=self._new_id(), title=clean_title, citation=text, created_at=self._clock(), authors=parsed.authors,
            year=parsed.year, arxiv_id=parsed.arxiv_id, doi=parsed.doi, url=parsed.url, source_doc_id=source_doc_id,
        )
        self._items.add(item)
        return item, True

    def update(self, item_id: str, *, title: str | None = None, note: str | None = None) -> ReadingItem:
        item = self.get(item_id)
        changes = {}
        if title is not None:
            clean = " ".join(str(title).split())
            if not clean:
                raise InvalidInput("제목을 입력하세요.")
            changes["title"] = clean[:300]
        if note is not None:
            changes["note"] = str(note)[:4000]
        updated = ReadingItem(**{**item.__dict__, **changes})
        self._items.update(updated)
        return updated

    def remove(self, item_id: str) -> None:
        self.get(item_id)
        self._items.delete(item_id)

    def _default_folder(self, item: ReadingItem, folder_id: str | None) -> str | None:
        if folder_id is not None:
            return folder_id or None
        if item.source_doc_id:  # same topic as the paper that cited it
            try:
                return self._library.get(item.source_doc_id).folder_id
            except NotFound:
                return None
        return None

    def attach_pdf(self, item_id: str, filename: str, data: bytes, folder_id: str | None = None) -> tuple[ReadingItem, Document]:
        item = self.get(item_id)
        document, created = self._library.import_pdf(filename, data, self._default_folder(item, folder_id))
        if created and item.title:
            document = self._library.rename(document.id, item.title)
        linked = ReadingItem(**{**item.__dict__, "document_id": document.id})
        self._items.update(linked)
        return linked, document

    def fetch_arxiv_pdf(self, item_id: str, folder_id: str | None = None) -> tuple[ReadingItem, Document]:
        item = self.get(item_id)
        if not re.fullmatch(r"\d{4}\.\d{4,5}", item.arxiv_id or ""):
            raise InvalidInput("arXiv 번호가 없는 논문이에요. PDF를 직접 추가해 주세요.")
        data = self._downloader.download(f"https://arxiv.org/pdf/{item.arxiv_id}", max_bytes=MAX_PDF_BYTES, timeout=90)
        return self.attach_pdf(item_id, f"{item.arxiv_id}.pdf", data, folder_id)

