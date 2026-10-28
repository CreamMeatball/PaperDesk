from __future__ import annotations

from urllib.parse import unquote

from .. import APP_ID, __version__
from ..app import Application
from ..domain.errors import InvalidInput, NotFound
import base64
import re

from ..domain.models import AssistRequest, AssistTask, ImageInput
from .http import Request, Response, Router
from ..i18n import _, translate

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
            ("GET", "/api/documents/{doc_id}/annotations", self.annotations),
            ("GET", "/api/documents/{doc_id}/conversation", self.conversation),
            ("PUT", "/api/documents/{doc_id}/conversation", self.save_conversation),
            ("GET", "/api/preferences", self.preferences),
            ("PATCH", "/api/preferences", self.update_preferences),
            ("POST", "/api/state/import", self.import_legacy_state),
            ("POST", "/api/documents/{doc_id}/annotations", self.add_annotation),
            ("PATCH", "/api/annotations/{annotation_id}", self.update_annotation),
            ("DELETE", "/api/annotations/{annotation_id}", self.delete_annotation),
            ("GET", "/api/documents/{doc_id}/translations", self.translations),
            ("POST", "/api/documents/{doc_id}/translations", self.translate_blocks),
            ("POST", "/api/references/explain", self.explain_reference),
            ("POST", "/api/reading-list/{item_id}/find-arxiv", self.reading_find_arxiv),
            ("GET", "/api/settings", self.settings),
            ("PUT", "/api/settings", self.update_settings),
            ("PUT", "/api/providers/{provider_id}", self.update_provider),
            ("POST", "/api/providers/{provider_id}/test", self.test_provider),
        ]
        for method, pattern, handler in routes:
            router.add(method, pattern, handler)

    def health(self, request: Request) -> Response:
        return Response.json({"app": APP_ID, "version": __version__})

    def conversation(self, request: Request) -> Response:
        return Response.json({"turns": self.app.conversations.get(request.params["doc_id"])})

    def save_conversation(self, request: Request) -> Response:
        turns = self.app.conversations.save(request.params["doc_id"], request.json().get("turns"))
        return Response.json({"saved": len(turns)})

    def preferences(self, request: Request) -> Response:
        return Response.json({"preferences": self.app.preferences.all()})

    def update_preferences(self, request: Request) -> Response:
        return Response.json({"preferences": self.app.preferences.update(request.json())})

    def import_legacy_state(self, request: Request) -> Response:
        data = request.json()
        conversations = data.get("conversations", {})
        if not isinstance(conversations, dict):
            raise InvalidInput(_("요청 형식이 올바르지 않아요."))
        imported = []
        for doc_id, turns in conversations.items():
            try:
                self.app.conversations.save(doc_id, turns, only_missing=True)
                imported.append(doc_id)
            except NotFound:
                continue  # retain legacy data for papers that are not in this library
        prefs = self.app.preferences.update(data.get("preferences", {}), only_missing=True)
        return Response.json({"preferences": prefs, "documents": imported})

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
            raise InvalidInput(_("파일이 너무 커요."))
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
            raise InvalidInput(_("pages 목록이 필요해요."))
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
            raise InvalidInput(_("파일이 너무 커요."))
        query = request.query
        folder = (query.get("folder") or "") if "folder" in query else None
        item, document = self.app.reading.attach_pdf(request.params["item_id"], unquote(request.headers.get("X-Filename", "paper.pdf")),
                                                     request.body, folder)
        return Response.json({"item": item.to_dict(), "document": document.to_dict()})

    @staticmethod
    def _images(raw) -> tuple[ImageInput, ...]:
        if not raw:
            return ()
        if not isinstance(raw, list) or len(raw) > 2:
            raise InvalidInput(_("이미지는 두 장까지 보낼 수 있어요."))
        images = []
        for url in raw:
            found = re.fullmatch(r"data:(image/(?:png|jpeg));base64,([A-Za-z0-9+/=]+)", str(url))
            if not found:
                raise InvalidInput(_("이미지 형식이 올바르지 않아요."))
            data = base64.b64decode(found.group(2))
            if not (data.startswith(b"\x89PNG") or data.startswith(b"\xff\xd8")):
                raise InvalidInput(_("이미지 형식이 올바르지 않아요."))
            images.append(ImageInput(found.group(1), data))
        return tuple(images)

    def assist(self, request: Request) -> Response:
        data = request.json()
        try:
            task = AssistTask(data.get("task", ""))
        except ValueError:
            raise InvalidInput(_("알 수 없는 작업이에요.")) from None
        if task in (AssistTask.TRANSLATE_BLOCKS, AssistTask.REFERENCE):
            raise InvalidInput(_("이 작업은 전용 주소를 쓰세요."))
        settings = self.app.settings.load()
        completion = self.app.assistant.run(AssistRequest(
            task=task,
            text=str(data.get("text", "")),
            question=str(data.get("question", ""))[:4000],
            context=str(data.get("context", ""))[:12000],
            target_language=settings.target_language,
            title=str(data.get("title", ""))[:300],
            images=self._images(data.get("images")),
        ), cache_only=bool(data.get("cache_only")))
        return Response.json(completion.to_dict() if completion else None)

    def annotations(self, request: Request) -> Response:
        return Response.json({"annotations": [a.to_dict() for a in self.app.annotations.list(request.params["doc_id"])]})

    def add_annotation(self, request: Request) -> Response:
        data = request.json()
        page = data.get("page")
        annotation = self.app.annotations.add(request.params["doc_id"], page=page if isinstance(page, int) else -1,
                                              kind=str(data.get("kind", "highlight")), color=str(data.get("color", "yellow")),
                                              text=str(data.get("text", "")), rects=data.get("rects"), note=str(data.get("note", "")))
        return Response.json({"annotation": annotation.to_dict()}, 201)

    def update_annotation(self, request: Request) -> Response:
        data = request.json()
        annotation = self.app.annotations.update(request.params["annotation_id"], color=data.get("color"), note=data.get("note"))
        return Response.json({"annotation": annotation.to_dict()})

    def delete_annotation(self, request: Request) -> Response:
        self.app.annotations.delete(request.params["annotation_id"])
        return Response.json({"ok": True})

    def translations(self, request: Request) -> Response:
        return Response.json(self.app.translations.list(request.params["doc_id"]))

    def translate_blocks(self, request: Request) -> Response:
        data = request.json()
        blocks = self.app.translations.parse_blocks(data.get("blocks"))
        return Response.json(self.app.translations.translate(request.params["doc_id"], blocks, title=str(data.get("title", ""))[:300],
                                                             section=str(data.get("section", ""))[:200], terms=str(data.get("terms", ""))[:600]))

    def explain_reference(self, request: Request) -> Response:
        data = request.json()
        return Response.json(self.app.reference_notes.explain(str(data.get("citation", "")), language=self.app.settings.load().target_language,
                                                              cache_only=bool(data.get("cache_only"))))

    def reading_find_arxiv(self, request: Request) -> Response:
        return Response.json({"item": self.app.reading.find_arxiv(request.params["item_id"]).to_dict()})

    @staticmethod
    def _localize_provider(provider: dict, lang: str) -> dict:
        out = {**provider, **{k: translate(provider[k], lang) for k in ("label", "description", "detail")}}
        out["options"] = [{**o, **{k: translate(o[k], lang) for k in ("label", "placeholder", "help")}} for o in provider["options"]]
        return out

    def _settings_view(self, request: Request) -> dict:
        view = self.app.settings.view()
        view["providers"] = [self._localize_provider(p, request.lang) for p in view["providers"]]
        return view

    def settings(self, request: Request) -> Response:
        return Response.json(self._settings_view(request))

    def update_settings(self, request: Request) -> Response:
        data = request.json()
        self.app.settings.update_general(provider=data.get("provider"), target_language=data.get("target_language"),
                                         ui_language=data.get("ui_language"))
        return Response.json(self._settings_view(request))

    def update_provider(self, request: Request) -> Response:
        values = request.json().get("values")
        if not isinstance(values, dict):
            raise InvalidInput(_("values 객체가 필요해요."))
        provider = self.app.settings.update_provider(request.params["provider_id"], values)
        return Response.json({"provider": self._localize_provider(provider, request.lang)})

    def test_provider(self, request: Request) -> Response:
        result = self.app.settings.test_provider(request.params["provider_id"])
        if not result.get("ok"):
            result["message"] = translate(result["message"], request.lang)
        return Response.json(result)
