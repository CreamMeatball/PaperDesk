from __future__ import annotations

import os
import re
from pathlib import Path

from ..ports.storage import BlobStore

_KEY = re.compile(r"^[a-z0-9][a-z0-9_-]*(/[a-z0-9][a-z0-9_.-]*)*$")


class FileBlobStore(BlobStore):
    def __init__(self, root: Path) -> None:
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def path(self, key: str) -> Path:
        if not _KEY.match(key) or ".." in key:
            raise ValueError(f"invalid blob key: {key!r}")
        return self.root / key

    def put(self, key: str, data: bytes) -> None:
        target = self.path(key)
        target.parent.mkdir(parents=True, exist_ok=True)
        temporary = target.with_name(target.name + ".part")
        temporary.write_bytes(data)
        os.replace(temporary, target)

    def exists(self, key: str) -> bool:
        return self.path(key).is_file()

    def delete(self, key: str) -> None:
        self.path(key).unlink(missing_ok=True)

