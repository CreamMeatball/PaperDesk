"""A single local worker; restarting never silently resends an interrupted AI request."""
from __future__ import annotations
import hashlib
import json
import threading
import uuid

from ..domain.errors import InvalidInput, NotFound, ReaderError
from ..domain.models import utcnow
from ..i18n import _
from ..ports.jobs import TranslationJobRepository
from .translation import TranslationService

MISSING_RETRIES = 2              # extra one-block requests for paragraphs a reply left out
RETRYABLE = {'provider_failed'}  # dropped connection, timeout, server error; login, quota and model errors are final


class TranslationJobs:
    def __init__(self, repository: TranslationJobRepository, settings, library, translate, close_runner=lambda: None) -> None:
        self.repository = repository
        self.settings = settings
        self.library = library
        self.translate = translate
        self.close_runner = close_runner
        self.retry_delays = (2, 6)  # seconds before re-sending after a transient failure
        self._inflight = None
        self._active_batch = None
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread = None
        self._lock = threading.RLock()

    def start(self) -> None:
        with self._lock:
            if self._thread is not None:
                return
            for job in self.repository.list():
                self.repository.transition(job['id'], ('queued', 'running'), 'paused', error='interrupted')
            self._thread = threading.Thread(target=self._run, name='paperdesk-translations', daemon=True)
            self._thread.start()

    def close(self) -> None:
        self._stop.set()
        self._wake.set()
        self.close_runner()
        if self._thread is None:
            return
        if self._thread:
            self._thread.join(timeout=1)
        for job in self.repository.list():
            self.repository.transition(job['id'], ('queued', 'running'), 'paused', error='interrupted')

    @staticmethod
    def view(job: dict) -> dict:
        return {k: job[k] for k in ('id', 'doc_id', 'state', 'completed', 'total', 'error', 'created_at', 'updated_at')} | {
            'provider_id': job['payload']['provider_id'], 'model': job['payload']['model'],
            'language': job['payload']['language'],
            'missing_keys': job['payload'].get('missing_keys', []),
            'pending_keys': [b['key'] for b in job['payload']['blocks'][job['completed']:]]
            if job['state'] in ('queued', 'running') else []}

    def list(self, doc_id: str) -> list[dict]:
        self.library.get(doc_id)
        batch = self._active_batch
        return [{**self.view(job), 'request_in_flight': job['id'] == self._inflight,
                 'active_keys': list(batch[1]) if batch and batch[0] == job['id'] else []}
                for job in self.repository.list(doc_id)]

    def summaries(self, language: str) -> list[dict]:
        return [{k: job[k] for k in ('id', 'doc_id', 'state', 'completed', 'total', 'error')}
                for job in self.repository.list() if job['payload']['language'] == language]

    def create(self, doc_id: str, data: dict) -> dict:
        self.library.get(doc_id)
        raw = data.get('blocks')
        if not isinstance(raw, list) or not raw or len(raw) > 5000:
            raise InvalidInput(_("번역할 문단 범위를 확인해 주세요."))
        blocks = []
        for item in raw:
            blocks.extend(TranslationService.parse_blocks([item]))
        if sum(len(b.text) for b in blocks) > 2_000_000:
            raise InvalidInput(_("한 번에 보내기에는 글이 너무 길어요. 범위를 줄여 주세요."))
        current = self.settings.load()
        provider = self.settings.active_provider(current)
        if provider is None:
            raise InvalidInput(_("AI가 연결되지 않았어요. 설정에서 사용할 AI를 고르세요."))
        model = provider.resolve_model()
        options = dict(current.options_for(provider.id))
        if model:
            options['model'] = model
        force = data.get('force') is True
        self.start()
        with self._lock:
            # The reader and the background translation after an import may ask for the same paper: a paragraph
            # already waiting in a queued or running job (same language) is not queued again.
            active = [job for job in self.repository.list(doc_id) if job['state'] in ('queued', 'running')
                      and job['payload']['language'] == current.target_language]
            waiting = {b['key'] for job in active for b in job['payload']['blocks'][job['completed']:]}
            if not force:
                blocks = [b for b in blocks if b.key not in waiting]
                if not blocks:
                    return self.view(active[0])
            payload = {'provider_id': provider.id, 'model': model,
                       'options': options, 'language': current.target_language,
                       'title': str(data.get('title', ''))[:300], 'section': str(data.get('section', ''))[:200],
                       'terms': str(data.get('terms', ''))[:600], 'force': force,
                       'blocks': [{'key': b.key, 'sentences': list(b.sentences)} for b in blocks]}
            fingerprint = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
            stamp = utcnow()
            job = self.repository.add({'id': uuid.uuid4().hex, 'doc_id': doc_id, 'fingerprint': fingerprint,
                                       'payload': payload, 'state': 'queued', 'total': len(blocks),
                                       'created_at': stamp, 'updated_at': stamp})
            self._wake.set()
        return self.view(job)

    def action(self, job_id: str, action: str) -> dict:
        self.start()
        with self._lock:
            job = self.repository.get(job_id)
            if job is None:
                raise NotFound(_("번역 작업을 찾지 못했어요."))
            if action == 'cancel':
                self.repository.transition(job_id, ('queued', 'running', 'paused', 'failed'), 'cancelled')
            elif action == 'resume':
                if job['state'] not in ('paused', 'failed'):
                    raise InvalidInput(_("이 작업은 재개할 수 없어요."))
                if any(other['id'] != job_id and other['fingerprint'] == job['fingerprint'] and
                       other['state'] in ('queued', 'running', 'paused') for other in self.repository.list(job['doc_id'])):
                    raise InvalidInput(_("이 작업은 재개할 수 없어요."))
                payload = dict(job['payload'])
                if job['state'] == 'failed' and job['error'] == 'invalid_input':
                    payload['batch_size'] = 1
                payload.pop('missing_keys', None)
                self.repository.transition(job_id, ('paused', 'failed'), 'queued', error='', payload=payload)
                self._wake.set()
            else:
                raise InvalidInput(_("알 수 없는 작업이에요."))
            return self.view(self.repository.get(job_id))

    def _run(self) -> None:
        while not self._stop.is_set():
            self._wake.wait()
            self._wake.clear()
            for job in self.repository.list():
                if self._stop.is_set():
                    return
                if not self.repository.transition(job['id'], ('queued',), 'running'):
                    continue
                try:
                    self._inflight = job['id']
                    self._process(job)
                except ReaderError as error:
                    # Store only a stable code, never provider output (which can contain source text or credentials).
                    self.repository.transition(job['id'], ('running',), 'failed', error=error.code)
                except Exception:
                    self.repository.transition(job['id'], ('running',), 'failed', error='internal')
                finally:
                    self._inflight = None
                    self._active_batch = None

    def _process(self, job: dict) -> None:
        payload = job['payload']
        blocks = payload['blocks']
        offset = job['completed']
        while offset < len(blocks):
            batch, size = [], 0
            while offset + len(batch) < len(blocks) and len(batch) < payload.get('batch_size', 10):
                block = blocks[offset + len(batch)]
                length = sum(map(len, block['sentences']))
                if batch and size + length > 5000:
                    break
                batch.append(block)
                size += length
            missing = self._translate_batch(job, payload, batch)
            if missing is None:
                return
            if missing:
                self.repository.transition(job['id'], ('running',), None,
                                           payload={**payload, 'missing_keys': missing})
                raise InvalidInput(_("일부 문단의 번역을 받지 못했어요. 다시 시도해 주세요."))
            offset += len(batch)
            self.repository.transition(job['id'], ('running', 'paused', 'cancelled'), None, completed=offset)
        self.repository.transition(job['id'], ('running',), 'completed')

    def _running(self, job: dict) -> bool:
        current = self.repository.get(job['id'])
        return not self._stop.is_set() and current is not None and current['state'] == 'running'

    def _translate_batch(self, job: dict, payload: dict, batch: list[dict]) -> list[str] | None:
        """Keys still missing after automatic retries, or None when the job stopped or was cancelled meanwhile."""
        result = self._request(job, payload, batch)
        if result is None:
            return None
        missing = result['missing']
        for _round in range(MISSING_RETRIES):
            if not missing:
                break
            still = []
            for block in [b for b in batch if b['key'] in missing]:
                # one block per request: a reply that ignores the JSON format is still usable
                result = self._request(job, payload, [block])
                if result is None:
                    return None
                still.extend(result['missing'])
            missing = still
        return missing

    def _request(self, job: dict, payload: dict, blocks: list[dict]) -> dict | None:
        for delay in (*self.retry_delays, None):
            if not self._running(job):
                return None
            self._active_batch = (job['id'], tuple(b['key'] for b in blocks))
            try:
                return self.translate(job['doc_id'], payload, TranslationService.parse_blocks(blocks))
            except ReaderError as error:
                if delay is None or error.code not in RETRYABLE:
                    raise
            finally:
                self._active_batch = None
            if self._stop.wait(delay):
                return None
