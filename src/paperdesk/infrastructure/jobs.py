import json
import sqlite3

from ..domain.models import utcnow
from ..ports.jobs import TranslationJobRepository
from .sqlite import Database


class SqliteTranslationJobs(TranslationJobRepository):
    def __init__(self, database: Database) -> None:
        self.database = database

    @staticmethod
    def _job(row) -> dict | None:
        if row is None:
            return None
        job = dict(row)
        job['payload'] = json.loads(job['payload'])
        return job

    def add(self, job: dict) -> dict:
        with self.database.connect() as db:
            try:
                db.execute('INSERT INTO translation_jobs '
                           '(id,doc_id,fingerprint,payload,state,total,created_at,updated_at) '
                           'VALUES (:id,:doc_id,:fingerprint,:payload,:state,:total,:created_at,:updated_at)',
                           {**job, 'payload': json.dumps(job['payload'], ensure_ascii=False)})
            except sqlite3.IntegrityError:
                row = db.execute("SELECT * FROM translation_jobs WHERE doc_id=? AND fingerprint=? "
                                 "AND state IN ('queued','running','paused')",
                                 (job['doc_id'], job['fingerprint'])).fetchone()
                if row is None:
                    raise
                return self._job(row)
        return self.get(job['id'])

    def get(self, job_id: str) -> dict | None:
        with self.database.connect() as db:
            return self._job(db.execute('SELECT * FROM translation_jobs WHERE id=?', (job_id,)).fetchone())

    def list(self, doc_id: str | None = None) -> list[dict]:
        with self.database.connect() as db:
            rows = db.execute('SELECT * FROM translation_jobs ' + ('WHERE doc_id=? ' if doc_id else '') +
                              'ORDER BY created_at', (doc_id,) if doc_id else ()).fetchall()
            return [self._job(row) for row in rows]

    def transition(self, job_id: str, before: tuple[str, ...], state: str, **changes) -> bool:
        if not set(changes) <= {'completed', 'error', 'payload'}:
            raise ValueError('Unsupported job field')
        if 'payload' in changes:
            changes['payload'] = json.dumps(changes['payload'], ensure_ascii=False)
        fields = {'updated_at': utcnow(), **changes}
        if state is not None:
            fields['state'] = state
        with self.database.connect() as db:
            result = db.execute('UPDATE translation_jobs SET ' + ','.join(k+'=?' for k in fields) +
                                ' WHERE id=? AND state IN (' + ','.join('?' for _ in before) + ')',
                                (*fields.values(), job_id, *before))
            return result.rowcount == 1
