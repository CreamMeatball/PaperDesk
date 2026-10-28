from __future__ import annotations

from abc import ABC, abstractmethod

from ..domain.models import PaperMetadata


class ScholarlyIndex(ABC):
    """Looks up a cited paper's public metadata (title, abstract) so summaries are grounded on real text."""

    @abstractmethod
    def lookup(self, *, title: str, arxiv_id: str = "", doi: str = "", year: str = "") -> PaperMetadata | None: ...
