"""Composition root: the only place that chooses concrete implementations."""

from __future__ import annotations

from dataclasses import dataclass

from .config import AppPaths
from .infrastructure.blobs import FileBlobStore
from .infrastructure.settings_store import JsonSettingsStore
from .infrastructure.sqlite import (Database, SqliteCompletionCache, SqliteDocumentRepository, SqliteFolderRepository,
                                    SqlitePageTextRepository)
from .platforms import Platform, current_platform
from .ports.ai import CommandRunner, HttpClient
from .ports.secrets import SecretStore
from .ports.settings import Settings, SettingsStore
from .providers.registry import ProviderRegistry, default_registry
from .providers.transport import SubprocessRunner, UrllibHttpClient
from .services.assistant import AssistantService
from .services.library import FolderService, LibraryService
from .services.prompts import PromptBuilder
from .services.settings import SettingsService


@dataclass
class Application:
    paths: AppPaths
    platform: Platform
    library: LibraryService
    folders: FolderService
    assistant: AssistantService
    settings: SettingsService

    @classmethod
    def build(cls, paths: AppPaths | None = None, *, secrets: SecretStore | None = None,
              settings_store: SettingsStore | None = None, registry: ProviderRegistry | None = None,
              runner: CommandRunner | None = None, http: HttpClient | None = None,
              platform: Platform | None = None) -> "Application":
        platform = platform or current_platform()
        paths = (paths or AppPaths.default()).ensure()
        database = Database(paths.database)
        documents = SqliteDocumentRepository(database)
        folders = FolderService(SqliteFolderRepository(database), documents)
        library = LibraryService(documents, FileBlobStore(paths.blobs), SqlitePageTextRepository(database), folders)
        settings = SettingsService(
            store=settings_store or JsonSettingsStore(paths.settings_file, Settings(target_language=platform.preferred_language())),
            secrets=secrets or platform.secret_store(paths.root),
            registry=registry or default_registry(),
            runner=runner or SubprocessRunner(),
            http=http or UrllibHttpClient(),
        )
        assistant = AssistantService(active_provider=settings.active_provider, prompts=PromptBuilder(),
                                     cache=SqliteCompletionCache(database))
        return cls(paths, platform, library, folders, assistant, settings)

