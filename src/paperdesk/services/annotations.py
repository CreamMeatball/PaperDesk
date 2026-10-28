from __future__ import annotations

import uuid
from typing import Callable

from ..domain.errors import InvalidInput, NotFound
from ..domain.models import Annotation, utcnow
from ..ports.repositories import AnnotationRepository
from .library import LibraryService

COLORS = ("yellow", "green", "blue", "pink")
KINDS = ("highlight", "note")


class AnnotationService:
    def __init__(self, repository: AnnotationRepository, library: LibraryService, *,
                 new_id: Callable[[], str] = lambda: uuid.uuid4().hex, clock: Callable[[], str] = utcnow) -> None:
        self._repository = repository
        self._library = library
        self._new_id = new_id
        self._clock = clock

    def list(self, doc_id: str) -> list[Annotation]:
        self._library.get(doc_id)
        return self._repository.list(doc_id)

    @staticmethod
    def _rects(raw) -> tuple[tuple[float, float, float, float], ...]:
        if not isinstance(raw, list) or not 0 < len(raw) <= 200:
            raise InvalidInput("표시할 위치가 없어요.")
        rects = []
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) != 4:
                raise InvalidInput("위치 형식이 올바르지 않아요.")
            left, top, right, bottom = (max(0.0, min(1.0, float(v))) for v in item)
            if right <= left or bottom <= top:
                continue
            rects.append((round(left, 5), round(top, 5), round(right, 5), round(bottom, 5)))
        if not rects:
            raise InvalidInput("표시할 위치가 없어요.")
        return tuple(rects)

    def add(self, doc_id: str, *, page: int, kind: str, color: str, text: str, rects, note: str = "") -> Annotation:
        document = self._library.get(doc_id)
        if kind not in KINDS:
            raise InvalidInput("알 수 없는 표시 종류예요.")
        if color not in COLORS:
            raise InvalidInput("알 수 없는 색이에요.")
        if not isinstance(page, int) or page < 1 or (document.page_count and page > document.page_count):
            raise InvalidInput("쪽 번호가 올바르지 않아요.")
        annotation = Annotation(self._new_id(), doc_id, page, kind, color, " ".join(str(text).split())[:4000],
                                self._rects(rects), self._clock(), str(note or "")[:8000])
        self._repository.add(annotation)
        return annotation

    def update(self, annotation_id: str, *, color: str | None = None, note: str | None = None) -> Annotation:
        current = self._repository.get(annotation_id)
        if current is None:
            raise NotFound("표시를 찾지 못했어요.")
        if color is not None and color not in COLORS:
            raise InvalidInput("알 수 없는 색이에요.")
        updated = Annotation(**{**current.__dict__, "color": color or current.color,
                                "note": current.note if note is None else str(note)[:8000],
                                "kind": "note" if (note or current.note) else current.kind})
        self._repository.update(updated)
        return updated

    def delete(self, annotation_id: str) -> None:
        if self._repository.get(annotation_id) is None:
            raise NotFound("표시를 찾지 못했어요.")
        self._repository.delete(annotation_id)

