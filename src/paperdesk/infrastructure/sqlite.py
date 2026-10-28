from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

from dataclasses import fields

from ..domain.models import Document, Folder, ReadingItem
from ..ports.repositories import CompletionCache, DocumentRepository, FolderRepository, PageTextRepository, ReadingListRepository

# Append-only. Each entry upgrades the schema by one version (tracked in PRAGMA user_version).
MIGRATIONS: tuple[str, ...] = (
    """
    CREATE TABLE folders (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL,
        parent_id TEXT REFERENCES folders(id) ON DELETE CASCADE,
        created_at TEXT NOT NULL
    );
    CREATE TABLE documents (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        filename TEXT NOT NULL,
        sha256 TEXT NOT NULL UNIQUE,
        size_bytes INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        folder_id TEXT REFERENCES folders(id) ON DELETE SET NULL,
        last_opened_at TEXT,
        page_count INTEGER NOT NULL DEFAULT 0,
        text_pages INTEGER NOT NULL DEFAULT 0
    );
    CREATE INDEX documents_folder ON documents(folder_id);
    CREATE TABLE page_texts (
        doc_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
        page INTEGER NOT NULL,
        text TEXT NOT NULL,
        PRIMARY KEY (doc_id, page)
    );
    CREATE TABLE completions (
        key TEXT PRIMARY KEY,
        text TEXT NOT NULL,
        created_at TEXT NOT NULL
    );
    """,
    """
    CREATE TABLE reading_items (
        id TEXT PRIMARY KEY,
        title TEXT NOT NULL,
        citation TEXT NOT NULL,
        created_at TEXT NOT NULL,
        authors TEXT NOT NULL DEFAULT '',
        year TEXT NOT NULL DEFAULT '',
        arxiv_id TEXT NOT NULL DEFAULT '',
        doi TEXT NOT NULL DEFAULT '',
        url TEXT NOT NULL DEFAULT '',
        source_doc_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
        document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
        note TEXT NOT NULL DEFAULT ''
    );
    """,
)


class Database:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._migrate()

    @contextmanager
    def connect(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _migrate(self) -> None:
        with self.connect() as db:
            db.execute("PRAGMA journal_mode = WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            for number, script in enumerate(MIGRATIONS[version:], start=version + 1):
                db.executescript(script)
                db.execute(f"PRAGMA user_version = {number}")


_DOC_COLUMNS = "id, title, filename, sha256, size_bytes, created_at, folder_id, last_opened_at, page_count, text_pages"


def _document(row: sqlite3.Row) -> Document:
    return Document(**{key: row[key] for key in row.keys()})


class SqliteDocumentRepository(DocumentRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    def add(self, document: Document) -> None:
        values = document.to_dict()
        with self._db.connect() as db:
            db.execute(f"INSERT INTO documents ({_DOC_COLUMNS}) VALUES ({', '.join(':' + c.strip() for c in _DOC_COLUMNS.split(','))})", values)

    def get(self, doc_id: str) -> Document | None:
        with self._db.connect() as db:
            row = db.execute(f"SELECT {_DOC_COLUMNS} FROM documents WHERE id = ?", (doc_id,)).fetchone()
        return _document(row) if row else None

    def find_by_sha256(self, digest: str) -> Document | None:
        with self._db.connect() as db:
            row = db.execute(f"SELECT {_DOC_COLUMNS} FROM documents WHERE sha256 = ?", (digest,)).fetchone()
        return _document(row) if row else None

    def list(self) -> list[Document]:
        with self._db.connect() as db:
            rows = db.execute(f"SELECT {_DOC_COLUMNS} FROM documents ORDER BY COALESCE(last_opened_at, created_at) DESC").fetchall()
        return [_document(row) for row in rows]

    def update(self, document: Document) -> None:
        values = document.to_dict()
        assignments = ", ".join(f"{c.strip()} = :{c.strip()}" for c in _DOC_COLUMNS.split(",")[1:])
        with self._db.connect() as db:
            db.execute(f"UPDATE documents SET {assignments} WHERE id = :id", values)

    def delete(self, doc_id: str) -> None:
        with self._db.connect() as db:
            db.execute("DELETE FROM documents WHERE id = ?", (doc_id,))

    def move_all(self, from_folder: str, to_folder: str | None) -> None:
        with self._db.connect() as db:
            db.execute("UPDATE documents SET folder_id = ? WHERE folder_id = ?", (to_folder, from_folder))


class SqliteFolderRepository(FolderRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    def add(self, folder: Folder) -> None:
        with self._db.connect() as db:
            db.execute("INSERT INTO folders (id, name, parent_id, created_at) VALUES (:id, :name, :parent_id, :created_at)", folder.to_dict())

    def get(self, folder_id: str) -> Folder | None:
        with self._db.connect() as db:
            row = db.execute("SELECT id, name, parent_id, created_at FROM folders WHERE id = ?", (folder_id,)).fetchone()
        return Folder(**dict(row)) if row else None

    def list(self) -> list[Folder]:
        with self._db.connect() as db:
            rows = db.execute("SELECT id, name, parent_id, created_at FROM folders ORDER BY name COLLATE NOCASE").fetchall()
        return [Folder(**dict(row)) for row in rows]

    def update(self, folder: Folder) -> None:
        with self._db.connect() as db:
            db.execute("UPDATE folders SET name = :name, parent_id = :parent_id WHERE id = :id", folder.to_dict())

    def delete(self, folder_id: str) -> None:
        with self._db.connect() as db:
            db.execute("DELETE FROM folders WHERE id = ?", (folder_id,))


_READING_COLUMNS = [f.name for f in fields(ReadingItem)]


class SqliteReadingListRepository(ReadingListRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    @staticmethod
    def _item(row: sqlite3.Row) -> ReadingItem:
        return ReadingItem(**{key: row[key] for key in _READING_COLUMNS})

    def add(self, item: ReadingItem) -> None:
        values = {key: getattr(item, key) for key in _READING_COLUMNS}
        with self._db.connect() as db:
            db.execute(f"INSERT INTO reading_items ({', '.join(_READING_COLUMNS)}) VALUES ({', '.join(':' + c for c in _READING_COLUMNS)})", values)

    def get(self, item_id: str) -> ReadingItem | None:
        with self._db.connect() as db:
            row = db.execute(f"SELECT {', '.join(_READING_COLUMNS)} FROM reading_items WHERE id = ?", (item_id,)).fetchone()
        return self._item(row) if row else None

    def list(self) -> list[ReadingItem]:
        with self._db.connect() as db:
            rows = db.execute(f"SELECT {', '.join(_READING_COLUMNS)} FROM reading_items ORDER BY created_at DESC").fetchall()
        return [self._item(row) for row in rows]

    def update(self, item: ReadingItem) -> None:
        values = {key: getattr(item, key) for key in _READING_COLUMNS}
        assignments = ", ".join(f"{c} = :{c}" for c in _READING_COLUMNS if c != "id")
        with self._db.connect() as db:
            db.execute(f"UPDATE reading_items SET {assignments} WHERE id = :id", values)

    def delete(self, item_id: str) -> None:
        with self._db.connect() as db:
            db.execute("DELETE FROM reading_items WHERE id = ?", (item_id,))


class SqlitePageTextRepository(PageTextRepository):
    def __init__(self, database: Database) -> None:
        self._db = database

    def replace(self, doc_id: str, pages: list[str]) -> None:
        with self._db.connect() as db:
            db.execute("DELETE FROM page_texts WHERE doc_id = ?", (doc_id,))
            db.executemany("INSERT INTO page_texts (doc_id, page, text) VALUES (?, ?, ?)",
                           [(doc_id, number, text) for number, text in enumerate(pages, start=1)])

    def read(self, doc_id: str, first: int, last: int) -> list[tuple[int, str]]:
        with self._db.connect() as db:
            rows = db.execute("SELECT page, text FROM page_texts WHERE doc_id = ? AND page BETWEEN ? AND ? ORDER BY page",
                              (doc_id, first, last)).fetchall()
        return [(row["page"], row["text"]) for row in rows]

    def search(self, query: str, limit: int) -> list[tuple[str, int, str]]:
        needle = query.strip()
        if not needle:
            return []
        escaped = needle.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        with self._db.connect() as db:
            rows = db.execute("SELECT doc_id, page, text FROM page_texts WHERE text LIKE ? ESCAPE '\\' ORDER BY doc_id, page LIMIT ?",
                              (f"%{escaped}%", limit)).fetchall()
        results = []
        for row in rows:
            text = row["text"]
            at = text.lower().find(needle.lower())
            start = max(0, at - 80)
            snippet = ("…" if start else "") + " ".join(text[start:at + len(needle) + 120].split()) + "…"
            results.append((row["doc_id"], row["page"], snippet))
        return results


class SqliteCompletionCache(CompletionCache):
    def __init__(self, database: Database) -> None:
        self._db = database

    def get(self, key: str) -> str | None:
        with self._db.connect() as db:
            row = db.execute("SELECT text FROM completions WHERE key = ?", (key,)).fetchone()
        return row["text"] if row else None

    def put(self, key: str, text: str) -> None:
        stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._db.connect() as db:
            db.execute("INSERT OR REPLACE INTO completions (key, text, created_at) VALUES (?, ?, ?)", (key, text, stamp))

