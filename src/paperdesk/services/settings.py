from __future__ import annotations

import time

from ..config import LANGUAGES
from ..domain.errors import InvalidInput
from ..domain.models import Prompt
from ..ports.ai import AIProvider, CommandRunner, HttpClient, ProviderContext
from ..ports.secrets import SecretStore
from ..ports.settings import Settings, SettingsStore
from ..providers.registry import ProviderRegistry


class SettingsService:
    """Owns user settings and builds provider instances from them."""

    def __init__(self, *, store: SettingsStore, secrets: SecretStore, registry: ProviderRegistry,
                 runner: CommandRunner, http: HttpClient) -> None:
        self._store = store
        self._secrets = secrets
        self._registry = registry
        self._runner = runner
        self._http = http

    def load(self) -> Settings:
        return self._store.load()

    def context_for(self, provider_id: str, settings: Settings | None = None) -> ProviderContext:
        current = settings or self._store.load()
        return ProviderContext(provider_id, current.options_for(provider_id), self._secrets, self._runner, self._http)

    def provider(self, provider_id: str) -> AIProvider:
        return self._registry.create(provider_id, self.context_for(provider_id))

    def active_provider(self) -> AIProvider | None:
        settings = self._store.load()
        if not settings.provider or not self._registry.has(settings.provider):
            return None
        return self._registry.create(settings.provider, self.context_for(settings.provider, settings))

    def view(self) -> dict:
        settings = self._store.load()
        return {
            "provider": settings.provider,
            "target_language": settings.target_language,
            "languages": sorted(set(LANGUAGES.values())),
            "providers": [self._registry.create(pid, self.context_for(pid, settings)).describe() for pid in self._registry.ids()],
        }

    def update_general(self, *, provider: str | None = None, target_language: str | None = None) -> Settings:
        settings = self._store.load()
        if provider is not None:
            if provider and not self._registry.has(provider):
                raise InvalidInput(f"알 수 없는 AI 연결: {provider}")
            settings.provider = provider
        if target_language is not None:
            language = " ".join(str(target_language).split())
            if not language or len(language) > 40:
                raise InvalidInput("번역 언어를 확인해 주세요.")
            settings.target_language = language
        self._store.save(settings)
        return settings

    def update_provider(self, provider_id: str, values: dict) -> dict:
        """values: {option_key: str | None}. For secrets, '' or None deletes; omitted keys stay unchanged."""
        cls = self._registry.get_class(provider_id)
        fields = {item.key: item for item in cls.options}
        settings = self._store.load()
        stored = settings.options_for(provider_id)
        context = self.context_for(provider_id, settings)
        for key, raw in values.items():
            if key not in fields:
                raise InvalidInput(f"알 수 없는 설정 항목: {key}")
            value = "" if raw is None else str(raw).strip()
            if len(value) > 4000:
                raise InvalidInput("값이 너무 길어요.")
            if fields[key].kind == "secret":
                if value:
                    self._secrets.set(context.secret_name(key), value)
                else:
                    self._secrets.delete(context.secret_name(key))
            elif value:
                stored[key] = value
            else:
                stored.pop(key, None)
        settings.provider_options[provider_id] = stored
        self._store.save(settings)
        return self.provider(provider_id).describe()

    def test_provider(self, provider_id: str) -> dict:
        provider = self.provider(provider_id)
        state = provider.status()
        if not state.available:
            return {"ok": False, "message": state.detail}
        started = time.monotonic()
        completion = provider.complete(Prompt("Reply with text only. Do not use tools.", "Reply with exactly: OK"))
        return {"ok": True, "message": completion.text.strip()[:200], "model": completion.model,
                "seconds": round(time.monotonic() - started, 1)}

