from __future__ import annotations

import hashlib
import json
from typing import Callable

from ..domain.errors import InvalidInput, ProviderUnavailable
from ..domain.models import AssistRequest, Completion
from ..ports.ai import AIProvider
from ..ports.repositories import CompletionCache
from .prompts import PROMPT_VERSION, PromptBuilder

MAX_TEXT = 60_000


class AssistantService:
    """Runs reading tasks on whichever provider is active, caching identical requests locally."""

    def __init__(self, *, active_provider: Callable[[], AIProvider | None], prompts: PromptBuilder, cache: CompletionCache) -> None:
        self._active_provider = active_provider
        self._prompts = prompts
        self._cache = cache

    def run(self, request: AssistRequest) -> Completion:
        if not request.text.strip():
            raise InvalidInput("내용이 비어 있어요.")
        if len(request.text) + len(request.context) > MAX_TEXT:
            raise InvalidInput("한 번에 보내기에는 글이 너무 길어요. 범위를 줄여 주세요.")
        provider = self._active_provider()
        if provider is None:
            raise ProviderUnavailable("AI가 연결되지 않았어요. 설정에서 사용할 AI를 고르세요.")
        prompt = self._prompts.build(request)
        key = hashlib.sha256(json.dumps(
            [PROMPT_VERSION, provider.id, provider.model, prompt.system, prompt.user], ensure_ascii=False
        ).encode()).hexdigest()
        cached = self._cache.get(key)
        if cached is not None:
            return Completion(cached, provider.id, provider.model, cached=True)
        state = provider.status()
        if not state.available:
            raise ProviderUnavailable(state.detail)
        completion = provider.complete(prompt)
        self._cache.put(key, completion.text)
        return completion

