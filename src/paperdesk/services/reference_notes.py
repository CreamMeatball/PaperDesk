from __future__ import annotations

import hashlib
import json

from ..domain.errors import InvalidInput
from ..domain.models import AssistRequest, AssistTask, PaperMetadata
from ..ports.repositories import CompletionCache
from ..ports.scholarly import ScholarlyIndex
from .assistant import AssistantService
from .references import ReferenceParser, clean_citation

META_PREFIX = "meta:v1:"


class ReferenceNoteService:
    """'이 논문 설명' for a citation: look up the abstract first, then ask the AI to explain only from that."""

    def __init__(self, index: ScholarlyIndex, assistant: AssistantService, cache: CompletionCache, *,
                 parser: ReferenceParser | None = None) -> None:
        self._index = index
        self._assistant = assistant
        self._cache = cache
        self._parser = parser or ReferenceParser()

    def metadata(self, citation: str) -> PaperMetadata | None:
        text = clean_citation(citation)
        if len(text) < 8 or len(text) > 2000:
            raise InvalidInput("참고문헌 형식이 올바르지 않아요.")
        key = META_PREFIX + hashlib.sha256(text.encode()).hexdigest()
        saved = self._cache.get(key)
        if saved is not None:
            data = json.loads(saved)
            return PaperMetadata(**data) if data else None
        parsed = self._parser.parse(text)
        found = self._index.lookup(title=parsed.title, arxiv_id=parsed.arxiv_id, doi=parsed.doi, year=parsed.year)
        self._cache.put(key, json.dumps(found.to_dict() if found else None, ensure_ascii=False))
        return found

    def explain(self, citation: str, *, language: str, cache_only: bool = False) -> dict:
        found = self.metadata(citation)
        parsed = self._parser.parse(citation)
        if found:
            material = f"Title: {found.title}\nAuthors: {found.authors}\nYear: {found.year}\nVenue: {found.venue}\nAbstract: {found.abstract or '(none)'}"
        else:
            material = f"Title (from the citation only): {parsed.title}\nAbstract: (not found)"
        completion = self._assistant.run(AssistRequest(AssistTask.REFERENCE, material, context=clean_citation(citation),
                                                       target_language=language), cache_only=cache_only)
        return {"metadata": found.to_dict() if found else None, "grounded": bool(found and found.abstract),
                "summary": completion.text if completion else None,
                "provider_id": completion.provider_id if completion else None, "model": completion.model if completion else ""}

