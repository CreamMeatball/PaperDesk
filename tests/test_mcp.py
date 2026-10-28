import io
import json
import unittest

from paperdesk.mcp import StdioMcpServer

from .helpers import build_app, make_pdf


class McpTests(unittest.TestCase):
    def setUp(self):
        self.app, self.tmp = build_app()
        folder = self.app.folders.create("Vision")
        self.doc, _ = self.app.library.import_pdf("vit.pdf", make_pdf(["ViT"]), folder.id)
        self.app.library.save_text(self.doc.id, ["An image is worth 16x16 words", "Patch embeddings"])

    def tearDown(self):
        self.tmp.cleanup()

    def exchange(self, *messages):
        stdin = io.StringIO("".join(json.dumps(m) + "\n" for m in messages))
        stdout = io.StringIO()
        StdioMcpServer.for_app(self.app, stdin=stdin, stdout=stdout).serve()
        return [json.loads(line) for line in stdout.getvalue().splitlines()]

    def test_handshake_list_and_read(self):
        replies = self.exchange(
            {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "list_papers", "arguments": {}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "read_paper", "arguments": {"id": self.doc.id, "first_page": 2}}},
            {"jsonrpc": "2.0", "id": 5, "method": "nope"},
        )
        self.assertEqual([r["id"] for r in replies], [1, 2, 3, 4, 5])
        self.assertEqual(replies[0]["result"]["protocolVersion"], "2025-06-18")
        self.assertEqual({t["name"] for t in replies[1]["result"]["tools"]}, {"list_papers", "read_paper", "search_papers"})
        papers = json.loads(replies[2]["result"]["content"][0]["text"])
        self.assertEqual((papers[0]["folder"], papers[0]["text_available"]), ("Vision", True))
        text = replies[3]["result"]["content"][0]["text"]
        self.assertIn("Patch embeddings", text)
        self.assertNotIn("16x16", text)
        self.assertEqual(replies[4]["error"]["code"], -32601)

    def test_unknown_paper_is_tool_error(self):
        replies = self.exchange({"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                                 "params": {"name": "read_paper", "arguments": {"id": "missing"}}})
        self.assertTrue(replies[0]["result"]["isError"])

