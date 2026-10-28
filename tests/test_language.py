import unittest
from unittest import mock

from paperdesk.config import language_name
from paperdesk.domain.models import AssistRequest, AssistTask, Completion, ProviderStatus
from paperdesk.platforms import LinuxPlatform, MacPlatform
from paperdesk.ports.ai import AIProvider
from paperdesk.providers.registry import ProviderRegistry

from .helpers import build_app


class RecordingProvider(AIProvider):
    id = "recording"
    label = "Recording"
    kind = "offline"
    prompts = []

    def status(self):
        return ProviderStatus(True)

    def complete(self, prompt):
        RecordingProvider.prompts.append(prompt)
        return Completion("ok", self.id)


class LanguageTests(unittest.TestCase):
    def test_language_codes(self):
        self.assertEqual(language_name("ko-KR"), "Korean")
        self.assertEqual(language_name("ko_KR.UTF-8"), "Korean")
        self.assertEqual(language_name("zh-Hans-KR"), "Chinese (Simplified)")
        self.assertIsNone(language_name("tlh"))

    def test_mac_prefers_system_settings_over_terminal_lang(self):
        output = '(\n    "ko-KR",\n    "en-KR"\n)\n'
        with mock.patch("subprocess.run", return_value=mock.Mock(returncode=0, stdout=output)), \
             mock.patch.dict("os.environ", {"LANG": "en_US.UTF-8", "LC_ALL": ""}):
            self.assertEqual(MacPlatform().preferred_language(), "Korean")

    def test_mac_falls_back_to_environment(self):
        with mock.patch("subprocess.run", side_effect=OSError), \
             mock.patch.dict("os.environ", {"LANG": "ja_JP.UTF-8", "LC_ALL": ""}):
            self.assertEqual(MacPlatform().preferred_language(), "Japanese")

    def test_c_locale_is_skipped(self):
        with mock.patch.dict("os.environ", {"LC_ALL": "C.UTF-8", "LANG": "de_DE.UTF-8"}):
            self.assertEqual(LinuxPlatform().preferred_language(), "German")

    def test_chosen_language_reaches_the_prompt_and_cache_key(self):
        RecordingProvider.prompts = []
        app, tmp = build_app(registry=ProviderRegistry([RecordingProvider]))
        self.addCleanup(tmp.cleanup)
        app.settings.update_general(provider="recording", target_language="Korean")
        request = lambda lang: AssistRequest(AssistTask.TRANSLATE, "Attention is all you need.", target_language=lang)
        app.assistant.run(request(app.settings.load().target_language))
        app.settings.update_general(target_language="Japanese")
        second = app.assistant.run(request(app.settings.load().target_language))
        self.assertFalse(second.cached)  # a new language must not reuse the Korean answer
        self.assertIn("natural Korean", RecordingProvider.prompts[0].user)
        self.assertIn("Answer in Japanese", RecordingProvider.prompts[1].system)
