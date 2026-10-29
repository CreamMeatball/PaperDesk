"""An allowlist, deliberately independent of settings, paper titles and provider output."""
import platform
import sqlite3
import sys
import json
from pathlib import Path
from contextlib import closing

from .. import __version__, STORAGE_ID


def diagnostic_report(paths) -> dict:
    with closing(sqlite3.connect(paths.database)) as db:
        schema = db.execute('PRAGMA user_version').fetchone()[0]
    report = {'app': STORAGE_ID, 'version': __version__, 'python': sys.version.split()[0],
            'os': platform.system(), 'os_version': platform.mac_ver()[0] or platform.release(),
            'architecture': platform.machine(), 'database_schema': schema,
            'includes': ['versions', 'architecture', 'schema'],
            'excludes': ['papers', 'filenames', 'paths', 'prompts', 'conversations', 'settings', 'credentials', 'logs']}
    if getattr(sys, 'frozen', False):
        # Windows: beside Paperdesk.exe; macOS: Paperdesk.app/Contents/Resources.
        manifest = (Path(sys.executable).parent if sys.platform == 'win32' else Path(sys.executable).parents[1]/'Resources')/'build-manifest.json'
        try:
            build = json.loads(manifest.read_text(encoding='utf-8'))
            report['build'] = build.get('build')
            report['source_tree_sha256'] = build.get('source_tree_sha256')
        except (OSError, ValueError):
            pass
    return report
