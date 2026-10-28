import base64
import importlib.util
import json
import queue
import sqlite3
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from paperdesk.domain.errors import InvalidInput, ProviderUnavailable
from paperdesk.infrastructure.macos_updates import SparkleUpdates, valid_update_configuration
from paperdesk.infrastructure.sqlite import Database, MIGRATIONS
from paperdesk.ports.updates import UpdateBackend, UpdateState
from paperdesk.services.updates import UpdateService
from paperdesk.web.server import create_server
from .helpers import build_app, make_pdf

ROOT = Path(__file__).resolve().parents[1]


def script(name):
    spec = importlib.util.spec_from_file_location(name, ROOT / 'scripts' / (name + '.py'))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class RecordingUpdates(UpdateBackend):
    def __init__(self):
        self.auto = False
        self.busy = False
        self.checks = 0

    def state(self):
        return UpdateState(True, not self.busy, self.auto)

    def check(self):
        self.checks += 1

    def set_automatic_checks(self, enabled):
        self.auto = enabled


class UpdateTests(unittest.TestCase):
    def test_unconfigured_build_does_not_claim_to_be_current_or_connect(self):
        service = UpdateService()
        state = service.view('en')
        self.assertFalse(state['available'])
        self.assertIn('distributed macOS app', state['message'])
        with self.assertRaises(ProviderUnavailable):
            service.check()
        self.assertFalse(SparkleUpdates().state().available)

    def test_native_backend_receives_manual_check_and_opt_in(self):
        backend = RecordingUpdates()
        service = UpdateService(backend)
        self.assertFalse(service.view()['automatic_checks'])
        service.configure(True)
        self.assertTrue(backend.auto)
        self.assertEqual(service.check(), {'opened': True})
        self.assertEqual(backend.checks, 1)
        backend.busy = True
        with self.assertRaises(InvalidInput):
            service.check()
        for bad in ['yes', 1, None]:
            with self.assertRaises(InvalidInput):
                service.configure(bad)

    def test_native_check_is_dispatched_from_http_thread_to_main_thread(self):
        calls = []
        class Controller:
            def checkForUpdates_(self, sender):
                self_thread = threading.current_thread()
                calls.append(self_thread)
        native = SparkleUpdates()
        native._controller = Controller()
        jobs = queue.Queue()
        native._dispatch = jobs.put
        errors = []
        def request():
            try:
                native.check()
            except Exception as error:
                errors.append(error)
        worker = threading.Thread(target=request)
        worker.start()
        jobs.get(timeout=2)()
        worker.join(timeout=2)
        self.assertFalse(worker.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(calls, [threading.main_thread()])

    def test_update_configuration_requires_https_and_pinned_public_key(self):
        key = base64.b64encode(bytes(range(32))).decode()
        self.assertTrue(valid_update_configuration('https://example.org/appcast.xml', key))
        for feed, public_key in [('http://example.org/feed',key), ('https://name:secret@example.org/feed',key),
                                 ('https://example.org/feed','bad'), ('file:///tmp/feed',key)]:
            self.assertFalse(valid_update_configuration(feed, public_key))
        metadata = script('build_macos').bundle_metadata(version='1.2.3', build=27,
                           feed_url='https://example.org/appcast.xml', public_key=key)
        self.assertEqual(metadata['CFBundleVersion'], '27')
        self.assertFalse(metadata['SUEnableAutomaticChecks'])
        self.assertFalse(metadata['SUAutomaticallyUpdate'])
        self.assertFalse(metadata['SUAllowsAutomaticUpdates'])
        self.assertTrue(metadata['SUVerifyUpdateBeforeExtraction'])

    def test_api_opens_native_ui_and_persists_user_choice_without_ai(self):
        app, tmp = build_app()
        backend = RecordingUpdates()
        app.updates.attach(backend)
        server = create_server(app, '127.0.0.1', 0)
        threading.Thread(target=server.serve_forever, daemon=True).start()
        def call(path, method='GET', data=None):
            req = urllib.request.Request(server.url + path, method=method,
                data=json.dumps(data).encode() if data is not None else None,
                headers={'X-Paperdesk':'1','Content-Type':'application/json'})
            with urllib.request.urlopen(req) as response:
                return json.load(response)
        try:
            self.assertFalse(call('api/updates')['automatic_checks'])
            self.assertTrue(call('api/updates/preferences', 'PUT', {'automatic_checks':True})['automatic_checks'])
            self.assertEqual(call('api/updates/check','POST',{}), {'opened':True})
            self.assertEqual(backend.checks, 1)
        finally:
            server.shutdown()
            server.server_close()
            tmp.cleanup()

    def test_database_migration_backs_up_committed_library(self):
        app, tmp = build_app()
        try:
            doc, _ = app.library.import_pdf('old.pdf', make_pdf(['Data before an update']))
            # A real older installed schema, with existing user documents in WAL mode.
            with sqlite3.connect(app.paths.database) as connection:
                connection.executescript('DROP TABLE conversations; DROP TABLE preferences; PRAGMA user_version=3;')
            Database(app.paths.database)
            backups = list((app.paths.root / 'backups/migrations').glob('*.sqlite3'))
            self.assertEqual(len(backups), 1)
            with sqlite3.connect(backups[0]) as backup:
                self.assertEqual(backup.execute('PRAGMA user_version').fetchone()[0], 3)
                self.assertEqual(backup.execute('SELECT title FROM documents WHERE id=?',(doc.id,)).fetchone()[0], doc.title)
            Database(app.paths.database)
            self.assertEqual(len(list((app.paths.root / 'backups/migrations').glob('*.sqlite3'))), 1)
        finally:
            tmp.cleanup()

    def test_failed_migration_rolls_back_and_future_schema_is_refused(self):
        app, tmp = build_app()
        try:
            # Exercise a future migration that fails part-way through.
            with mock.patch('paperdesk.infrastructure.sqlite.MIGRATIONS', MIGRATIONS +
                            ('CREATE TABLE should_rollback(x); INVALID SQL;',)):
                with self.assertRaises(sqlite3.Error):
                    Database(app.paths.database)
            with sqlite3.connect(app.paths.database) as connection:
                self.assertEqual(connection.execute('PRAGMA user_version').fetchone()[0], len(MIGRATIONS))
                self.assertIsNone(connection.execute("SELECT name FROM sqlite_master WHERE name='should_rollback'").fetchone())
                connection.execute('PRAGMA user_version=99')
            with self.assertRaises(InvalidInput):
                Database(app.paths.database)
        finally:
            tmp.cleanup()


class MacReleaseTests(unittest.TestCase):
    def test_cask_uses_native_app_versions_and_keeps_user_data(self):
        release = script('release_macos')
        shared = {'version':'1.2.3', 'build':27, 'bundle_id':'org.paperdesk.Paperdesk'}
        arm = {**shared, 'arch':'arm64', 'sha256':'a'*64}
        intel = {**shared, 'arch':'x86_64', 'sha256':'b'*64}
        text = release.render_cask('example/paperdesk', [arm, intel])
        self.assertIn('version "1.2.3,27"', text)
        self.assertIn('app "Paperdesk.app"', text)
        self.assertIn('auto_updates true', text)
        self.assertIn('on_arm do', text)
        self.assertIn('on_intel do', text)
        self.assertNotIn('zap', text)
        self.assertNotIn('Application Support', text)
        with self.assertRaises(ValueError):
            release.render_cask('example/paperdesk', [arm, {**intel, 'build':26}])

    def test_unsigned_development_artifact_cannot_be_published(self):
        release = script('release_macos')
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / 'Paperdesk-1.2.3-27-arm64.dmg'
            path.write_bytes(b'example dmg')
            meta = {'version':'1.2.3','build':27,'arch':'arm64','updates':False,'signed':False,'notarized':False}
            path.with_suffix('.json').write_text(json.dumps(meta))
            with self.assertRaises(ValueError):
                release.artifact(path)

    def test_appcast_checks_expected_artifact_signature_field_and_build(self):
        release = script('release_macos')
        signature = base64.b64encode(bytes(64)).decode()
        with tempfile.TemporaryDirectory() as folder:
            dmg = Path(folder) / 'app.dmg'
            dmg.write_bytes(b'abc')
            feed = Path(folder) / 'appcast.xml'
            xml = ('<rss xmlns:sparkle="'+release.SPARKLE+'"><channel><item>'
                   '<sparkle:version>27</sparkle:version><enclosure url="https://example.org/app.dmg" '
                   'length="3" sparkle:edSignature="'+signature+'" /></item></channel></rss>')
            feed.write_text(xml)
            release.verify_feed(feed, {'build':27,'path':dmg}, 'https://example.org/app.dmg')
            feed.write_text(xml.replace('length="3"','length="4"'))
            with self.assertRaises(ValueError):
                release.verify_feed(feed, {'build':27,'path':dmg}, 'https://example.org/app.dmg')
