from __future__ import annotations

from typing import Iterable

from ..domain.errors import NotFound
from ..ports.ai import AIProvider, ProviderContext
from .anthropic_api import AnthropicApiProvider
from .claude_code import ClaudeCodeProvider
from .codex_cli import CodexCliProvider
from .openai_api import OpenAIApiProvider
from .openai_compatible import OllamaProvider, OpenAICompatibleServerProvider
from ..i18n import _


class ProviderRegistry:
    """Maps provider ids to classes. Order is the order shown on the settings page."""

    def __init__(self, classes: Iterable[type[AIProvider]] = ()) -> None:
        self._classes: dict[str, type[AIProvider]] = {}
        for cls in classes:
            self.register(cls)

    def register(self, cls: type[AIProvider]) -> type[AIProvider]:
        if cls.id in self._classes:
            raise ValueError(f"duplicate provider id: {cls.id}")
        self._classes[cls.id] = cls
        return cls

    def ids(self) -> list[str]:
        return list(self._classes)

    def has(self, provider_id: str) -> bool:
        return provider_id in self._classes

    def get_class(self, provider_id: str) -> type[AIProvider]:
        try:
            return self._classes[provider_id]
        except KeyError:
            raise NotFound(_("알 수 없는 AI 연결: {id}", id=provider_id)) from None

    def create(self, provider_id: str, context: ProviderContext) -> AIProvider:
        return self.get_class(provider_id)(context)


def default_registry() -> ProviderRegistry:
    return ProviderRegistry([
        CodexCliProvider,
        ClaudeCodeProvider,
        OpenAIApiProvider,
        AnthropicApiProvider,
        OllamaProvider,
        OpenAICompatibleServerProvider,
    ])

