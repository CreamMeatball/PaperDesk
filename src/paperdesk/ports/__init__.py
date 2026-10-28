"""Interfaces the services depend on. Swap an implementation without touching the services."""

from .ai import AIProvider, CommandResult, CommandRunner, HttpClient, OptionField, ProviderContext
from .downloads import FileDownloader
from .repositories import CompletionCache, DocumentRepository, FolderRepository, PageTextRepository, ReadingListRepository
from .secrets import SecretStore
from .settings import Settings, SettingsStore
from .storage import BlobStore

__all__ = [
    "AIProvider", "BlobStore", "CommandResult", "CommandRunner", "CompletionCache", "DocumentRepository",
    "FileDownloader", "FolderRepository", "HttpClient", "OptionField", "PageTextRepository", "ProviderContext", "ReadingListRepository", "SecretStore",
    "Settings", "SettingsStore",
]

