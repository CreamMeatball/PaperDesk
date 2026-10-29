import importlib.util
import json
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from paperdesk.i18n import _, from_header, translate
from paperdesk.web.server import create_server

from .helpers import build_app

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("i18n_tool", ROOT / "scripts" / "i18n.py")
i18n_tool = importlib.util.module_from_spec(spec)
spec.loader.exec_module(i18n_tool)


class CatalogTests(unittest.TestCase):
    def test_every_message_is_translated_with_matching_placeholders(self):
        for lang, report in i18n_tool.problems().items():
            self.assertEqual(report["missing"], [], lang)
            self.assertEqual(report["placeholders"], [], lang)

    def test_msg_translation_with_params(self):
        message = _("폴더 이름은 {n}자 이하로 해 주세요.", n=120)
        self.assertEqual(str(message), "폴더 이름은 120자 이하로 해 주세요.")
        self.assertEqual(translate(message, "en"), "Folder names can be at most 120 characters.")
        self.assertEqual(translate(message, "ja"), "フォルダ名は120文字以内にしてください。")
        self.assertEqual(translate(_("폴더 이름을 입력하세요."), "zh"), "请输入文件夹名称。")
        self.assertEqual(translate("not a message id", "en"), "not a message id")

    def test_language_header(self):
        self.assertEqual(from_header("ja-JP,ja;q=0.9,en;q=0.8"), "ja")
        self.assertEqual(from_header("zh-Hans"), "zh")
        self.assertEqual(from_header("fr-FR"), "en")


class ServerLanguageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.tmp = build_app()
        cls.server = create_server(cls.app, "127.0.0.1", 0)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = cls.server.url.rstrip("/")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def get(self, path, lang, method="GET", body=None):
        request = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body else None,
                                         headers={"X-Paperdesk": "1", "X-Paperdesk-Lang": lang, "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read())
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read())

    def test_errors_follow_the_ui_language(self):
        for lang, expected in (("ko", "논문을 찾지 못했어요."), ("en", "Paper not found."), ("zh", "找不到论文。")):
            status, body = self.get("/api/documents/missing", lang)
            self.assertEqual((status, body["error"]["message"]), (404, expected))
        status, body = self.get("/api/folders", "en", "POST", {"name": " "})
        self.assertEqual(body["error"]["message"], "Enter a folder name.")

    def test_settings_texts_and_ui_language_setting(self):
        _, view = self.get("/api/settings", "ja")
        codex = next(p for p in view["providers"] if p["id"] == "codex-cli")
        self.assertEqual(codex["options"][0]["label"], "モデル")
        openai = next(p for p in view["providers"] if p["id"] == "openai-api")
        self.assertEqual(openai["options"][1]["label"], "APIキー")
        status, view = self.get("/api/settings", "en", "PUT", {"ui_language": "zh"})
        self.assertEqual((status, view["ui_language"]), (200, "zh"))
        status, body = self.get("/api/settings", "en", "PUT", {"ui_language": "xx"})
        self.assertEqual(body["error"]["message"], "Unsupported display language.")
