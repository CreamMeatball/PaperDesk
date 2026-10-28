"""Pull title / authors / year / identifiers out of a free-form bibliography entry.

Heuristic by nature: covers numeric ([12] ...), APA (Surname, A. (2020). Title.), natbib/ACL (Authors. 2020. Title.)
and NeurIPS/ICLR style (Authors. Title. In Venue, 2017.). The user can always rename the title afterwards.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_LEADING_MARK = re.compile(r"^\s*(?:\[\s*\d{1,4}\s*\]|\(\s*\d{1,4}\s*\)|\d{1,4}\.(?=\s))\s*")
_ARXIV = re.compile(r"(?:arxiv(?:\.org/(?:abs|pdf)/|\s*(?:preprint)?\s*(?:arxiv)?\s*:?\s*))(\d{4}\.\d{4,5})(?:v\d+)?", re.I)
_ARXIV_BARE = re.compile(r"\babs/(\d{4}\.\d{4,5})\b")
_DOI = re.compile(r"\b(10\.\d{4,9}/[^\s\"<>]+)", re.I)
_URL = re.compile(r"https?://[^\s<>\"]+")
_YEAR = re.compile(r"\b((?:19[5-9]\d|20[0-4]\d)[a-z]?)\b")
_QUOTED = re.compile(r"[“\"]([^”\"]{8,300})[”\"]")
_NOT_SENTENCE_END = {"vs", "eg", "ie", "etc", "jr", "sr", "dr", "st", "proc", "conf", "int", "vol", "no", "pp"}


@dataclass(frozen=True)
class ParsedReference:
    title: str
    authors: str = ""
    year: str = ""
    arxiv_id: str = ""
    doi: str = ""
    url: str = ""


def clean_citation(text: str) -> str:
    return " ".join(str(text or "").replace("\u00ad", "").split())


def _segments(text: str) -> list[str]:
    """Split on '. ' that ends a sentence, not an initial (A.) or an abbreviation. 'et al.' ends the author list."""
    parts, start = [], 0
    for match in re.finditer(r"\.\s+", text):
        before = text[start:match.start()]
        word = re.split(r"[\s,(]", before)[-1] if before else ""
        bare = word.strip(".").lower()
        if len(bare) <= 1 or bare in _NOT_SENTENCE_END or re.fullmatch(r"(?:[A-Z]\.?-?)+", word):
            continue
        parts.append(text[start:match.start()].strip())
        start = match.end()
    tail = text[start:].strip().rstrip(".")
    if tail:
        parts.append(tail)
    return [p for p in parts if p]


def _strip_title(value: str) -> str:
    value = re.sub(r"^\(?\s*(?:19|20)\d{2}[a-z]?\s*\)?\s*[.,:]?\s*", "", value).strip()
    value = re.sub(r"\s*\[[^\]]*\]\s*$", "", value)
    value = re.sub(r",?\s*\(?(?:19|20)\d{2}[a-z]?\)?$", "", value)  # "Qwen2.5-vl technical report, 2025"
    return value.strip(" .,;:")


def _looks_like_venue(value: str) -> bool:
    if _YEAR.search(value) and len(value.split()) <= 3:  # "NeurIPS 2017"
        return True
    return bool(re.match(r"^(in|proceedings|proc\.|advances in|arxiv|journal|transactions|ieee|acm|conference|"
                         r"workshop|preprint|technical report|corr|openreview)\b", value, re.I))


class ReferenceParser:
    def parse(self, raw: str) -> ParsedReference:
        text = _LEADING_MARK.sub("", clean_citation(raw))
        arxiv = _ARXIV.search(text) or _ARXIV_BARE.search(text)
        doi = _DOI.search(text)
        url = _URL.search(text)
        scrubbed = _URL.sub(" ", _DOI.sub(" ", _ARXIV_BARE.sub(" ", _ARXIV.sub(" ", text))))
        year = _YEAR.search(scrubbed)  # identifiers like arXiv:2006.11239 must not read as a year
        title, authors = self._title_and_authors(text)
        return ParsedReference(
            title=title[:300],
            authors=authors[:300],
            year=year.group(1) if year else "",
            arxiv_id=arxiv.group(1) if arxiv else "",
            doi=doi.group(1).rstrip(".,;)") if doi else "",
            url=url.group(0).rstrip(".,;)") if url else "",
        )

    def _title_and_authors(self, text: str) -> tuple[str, str]:
        quoted = _QUOTED.search(text)
        if quoted:  # IEEE: A. Author, “Title,” in ...
            return quoted.group(1).strip(" ,."), text[:quoted.start()].strip(" ,")
        apa = re.match(r"^(.{3,400}?)\s*\(\s*((?:19|20)\d{2}[a-z]?|n\.d\.)\s*\)\s*\.?\s*(.+)$", text)
        if apa:  # APA: Authors (2020). Title. Venue
            rest = _segments(apa.group(3))
            if rest:
                return _strip_title(rest[0]), apa.group(1).strip(" ,.")
        parts = _segments(text)
        if len(parts) >= 3 and re.fullmatch(r"\(?(?:19|20)\d{2}[a-z]?\)?", parts[1]):
            return _strip_title(parts[2]), parts[0]  # ACL: Authors. 2020. Title. Venue
        if len(parts) >= 2:
            candidate = _strip_title(parts[1])
            if candidate and not _looks_like_venue(candidate) and len(candidate.split()) >= 2:
                return candidate, parts[0]
        candidates = [_strip_title(p) for p in parts[1:] if not _looks_like_venue(p)] or [text]
        return max(candidates, key=len)[:300], parts[0] if parts else ""

