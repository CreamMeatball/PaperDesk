"""Portable, validated library archives. Secrets and WebKit/CLI authentication are never exported."""
import hashlib
import json
import os
import re
import shutil
import sqlite3
import stat
import tempfile
import time
import uuid
import zipfile
from contextlib import closing
from pathlib import Path

from .. import STORAGE_ID, __version__
from ..config import AppPaths
from ..domain.errors import InvalidInput, NotFound
from ..i18n import _
from ..ports.settings import Settings
from .sqlite import Database, MIGRATIONS

MAX_EXPANDED = 4 * 1024**3


def digest(path: Path) -> str:
    result = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            result.update(chunk)
    return result.hexdigest()


def portable_settings(data: dict) -> dict:
    if not isinstance(data, dict) or not isinstance(data.get('provider_options', {}), dict):
        raise ValueError('Invalid settings')
    settings = Settings.from_dict(data)
    settings.provider_options = {pid: {k: v for k, v in values.items() if k in ('model', 'binary', 'base_url')}
                                 for pid, values in settings.provider_options.items()}
    return settings.to_dict()


def validate_database(path: Path) -> tuple[int, list]:
    """Check the claimed schema and migrate a disposable copy before replacing live data."""
    path = path.resolve()
    with tempfile.TemporaryDirectory(prefix='paperdesk-validate-') as temporary:
        copy = Path(temporary)/'library.sqlite3'
        with closing(sqlite3.connect(path.as_uri()+'?mode=ro', uri=True)) as source, closing(sqlite3.connect(copy)) as target:
            version = source.execute('PRAGMA user_version').fetchone()[0]
            if not 1 <= version <= len(MIGRATIONS):
                raise ValueError('Unsupported schema')
            if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or source.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Database integrity')
            # Compare against the actual append-only schema, not just its self-reported version number.
            with closing(sqlite3.connect(':memory:')) as reference:
                for script in MIGRATIONS[:version]:
                    reference.executescript(script)
                expected = list(reference.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name"))
                actual = list(source.execute("SELECT type,name,sql FROM sqlite_master WHERE sql IS NOT NULL ORDER BY type,name"))
                if actual != expected:
                    raise ValueError('Invalid schema')
            source.backup(target)
        database = Database(copy)
        with database.connect() as db:
            if db.execute('PRAGMA foreign_key_check').fetchone():
                raise ValueError('Database integrity')
            return version, list(db.execute('SELECT id,sha256 FROM documents'))


class LibraryArchives:
    def __init__(self, paths: AppPaths) -> None:
        self.paths = paths

    def export(self) -> Path:
        folder = self.paths.root / 'backups' / 'exports'
        folder.mkdir(parents=True, exist_ok=True)
        output = folder / (uuid.uuid4().hex + '.paperdesk')
        try:
            with tempfile.TemporaryDirectory(prefix='paperdesk-backup-') as temporary:
                root = Path(temporary)
                with closing(sqlite3.connect(self.paths.database)) as source, closing(sqlite3.connect(root/'library.sqlite3')) as target:
                    source.backup(target)
                config = json.loads(self.paths.settings_file.read_text(encoding='utf-8')) if self.paths.settings_file.exists() else {}
                (root/'settings.json').write_text(json.dumps(portable_settings(config), ensure_ascii=False), encoding='utf-8')
                entries = {name: root/name for name in ('library.sqlite3', 'settings.json')}
                with closing(sqlite3.connect(root/'library.sqlite3')) as db:
                    for doc_id, in db.execute('SELECT id FROM documents'):
                        if not re.fullmatch(r'[a-zA-Z0-9_-]+', doc_id):
                            raise InvalidInput(_("서재의 문서 식별자를 확인할 수 없어요."))
                        name = f'files/documents/{doc_id}.pdf'
                        entries[name] = self.paths.root/name
                manifest = {'format': 1, 'storage_id': STORAGE_ID, 'version': __version__,
                            'sha256': {name: digest(path) for name, path in entries.items()}}
                with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
                    for name, path in entries.items():
                        archive.write(path, name)
                    archive.writestr('manifest.json', json.dumps(manifest))
            return output
        except Exception:
            output.unlink(missing_ok=True)
            raise

    def prepare(self, archive_path: Path) -> dict:
        token = uuid.uuid4().hex
        stage = self.paths.root/'restore-staging'/token
        stage.mkdir(parents=True, mode=0o700)
        try:
            with zipfile.ZipFile(archive_path) as archive:
                infos = archive.infolist()
                names = [info.filename for info in infos]
                if (len(names) != len(set(names)) or len(names) > 100_000 or
                        sum(info.file_size for info in infos) > MAX_EXPANDED):
                    raise ValueError('Archive bounds')
                for info in infos:
                    if (not re.fullmatch(r'(manifest\.json|library\.sqlite3|settings\.json|files/documents/[A-Za-z0-9_-]+\.pdf)', info.filename)
                            or stat.S_ISLNK(info.external_attr >> 16)):
                        raise ValueError('Archive path')
                if archive.getinfo('manifest.json').file_size > 16*1024*1024:
                    raise ValueError('Manifest bounds')
                manifest = json.loads(archive.read('manifest.json'))
                if not isinstance(manifest, dict) or manifest.get('format') != 1 or manifest.get('storage_id') != STORAGE_ID:
                    raise ValueError('Archive format')
                hashes = manifest.get('sha256', {})
                if not isinstance(hashes, dict) or set(hashes) != set(names)-{'manifest.json'} or not {'library.sqlite3','settings.json'} <= hashes.keys():
                    raise ValueError('Archive members')
                for name in names:
                    target = stage/name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with archive.open(name) as source, target.open('wb') as output:
                        shutil.copyfileobj(source, output)
                    if name != 'manifest.json' and digest(target) != hashes[name]:
                        raise ValueError('Archive checksum')
            version, documents = validate_database(stage/'library.sqlite3')
            expected = {f'files/documents/{doc_id}.pdf' for doc_id, _ in documents}
            if expected != {name for name in hashes if name.startswith('files/')}:
                raise ValueError('PDF inventory')
            for doc_id, sha in documents:
                if digest(stage/f'files/documents/{doc_id}.pdf') != sha:
                    raise ValueError('PDF checksum')
            config = portable_settings(json.loads((stage/'settings.json').read_text(encoding='utf-8')))
            for values in config['provider_options'].values():
                # A CLI path from another computer (a Mac backup restored on Windows) falls back to automatic discovery.
                if values.get('binary') and not Path(values['binary']).expanduser().is_file():
                    del values['binary']
            (stage/'settings.json').write_text(json.dumps(config, ensure_ascii=False), encoding='utf-8')
            manifest['sha256']['settings.json'] = digest(stage/'settings.json')
            (stage/'manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
            (stage/'files').mkdir(exist_ok=True)
            return {'token': token, 'documents': len(documents), 'bytes': sum(p.stat().st_size for p in stage.rglob('*') if p.is_file()),
                    'version': manifest.get('version', ''), 'schema': version}
        except (ValueError, KeyError, TypeError, OSError, sqlite3.Error, zipfile.BadZipFile, RuntimeError, NotImplementedError) as error:
            shutil.rmtree(stage, ignore_errors=True)
            raise InvalidInput(_("백업 파일이 손상되었거나 지원하지 않는 형식이에요. 현재 서재는 변경하지 않았어요.")) from error

    def schedule(self, token: str) -> dict:
        if not re.fullmatch(r'[a-f0-9]{32}', token):
            raise InvalidInput(_("백업 확인을 다시 진행해 주세요."))
        stage = self.paths.root/'restore-staging'/token
        if not (stage/'library.sqlite3').is_file():
            raise NotFound(_("확인한 백업 파일을 찾지 못했어요."))
        temporary = self.paths.root/'pending-restore.tmp'
        temporary.write_text(json.dumps({'token': token}), encoding='utf-8')
        _replace(temporary, self.paths.root/'pending-restore.json')
        return {'restart_required': True}


def _replace(source: Path, target: Path) -> None:
    """os.replace; Windows refuses to move a folder while antivirus or indexing briefly holds a file in it, so retry."""
    for delay in (0.1, 0.3, 1.0, 2.0) if os.name == 'nt' else ():
        try:
            return os.replace(source, target)
        except PermissionError:
            time.sleep(delay)
    os.replace(source, target)


def _identity(path: Path) -> list[int]:
    stat = path.stat()
    return [stat.st_dev, stat.st_ino]


def _rollback(root: Path, old: Path, candidate: Path, stage: Path) -> None:
    if old.exists():
        if root.exists():
            # Preserve a directory created by an unexpected concurrent writer as well.
            _replace(root, root.with_name(root.name+'.restore-conflict-'+uuid.uuid4().hex))
        _replace(old, root)
    if candidate.exists():
        stage.parent.mkdir(parents=True, exist_ok=True)
        _replace(candidate, stage)


def apply_pending_restore(paths: AppPaths) -> None:
    root = paths.root.resolve()
    journal = root.with_name('.'+root.name+'-restore.json')
    if journal.exists():
        state = json.loads(journal.read_text(encoding='utf-8'))
        token = state['token']
        if (not re.fullmatch('[a-f0-9]{32}', token) or state['old'] != root.name+'.before-restore-'+token
                or state['candidate'] != root.name+'.restore-'+token):
            raise InvalidInput(_("서재 복원 기록을 확인해 주세요."))
        old = root.with_name(state['old'])
        candidate = root.with_name(state['candidate'])
        installed = root.exists() and _identity(root) == state.get('candidate_identity')
        if not installed:
            _rollback(root, old, candidate, root/'restore-staging'/token)
        if not root.exists():
            raise InvalidInput(_("서재 복원 기록을 확인해 주세요."))
        journal.unlink()
    pending = root/'pending-restore.json'
    if not pending.exists():
        return
    token = json.loads(pending.read_text(encoding='utf-8'))['token']
    if not re.fullmatch(r'[a-f0-9]{32}', token):
        raise InvalidInput(_("백업 확인을 다시 진행해 주세요."))
    stage = root/'restore-staging'/token
    # Revalidate the staged snapshot before replacing any live file.
    manifest = json.loads((stage/'manifest.json').read_text(encoding='utf-8'))
    for name, expected in manifest['sha256'].items():
        if (not re.fullmatch(r'(library\.sqlite3|settings\.json|files/documents/[A-Za-z0-9_-]+\.pdf)', name)
                or digest(stage/name) != expected):
            raise InvalidInput(_("백업 파일이 손상되었어요."))
    validate_database(stage/'library.sqlite3')
    candidate = root.with_name(root.name+'.restore-'+token)
    old = root.with_name(root.name+'.before-restore-'+token)
    journal_tmp = journal.with_name(journal.name+'.tmp')
    journal_tmp.write_text(json.dumps({'old': old.name, 'candidate': candidate.name, 'token': token,
                                      'candidate_identity': _identity(stage)}), encoding='utf-8')
    os.chmod(journal_tmp, 0o600)
    _replace(journal_tmp, journal)
    try:
        _replace(stage, candidate)
        _replace(root, old)
        _replace(candidate, root)
    except OSError:
        _rollback(root, old, candidate, stage)
        journal.unlink()
        raise
    journal.unlink()
    # The previous complete data directory is retained beside the restored directory for recovery.
