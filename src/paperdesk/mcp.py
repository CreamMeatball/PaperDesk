"""MCP server over stdio so the user's Claude Desktop or Codex can read papers stored in PaperDesk.

This is the officially supported direction for desktop assistants: they call our tools; we never touch their logins.
"""

from __future__ import annotations

import json
import sys
from abc import ABC, abstractmethod
from typing import IO, Any, ClassVar

from . import APP_ID, __version__
from .app import Application
from .domain.errors import ReaderError

SUPPORTED_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26", "2024-11-05")
MAX_CHARS = 60_000


class McpTool(ABC):
    name: ClassVar[str]
    description: ClassVar[str]
    input_schema: ClassVar[dict]

    def __init__(self, app: Application) -> None:
        self.app = app

    @abstractmethod
    def call(self, arguments: dict) -> str: ...

    def spec(self) -> dict:
        return {"name": self.name, "description": self.description, "inputSchema": self.input_schema}


class ListPapersTool(McpTool):
    name = "list_papers"
    description = "List papers in the user's PaperDesk library with their folder path and whether text is available."
    input_schema = {"type": "object", "properties": {"folder": {"type": "string", "description": "Optional folder name filter"}}}

    def call(self, arguments: dict) -> str:
        folders = {f.id: f for f in self.app.folders.list()}

        def path(folder_id: str | None) -> str:
            names = []
            while folder_id and folder_id in folders:
                names.append(folders[folder_id].name)
                folder_id = folders[folder_id].parent_id
            return " / ".join(reversed(names)) or "(unfiled)"

        wanted = str(arguments.get("folder") or "").casefold()
        rows = []
        for doc in self.app.library.list():
            where = path(doc.folder_id)
            if wanted and wanted not in where.casefold():
                continue
            rows.append({"id": doc.id, "title": doc.title, "folder": where, "pages": doc.page_count,
                         "text_available": doc.text_pages > 0})
        return json.dumps(rows, ensure_ascii=False, indent=1)


class ReadPaperTool(McpTool):
    name = "read_paper"
    description = "Read the extracted text of a paper by id, optionally for a page range (1-based, inclusive)."
    input_schema = {
        "type": "object",
        "properties": {"id": {"type": "string"}, "first_page": {"type": "integer", "minimum": 1},
                       "last_page": {"type": "integer", "minimum": 1}},
        "required": ["id"],
    }

    def call(self, arguments: dict) -> str:
        doc = self.app.library.get(str(arguments.get("id", "")))
        if doc.text_pages == 0:
            return f"'{doc.title}' has no extracted text yet. Ask the user to open it once in PaperDesk."
        first = int(arguments.get("first_page") or 1)
        last = int(arguments.get("last_page") or doc.text_pages)
        parts, size = [f"# {doc.title}"], 0
        for number, text in self.app.library.read_text(doc.id, first, last):
            chunk = f"\n\n[page {number}]\n{text}"
            if size + len(chunk) > MAX_CHARS:
                parts.append(f"\n\n[truncated at page {number}; request a later page range]")
                break
            parts.append(chunk)
            size += len(chunk)
        return "".join(parts)


class SearchPapersTool(McpTool):
    name = "search_papers"
    description = "Full-text search across the user's papers. Returns paper id, page and a snippet."
    input_schema = {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}

    def call(self, arguments: dict) -> str:
        return json.dumps(self.app.library.search(str(arguments.get("query", "")), 20), ensure_ascii=False, indent=1)


class ListReadingListTool(McpTool):
    name = "list_reading_list"
    description = "List papers the user saved to read later (title, authors, year, arXiv id/DOI, and whether the PDF is already in the library)."
    input_schema = {"type": "object", "properties": {}}

    def call(self, arguments: dict) -> str:
        keys = ("title", "authors", "year", "arxiv_id", "doi", "in_library", "note")
        return json.dumps([{k: item.to_dict()[k] for k in keys} for item in self.app.reading.list()], ensure_ascii=False, indent=1)


class StdioMcpServer:
    def __init__(self, tools: list[McpTool], *, stdin: IO[str] | None = None, stdout: IO[str] | None = None) -> None:
        self.tools = {tool.name: tool for tool in tools}
        self.stdin = stdin or sys.stdin
        self.stdout = stdout or sys.stdout

    @classmethod
    def for_app(cls, app: Application, **streams: Any) -> "StdioMcpServer":
        return cls([ListPapersTool(app), ReadPaperTool(app), SearchPapersTool(app), ListReadingListTool(app)], **streams)

    def serve(self) -> None:
        for line in self.stdin:
            if not line.strip():
                continue
            try:
                message = json.loads(line)
            except ValueError:
                self._write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
                continue
            reply = self.handle(message)
            if reply is not None:
                self._write(reply)

    def handle(self, message: dict) -> dict | None:
        method, ident = message.get("method"), message.get("id")
        if ident is None:  # notification (e.g. notifications/initialized)
            return None
        params = message.get("params") or {}
        try:
            if method == "initialize":
                requested = params.get("protocolVersion")
                result = {
                    "protocolVersion": requested if requested in SUPPORTED_VERSIONS else SUPPORTED_VERSIONS[0],
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": APP_ID, "version": __version__},
                }
            elif method == "ping":
                result = {}
            elif method == "tools/list":
                result = {"tools": [tool.spec() for tool in self.tools.values()]}
            elif method == "tools/call":
                tool = self.tools.get(params.get("name", ""))
                if tool is None:
                    return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32602, "message": "Unknown tool"}}
                try:
                    result = {"content": [{"type": "text", "text": tool.call(params.get("arguments") or {})}]}
                except (ReaderError, ValueError) as error:
                    result = {"content": [{"type": "text", "text": str(error)}], "isError": True}
            else:
                return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32601, "message": "Method not found"}}
        except Exception as error:  # never crash the host app's MCP connection
            return {"jsonrpc": "2.0", "id": ident, "error": {"code": -32603, "message": str(error)}}
        return {"jsonrpc": "2.0", "id": ident, "result": result}

    def _write(self, message: dict) -> None:
        self.stdout.write(json.dumps(message, ensure_ascii=False) + "\n")
        self.stdout.flush()

