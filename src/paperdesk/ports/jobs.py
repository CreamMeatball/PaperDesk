from abc import ABC, abstractmethod


class TranslationJobRepository(ABC):
    @abstractmethod
    def add(self, job: dict) -> dict: ...

    @abstractmethod
    def get(self, job_id: str) -> dict | None: ...

    @abstractmethod
    def list(self, doc_id: str | None = None) -> list[dict]: ...

    @abstractmethod
    def transition(self, job_id: str, before: tuple[str, ...], state: str, **changes) -> bool: ...
