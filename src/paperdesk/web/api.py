from __future__ import annotations

from urllib.parse import unquote

from .. import APP_ID, __version__
from ..app import Application
from ..domain.errors import InvalidInput
from ..domain.models import AssistRequest, AssistTask
from .http import Request, Response, Router

MAX_UPLOAD = 210 * 1024 * 1024


class ApiController:
    """Translates HTTP into service calls. No business rules here."""

    def __init__(self, app: Application) -> None:
        self.app = app

    def register(self, router: Router) -> None:
        routes = [
            ("GET", "/api/health", self.health),
            ("GET", "/api/library", self.library),
            ("GET", "/api/search", self.search),
            ("POST", "/api/documents", self.upload),
            ("GET", "/api/documents/{doc_id}", self.document),
            ("PATCH", "/api/documents/{doc_id}", self.update_document),
            ("DELETE", "/api/documents/{doc_id}", self.delete_document),
            ("GET", "/api/documents/{doc_id}/file", self.document_file),
            ("POST", "/api/documents/{doc_id}/open", self.open_document),
            ("PUT", "/api/documents/{doc_id}/text", self.save_text),
            ("POST", "/api/folders", self.create_folder),
            ("PATCH", "/api/folders/{folder_id}", self.update_folder),
            ("DELETE", "/api/folders/{folder_id}", self.delete_folder),
            ("POST", "/api/reading-list", self.add_reading),
            ("PATCH", "/api/reading-list/{item_id}", self.update_reading),
            ("DELETE", "/api/reading-list/{item_id}", self.delete_reading),
            ("POST", "/api/reading-list/{item_id}/arxiv", self.reading_from_arxiv),
            ("POST", "/api/reading-list/{item_id}/pdf", self.reading_attach_pdf),
            ("POST", "/api/assist", self.assist),
            ("GET", "/api/settings", self.settings),
            ("PUT", "/api/settings", self.update_settings),
            ("PUT", "/api/providers/{provider_id}", self.update_provider),
            ("POST", "/api/providers/{provider_id}/test", self.test_provider),
        ]
        for method, pattern, handler in routes:
            router.add(method, pattern, handler)

    def health(self, request: Request) -> Response:
        return Response.json({"app": APP_ID, "version": __version__})

    def library(self, request: Request) -> Response:
        return Response.json({
            "folders": [folder.to_dict() for folder in self.app.folders.list()],
            "documents": [doc.to_dict() for doc in self.app.library.list()],
            "reading_list": [item.to_dict() for item in self.app.reading.list()],
        })

    def search(self, request: Request) -> Response:
        return Response.json({"results": self.app.library.search(request.query.get("q", ""), 30)})

    def upload(self, request: Request) -> Response:
        if len(request.body) > MAX_UPLOAD:
            raise InvalidInput("파일이 너무 커요.")
        filename = unquote(request.headers.get("X-Filename", "paper.pdf"))
        document, created = self.app.library.import_pdf(filename, request.body, request.query.get("folder") or None)
        return Response.json({"document": document.to_dict(), "created": created}, 201 if created else 200)

    def document(self, request: Request) -> Response:
        return Response.json({"document": self.app.library.get(request.params["doc_id"]).to_dict()})

    def update_document(self, request: Request) -> Response:
        doc_id, data = request.params["doc_id"], request.json()
        document = self.app.library.get(doc_id)
        if "title" in data:
            document = self.app.library.rename(doc_id, data["title"])
        if "folder_id" in data:
            document = self.app.library.move(doc_id, data["folder_id"])
        return Response.json({"document": document.to_dict()})

    def delete_document(self, request: Request) -> Response:
        self.app.library.delete(request.params["doc_id"])
        return Response.json({"ok": True})

    def document_file(self, request: Request) -> Response:
        path = self.app.library.pdf_path(request.params["doc_id"])
        return Response.send_file(path, "application/pdf", {"Cache-Control": "private, max-age=3600"})

    def open_document(self, request: Request) -> Response:
        return Response.json({"document": self.app.library.mark_opened(request.params["doc_id"]).to_dict()})

    def save_text(self, request: Request) -> Response:
        pages = request.json().get("pages")
        if not isinstance(pages, list):
            raise InvalidInput("pages 목록이 필요해요.")
        return Response.json({"document": self.app.library.save_text(request.params["doc_id"], pages).to_dict()})

    def create_folder(self, request: Request) -> Response:
        data = request.json()
        folder = self.app.folders.create(data.get("name", ""), data.get("parent_id"))
        return Response.json({"folder": folder.to_dict()}, 201)

    def update_folder(self, request: Request) -> Response:
        folder_id, data = request.params["folder_id"], request.json()
        folder = self.app.folders.get(folder_id)
        if "name" in data:
            folder = self.app.folders.rename(folder_id, data["name"])
        if "parent_id" in data:
            folder = self.app.folders.move(folder_id, data["parent_id"])
        return Response.json({"folder": folder.to_dict()})

    def delete_folder(self, request: Request) -> Response:
        self.app.folders.delete(request.params["folder_id"])
        return Response.json({"ok": True})

    def add_reading(self, request: Request) -> Response:
        data = request.json()
        item, created = self.app.reading.add(str(data.get("citation", "")), source_doc_id=data.get("source_doc_id") or None,
                                             title=str(data.get("title") or ""))
        return Response.json({"item": item.to_dict(), "created": created}, 201 if created else 200)

    def update_reading(self, request: Request) -> Response:
        data = request.json()
        item = self.app.reading.update(request.params["item_id"], title=data.get("title"), note=data.get("note"))
        return Response.json({"item": item.to_dict()})

    def delete_reading(self, request: Request) -> Response:
        self.app.reading.remove(request.params["item_id"])
        return Response.json({"ok": True})

    @staticmethod
    def _folder_choice(data: dict) -> str | None:
        # absent -> folder of the citing paper; null -> unfiled; id -> that folder
        if "folder_id" not in data:
            return None
        return data["folder_id"] or ""

    def reading_from_arxiv(self, request: Request) -> Response:
        item, document = self.app.reading.fetch_arxiv_pdf(request.params["item_id"], self._folder_choice(request.json()))
        return Response.json({"item": item.to_dict(), "document": document.to_dict()})

    def reading_attach_pdf(self, request: Request) -> Response:
        if len(request.body) > MAX_UPLOAD:
            raise InvalidInput("파일이 너무 커요.")
        query = request.query
        folder = (query.get("folder") or "") if "folder" in query else None
        item, document = self.app.reading.attach_pdf(request.params["item_id"], unquote(request.headers.get("X-Filename", "paper.pdf")),
                                                     request.body, folder)
        return Response.json({"item": item.to_dict(), "document": document.to_dict()})

    def assist(self, request: Request) -> Response:
        data = request.json()
        try:
            task = AssistTask(data.get("task", ""))
        except ValueError:
            raise InvalidInput("알 수 없는 작업이에요.") from None
        settings = self.app.settings.load()
        completion = self.app.assistant.run(AssistRequest(
            task=task,
            text=str(data.get("text", "")),
            question=str(data.get("question", "")),
            context=str(data.get("context", ""))[:8000],
            target_language=settings.target_language,
        ))
        return Response.json(completion.to_dict())

    def settings(self, request: Request) -> Response:
        return Response.json(self.app.settings.view())

    def update_settings(self, request: Request) -> Response:
        data = request.json()
        self.app.settings.update_general(provider=data.get("provider"), target_language=data.get("target_language"))
        return Response.json(self.app.settings.view())

    def update_provider(self, request: Request) -> Response:
        values = request.json().get("values")
        if not isinstance(values, dict):
            raise InvalidInput("values 객체가 필요해요.")
        return Response.json({"provider": self.app.settings.update_provider(request.params["provider_id"], values)})

    def test_provider(self, request: Request) -> Response:
        return Response.json(self.app.settings.test_provider(request.params["provider_id"]))

