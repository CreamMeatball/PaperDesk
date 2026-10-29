import json
import unittest
from pathlib import Path
from unittest.mock import patch

from paperdesk.domain.models import ProviderStatus
from paperdesk.ports.ai import AIProvider, OptionField
from paperdesk.ports.settings import Settings
from paperdesk.infrastructure.settings_store import MemorySettingsStore
from paperdesk.providers.registry import ProviderRegistry
from paperdesk.services.layout import LayoutAnalysis, normalize_docling
from .helpers import build_app, make_pdf


def docling_fixture():
    def item(ref, label, text, page=1, span=None):
        return {'self_ref':ref,'label':label,'text':text,'prov':[{'page_no':page,'charspan':span or [0,len(text)],
            'bbox':{'l':50,'t':700,'r':280,'b':650,'coord_origin':'BOTTOMLEFT'}}]}
    return {'version':'2.142.1','document':{
        'pages':{'1':{'size':{'width':600,'height':800}},'2':{'size':{'width':600,'height':800}}},
        'body':{'self_ref':'#/body','children':[{'$ref':'#/texts/1'},{'$ref':'#/texts/0'}]},
        'texts':[item('#/texts/0','text','Second paragraph.'),item('#/texts/1','text','First paragraph.'),
                 item('#/texts/2','formula',''),item('#/texts/3','text','Page one.Page two.',2,[9,18])],
        'pictures':[], 'tables':[]}}


class LayoutAnalysisTests(unittest.TestCase):
    def test_docling_coordinates_reading_order_and_page_charspans(self):
        result=normalize_docling(docling_fixture())
        self.assertEqual(result['engine'],'docling')
        self.assertEqual([b['text'] for b in result['pages'][0]['blocks'][:2]],['First paragraph.','Second paragraph.'])
        self.assertEqual(result['pages'][0]['blocks'][0]['rect'],[50/600,100/800,280/600,150/800])
        self.assertIsNone(result['pages'][0]['blocks'][2]['text'])
        self.assertEqual(result['pages'][1]['blocks'][0]['text'],'Page two.')

    def test_table_contents_are_excluded_but_captions_are_kept(self):
        source=docling_fixture();table=dict(source['document']['texts'][0],self_ref='#/tables/0',label='table')
        source['document']['tables']=[table]
        source['document']['texts'][1]['label']='caption'
        result=normalize_docling(source)
        self.assertEqual([b['kind'] for b in result['pages'][0]['blocks']],['caption','table'])

    def test_successful_analysis_is_cached_and_not_queued_again(self):
        app,tmp=build_app();self.addCleanup(tmp.cleanup);self.addCleanup(app.analysis.close)
        doc,_=app.library.import_pdf('fixture.pdf',make_pdf(['A paper.']))
        directory=app.analysis._directory(doc.id);directory.mkdir(parents=True)
        (directory/'layout.json').write_text(json.dumps(normalize_docling(docling_fixture())))
        with patch.object(app.analysis._pool,'submit') as submit:
            self.assertEqual(app.analysis.ensure(doc.id)['state'],'completed');submit.assert_not_called()
        # A new app process reuses the same content/version cache.
        other=LayoutAnalysis(app.paths,app.library);self.addCleanup(other.close)
        self.assertEqual(other.status(doc.id)['state'],'completed')

    def test_failure_needs_explicit_retry_and_does_not_change_original(self):
        app,tmp=build_app();self.addCleanup(tmp.cleanup);self.addCleanup(app.analysis.close)
        content=make_pdf(['Keep this PDF.']);doc,_=app.library.import_pdf('fixture.pdf',content)
        with patch.object(app.analysis,'_python',return_value=Path('/missing/python')):
            app.analysis._run(doc.id)
        self.assertEqual(app.analysis.status(doc.id)['state'],'failed')
        with patch.object(app.analysis._pool,'submit') as submit:
            app.analysis.ensure(doc.id);submit.assert_not_called()
            self.assertEqual(app.analysis.ensure(doc.id,retry=True)['state'],'queued');submit.assert_called_once()
        self.assertEqual(app.library.pdf_path(doc.id).read_bytes(),content)


class LoginCodex(AIProvider):
    id='codex-cli';label='Codex';kind='local-cli';options=(OptionField('model','Model'),)
    logged_in=True
    def status(self):return ProviderStatus(self.logged_in,'local login')
    def available_models(self):return ['gpt-6-luna','gpt-6.1-luna','gpt-6.1-sol']
    def complete(self,prompt):raise AssertionError('Initialization must not send an AI request')


class LoginClaude(LoginCodex):
    id='claude-code';label='Claude'
    def available_models(self):return ['sonnet','opus','haiku']


class InitialAISelectionTests(unittest.TestCase):
    def app(self,settings=None):
        app,tmp=build_app(registry=ProviderRegistry([LoginCodex,LoginClaude]),
                          settings_store=MemorySettingsStore(settings or Settings()))
        self.addCleanup(tmp.cleanup);self.addCleanup(app.analysis.close)
        return app

    def test_first_entry_chooses_logged_in_codex_and_latest_supported_luna(self):
        app=self.app();view=app.settings.initialize_ai()
        self.assertEqual(view['provider'],'codex-cli')
        self.assertEqual(app.settings.load().options_for('codex-cli')['model'],'gpt-6.1-luna')

    def test_claude_login_is_used_if_codex_is_not_logged_in(self):
        app=self.app()
        with patch.object(LoginCodex,'logged_in',False),patch.object(LoginClaude,'logged_in',True):
            self.assertEqual(app.settings.initialize_ai()['provider'],'claude-code')
        self.assertEqual(app.settings.load().options_for('claude-code')['model'],'sonnet')

    def test_saved_provider_and_model_are_preserved(self):
        app=self.app(Settings(provider='claude-code',provider_options={'claude-code':{'model':'haiku'}}))
        app.settings.initialize_ai()
        self.assertEqual(app.settings.load().provider,'claude-code')
        self.assertEqual(app.settings.load().options_for('claude-code')['model'],'haiku')

    def test_no_login_and_expired_selected_login_do_not_switch_to_another_account(self):
        app=self.app()
        with patch.object(LoginCodex,'logged_in',False),patch.object(LoginClaude,'logged_in',False):
            self.assertEqual(app.settings.initialize_ai()['provider'],'')
        app.settings.update_general(provider='claude-code')
        with patch.object(LoginClaude,'logged_in',False):
            self.assertEqual(app.settings.initialize_ai()['provider'],'claude-code')
