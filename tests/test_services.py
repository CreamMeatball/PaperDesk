import json
import unittest

from paperdesk.domain.errors import InvalidInput, ProviderUnavailable
from paperdesk.domain.models import AssistRequest, AssistTask

from .helpers import build_app


class AssistantTests(unittest.TestCase):
    def setUp(self):
        self.app, self.tmp = build_app()

    def tearDown(self):
        self.tmp.cleanup()

    def test_requires_a_chosen_provider(self):
        with self.assertRaises(ProviderUnavailable):
            self.app.assistant.run(AssistRequest(AssistTask.TRANSLATE, "hello"))

    def test_demo_provider_answer_is_cached(self):
        self.app.settings.update_general(provider="demo")
        request = AssistRequest(AssistTask.EXPLAIN, "Self-attention lets each token attend to all tokens.")
        first = self.app.assistant.run(request)
        second = self.app.assistant.run(request)
        self.assertFalse(first.cached)
        self.assertTrue(second.cached)
        self.assertEqual(first.text, second.text)

    def test_ask_needs_question(self):
        self.app.settings.update_general(provider="demo")
        with self.assertRaises(InvalidInput):
            self.app.assistant.run(AssistRequest(AssistTask.ASK, "text", question=" "))


class SettingsTests(unittest.TestCase):
    def setUp(self):
        self.app, self.tmp = build_app()
        self.settings = self.app.settings

    def tearDown(self):
        self.tmp.cleanup()

    def test_secrets_go_to_secret_store_not_settings(self):
        described = self.settings.update_provider("openai-api", {"api_key": "sk-test-123", "model": "gpt-x"})
        stored = self.settings.load()
        self.assertNotIn("sk-test-123", json.dumps(stored.to_dict()))
        self.assertEqual(stored.options_for("openai-api"), {"model": "gpt-x"})
        self.assertTrue(described["available"])
        self.settings.update_provider("openai-api", {"api_key": None})
        self.assertFalse(self.settings.provider("openai-api").status().available)

    def test_rejects_unknown_provider_and_option(self):
        with self.assertRaises(Exception):
            self.settings.update_general(provider="nope")
        with self.assertRaises(InvalidInput):
            self.settings.update_provider("ollama", {"temperature": "1"})

    def test_view_lists_every_provider_with_option_schema(self):
        view = self.settings.view()
        ids = [p["id"] for p in view["providers"]]
        for expected in ("codex-cli", "claude-code", "chatgpt-plan", "openai-api", "anthropic-api", "ollama", "openai-compatible", "demo"):
            self.assertIn(expected, ids)
        ollama = next(p for p in view["providers"] if p["id"] == "ollama")
        self.assertEqual([o["key"] for o in ollama["options"]], ["base_url", "model", "api_key"])

