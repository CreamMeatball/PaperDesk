import tempfile
import unittest
from pathlib import Path
from unittest import mock

from .test_updates import ROOT, script


class SourceInstallTests(unittest.TestCase):
    def setUp(self):
        self.installer = script('install_source')

    def test_each_system_installs_its_window_lock_and_the_shared_docling_versions(self):
        with mock.patch.multiple(self.installer, WINDOWS=True, MACOS=False):
            self.assertEqual([p.name for p in self.installer.locks()], ['windows-app.lock', 'docling-windows.lock'])
            self.assertEqual(self.installer.environment_python(Path('env'), window=True), Path('env/Scripts/pythonw.exe'))
        with mock.patch.multiple(self.installer, WINDOWS=False, MACOS=True):
            self.assertEqual([p.name for p in self.installer.locks()], ['macos-app.lock', 'docling-macos.lock'])
            self.assertEqual(self.installer.environment_python(Path('env')), Path('env/bin/python'))
        for lock in ('windows-app.lock', 'macos-app.lock'):
            pins = (ROOT/'requirements'/lock).read_text(encoding='utf-8')
            self.assertIn('pywebview==6.2.1', pins)
        # The Windows Docling lock differs from macOS only by Windows-only packages.
        mac = set((ROOT/'requirements/docling-macos.lock').read_text(encoding='utf-8').split())
        windows = set((ROOT/'requirements/docling-windows.lock').read_text(encoding='utf-8').split())
        self.assertEqual({line.split('==')[0] for line in windows - mac}, {'colorama', 'pywin32'})
        self.assertEqual(mac - windows, set())

    def test_powershell_literals_escape_quotes(self):
        self.assertEqual(self.installer.quote("C:/Users/O'Brien/Paperdesk"), "'C:/Users/O''Brien/Paperdesk'")

    def test_only_environments_made_for_python_312_are_reused(self):
        with tempfile.TemporaryDirectory() as folder:
            environment = Path(folder)
            python = self.installer.environment_python(environment)
            python.parent.mkdir(parents=True)
            python.touch()
            (environment/'pyvenv.cfg').write_text('home = x\nversion = 3.12.10\n', encoding='utf-8')
            self.assertTrue(self.installer.matching_environment(environment))
            (environment/'pyvenv.cfg').write_text('home = x\nversion_info = 3.13.2\n', encoding='utf-8')
            self.assertFalse(self.installer.matching_environment(environment))
            self.assertFalse(self.installer.matching_environment(environment/'missing'))

    def test_uninstall_never_removes_a_folder_it_did_not_create(self):
        with tempfile.TemporaryDirectory() as folder, mock.patch.object(self.installer, 'WINDOWS', False), \
                mock.patch.object(self.installer, 'data_folder', return_value=Path('library')):
            mine, other = Path(folder)/'mine', Path(folder)/'other'
            for path in (mine, other):
                (path/'venv').mkdir(parents=True)
            (mine/self.installer.MARKER).touch()
            with self.assertRaises(SystemExit):
                self.installer.uninstall(other)
            self.assertTrue(other.exists())
            with mock.patch('builtins.print'):
                self.installer.uninstall(mine)
            self.assertFalse(mine.exists())


if __name__ == '__main__':
    unittest.main()
