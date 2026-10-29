import shutil
import subprocess
import tempfile
import unittest
import types
from unittest.mock import Mock, patch
from paperdesk.desktop import NativeWindowShell, _macos_settings_shortcut
from paperdesk.platforms import MacPlatform
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

class ReaderUIRegressionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('node'), 'Node.js is needed for the reader regression suite')
    def test_reader_interactions(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'package.json').write_text('{"type":"module"}')
            shutil.copytree(ROOT/'src/paperdesk/web/static/js', root/'src/paperdesk/web/static/js')
            (root/'tests/js').mkdir(parents=True)
            shutil.copyfile(ROOT/'tests/js/reader_ui.mjs', root/'tests/js/reader_ui.mjs')
            result = subprocess.run(['node', '--test', str(root/'tests/js/reader_ui.mjs')], capture_output=True, text=True, encoding='utf-8')
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


    def test_native_settings_menu_opens_the_existing_settings_page(self):
        class Menu:
            def __init__(self, title, items): self.title, self.items = title, items
        class MenuAction:
            def __init__(self, title, function): self.title, self.function = title, function
        webview = types.SimpleNamespace(settings={}, create_window=Mock(), start=Mock())
        with tempfile.TemporaryDirectory() as directory, patch.dict('sys.modules', {
            'webview':webview, 'webview.menu':types.SimpleNamespace(Menu=Menu,MenuAction=MenuAction)
        }):
            NativeWindowShell(MacPlatform(),Path(directory)).run('http://127.0.0.1:1234/')
        options = webview.start.call_args.kwargs
        self.assertEqual(options['menu'][0].title,'__app__')
        action = options['menu'][0].items[0]
        self.assertEqual(action.title,'Settings…')
        action.function()
        webview.create_window.return_value.load_url.assert_called_once_with('http://127.0.0.1:1234/settings?shell=native')
        self.assertFalse(webview.create_window.call_args.kwargs['frameless'])

    def test_native_settings_menu_has_command_comma_shortcut(self):
        about, settings = Mock(), Mock()
        about.title.return_value = 'About Paperdesk'
        settings.title.return_value = 'Settings…'
        app = Mock()
        app.mainMenu.return_value.itemAtIndex_.return_value.submenu.return_value.itemArray.return_value = [about, settings]
        with patch.dict('sys.modules', {'AppKit':types.SimpleNamespace(
            NSApplication=types.SimpleNamespace(sharedApplication=lambda:app), NSEventModifierFlagCommand=1<<20)}):
            _macos_settings_shortcut()
        settings.setKeyEquivalent_.assert_called_once_with(',')
        settings.setKeyEquivalentModifierMask_.assert_called_once_with(1<<20)
