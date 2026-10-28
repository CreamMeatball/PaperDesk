import json
import threading
import unittest
import urllib.error
import urllib.request
from urllib.parse import quote

from paperdesk.web.server import create_server

from .helpers import build_app, make_pdf


class WebTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app, cls.tmp = build_app()
        cls.server = create_server(cls.app, "127.0.0.1", 0)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = cls.server.url.rstrip("/")

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.tmp.cleanup()

    def call(self, method, path, body=None, headers=None, raw=None):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        request = urllib.request.Request(self.base + path, data=data, method=method,
                                         headers={"X-Paperdesk": "1", "Content-Type": "application/json", **(headers or {})})
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, response.read(), dict(response.headers)
        except urllib.error.HTTPError as error:
            return error.code, error.read(), dict(error.headers)

    def test_end_to_end_folder_upload_move_and_assist(self):
        status, body, _ = self.call("POST", "/api/folders", {"name": "Diffusion"})
        self.assertEqual(status, 201)
        folder = json.loads(body)["folder"]
        status, body, _ = self.call("POST", "/api/documents?folder=" + folder["id"], raw=make_pdf(["Denoising"]),
                                    headers={"Content-Type": "application/pdf", "X-Filename": quote("DDPM 논문.pdf")})
        self.assertEqual(status, 201)
        doc = json.loads(body)["document"]
        self.assertEqual((doc["title"], doc["folder_id"]), ("DDPM 논문", folder["id"]))
        status, body, headers = self.call("GET", "/api/documents/" + doc["id"] + "/file")
        self.assertEqual((status, headers["Content-Type"]), (200, "application/pdf"))
        self.assertTrue(body.startswith(b"%PDF-"))
        status, body, _ = self.call("PATCH", "/api/documents/" + doc["id"], {"folder_id": None})
        self.assertIsNone(json.loads(body)["document"]["folder_id"])
        self.call("PUT", "/api/settings", {"provider": "demo"})
        status, body, _ = self.call("POST", "/api/assist", {"task": "translate", "text": "Denoising diffusion"})
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body)["provider_id"], "demo")

    def test_rejects_requests_without_app_header(self):
        status, body, _ = self.call("POST", "/api/folders", {"name": "x"}, headers={"X-Paperdesk": "0"})
        self.assertEqual(status, 403)

    def test_rejects_cross_site_and_foreign_host(self):
        status, _, _ = self.call("GET", "/api/library", headers={"Sec-Fetch-Site": "cross-site"})
        self.assertEqual(status, 403)
        status, _, _ = self.call("GET", "/api/library", headers={"Host": "evil.example:80"})
        self.assertEqual(status, 403)

    def test_static_routes_and_traversal(self):
        for path in ("/", "/library", "/reader", "/settings"):
            status, body, headers = self.call("GET", path)
            self.assertEqual(status, 200, path)
            self.assertIn(b"<main", body)
            self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        status, _, _ = self.call("GET", "/../../pyproject.toml")
        self.assertEqual(status, 404)
        status, _, _ = self.call("GET", "/js/%2e%2e/%2e%2e/app.py")
        self.assertEqual(status, 404)

    def test_errors_are_json(self):
        status, body, _ = self.call("GET", "/api/documents/missing")
        self.assertEqual(status, 404)
        self.assertEqual(json.loads(body)["error"]["code"], "not_found")

