"""An allowlist, deliberately independent of settings, paper titles and provider output."""
import platform
import sqlite3
import sys
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
    return report
