from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class Settings:
    provider: str = ""  # empty until the user picks an AI on the settings page
    target_language: str = "English"
    provider_options: dict[str, dict[str, str]] = field(default_factory=dict)

    def options_for(self, provider_id: str) -> dict[str, str]:
        return dict(self.provider_options.get(provider_id, {}))

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "target_language": self.target_language,
            "provider_options": {k: dict(v) for k, v in self.provider_options.items()},
        }

    @classmethod
    def from_dict(cls, data: dict, *, defaults: "Settings | None" = None) -> "Settings":
        base = defaults or cls()
        options = data.get("provider_options") or {}
        return cls(
            provider=str(data.get("provider", base.provider) or ""),
            target_language=str(data.get("target_language") or base.target_language),
            provider_options={
                str(pid): {str(k): str(v) for k, v in (values or {}).items()}
                for pid, values in options.items()
                if isinstance(values, dict)
            },
        )


class SettingsStore(ABC):
    @abstractmethod
    def load(self) -> Settings: ...

    @abstractmethod
    def save(self, settings: Settings) -> None: ...

