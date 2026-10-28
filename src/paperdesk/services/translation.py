from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Callable

from ..domain.errors import InvalidInput
from ..domain.models import AssistRequest, AssistTask, BlockTranslation, utcnow
from ..ports.repositories import TranslationRepository
from .assistant import AssistantService
from .library import LibraryService

MAX_BLOCKS = 16
MAX_BATCH_CHARS = 9000
_KEY = re.compile(r"^[0-9]{1,4}:[0-9a-z]{4,16}$")


@dataclass(frozen=True)
class BlockInput:
    key: str          # "<page>:<hash of normalized text>", computed by the viewer
    sentences: tuple[str, ...]

    @property
    def text(self) -> str:
        return " ".join(self.sentences)

    @property
    def source_hash(self) -> str:
        return hashlib.sha256(self.text.encode()).hexdigest()[:24]


def _extract_json(raw: str) -> dict | None:
    text = raw.strip()
    fence = re.search(r"\x60\x60\x60(?:json)?\s*(\{.*\})\s*\x60\x60\x60", text, re.S)
    if fence:
        text = fence.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        data = json.loads(text[start:end + 1])
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


class TranslationService:
    """Body translation stored per document block and language, aligned sentence by sentence when the model complies."""

    def __init__(self, repository: TranslationRepository, assistant: AssistantService, library: LibraryService, *,
                 language: Callable[[], str], clock: Callable[[], str] = utcnow) -> None:
        self._repository = repository
        self._assistant = assistant
        self._library = library
        self._language = language
        self._clock = clock

    def list(self, doc_id: str) -> dict:
        self._library.get(doc_id)
        language = self._language()
        return {"language": language, "blocks": {t.block_key: {**t.to_dict(), "hash": t.source_hash}
                                                 for t in self._repository.list(doc_id, language)}}

    @staticmethod
    def parse_blocks(raw: list) -> list[BlockInput]:
        if not isinstance(raw, list) or not raw:
            raise InvalidInput("번역할 문단이 없어요.")
        if len(raw) > MAX_BLOCKS:
            raise InvalidInput(f"한 번에 {MAX_BLOCKS}문단까지 번역할 수 있어요.")
        blocks, total = [], 0
        for item in raw:
            key = str((item or {}).get("key", ""))
            sentences = item.get("sentences") if isinstance(item, dict) else None
            if not _KEY.match(key) or not isinstance(sentences, list) or not sentences:
                raise InvalidInput("문단 형식이 올바르지 않아요.")
            clean = tuple(" ".join(str(s).split()) for s in sentences if str(s).strip())[:200]
            total += sum(len(s) for s in clean)
            blocks.append(BlockInput(key, clean))
        if total > MAX_BATCH_CHARS * 2:
            raise InvalidInput("한 번에 보내기에는 글이 너무 길어요.")
        return blocks

    def translate(self, doc_id: str, blocks: list[BlockInput], *, title: str = "", section: str = "", terms: str = "") -> dict:
        document = self._library.get(doc_id)
        language = self._language()
        saved = {t.block_key: t for t in self._repository.list(doc_id, language)}
        todo = [b for b in blocks if not (b.key in saved and saved[b.key].source_hash == b.source_hash)]
        results = {b.key: saved[b.key] for b in blocks if b not in todo}
        if todo:
            payload = {"blocks": [{"id": str(i), "sentences": list(b.sentences)} for i, b in enumerate(todo)]}
            completion = self._assistant.run(AssistRequest(
                AssistTask.TRANSLATE_BLOCKS, json.dumps(payload, ensure_ascii=False), question=terms[:600],
                context=f"Section: {section}" if section else "", target_language=language, title=title or document.title))
            data = _extract_json(completion.text) or {}
            by_id = {str(b.get("id")): b for b in data.get("blocks", []) if isinstance(b, dict)}
            for index, block in enumerate(todo):
                got = by_id.get(str(index), {})
                sentences = [" ".join(str(s).split()) for s in got.get("sentences", []) if isinstance(s, (str, int, float))]
                if not sentences and len(todo) == 1 and not data:
                    sentences = [completion.text.strip()]  # model ignored JSON: keep the paragraph unaligned
                if not sentences:
                    continue
                aligned = len(sentences) == len(block.sentences)
                translation = BlockTranslation(doc_id, block.key, language, block.source_hash, " ".join(sentences),
                                               tuple(sentences) if aligned else None, completion.provider_id, completion.model,
                                               self._clock())
                self._repository.put(translation)
                results[block.key] = translation
        return {"language": language, "blocks": {k: {**t.to_dict(), "hash": t.source_hash} for k, t in results.items()},
                "missing": [b.key for b in blocks if b.key not in results]}

