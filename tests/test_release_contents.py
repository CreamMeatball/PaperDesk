import unittest

from paperdesk.domain.errors import InvalidInput
from paperdesk.ports.ai import CommandResult
from paperdesk.ports.settings import Settings
from paperdesk.infrastructure.settings_store import MemorySettingsStore
from paperdesk.providers.registry import default_registry
from .helpers import build_app
from .test_providers import FakeRunner, FakeHttp


class ReleaseContentsTests(unittest.TestCase):
    def test_production_registry_contains_only_implemented_connections(self):
        self.assertEqual(default_registry().ids(),[
            'codex-cli','claude-code','openai-api','anthropic-api','ollama','openai-compatible'])

    def test_removed_connections_do_not_silently_switch_to_another_ai(self):
        for provider in ('demo','chatgpt-plan'):
            with self.subTest(provider=provider):
                app,tmp=build_app(registry=default_registry(),
                    settings_store=MemorySettingsStore(Settings(provider=provider,target_language='Korean',
                        provider_options={provider:{'model':'saved-model'}})),
                    runner=FakeRunner(CommandResult(0,'OK','')),http=FakeHttp(get={'data':[]}))
                try:
                    self.assertEqual(app.settings.view()['provider'],'')
                    self.assertIsNone(app.settings.active_provider())
                    self.assertEqual(app.settings.load().options_for(provider),{'model':'saved-model'})
                    self.assertEqual(app.settings.load().target_language,'Korean')
                    with self.assertRaises(InvalidInput):app.settings.update_general(provider=provider)
                finally:tmp.cleanup()
