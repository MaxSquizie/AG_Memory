"""Observational live events for CLI/GUI oracle runs; never model inputs.

The full prompt/response and actual observations remain in the ordinary run
artifacts. This bounded, flushed stream is a view of those real operations.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from datetime import datetime, timezone
from pathlib import Path
import json
import sys
import threading
import time

PREFIX = 'V7_PROGRESS '
SCHEMA = 'v7-oracle-progress-1'
PREVIEW_LIMIT = 4096
EVENT_LIMIT = 65536
_context = ContextVar('formalizer_v7_progress_context', default={})
_active = None


def _bounded(value, depth=0):
    if depth > 10:
        return '<nested value omitted>'
    if isinstance(value, str):
        return value[:PREVIEW_LIMIT]
    if isinstance(value, dict):
        result = {}
        for key, item in list(value.items())[:100]:
            key = str(key)
            result[key] = _bounded(item, depth + 1)
            if isinstance(item, str) and len(item) > PREVIEW_LIMIT:
                result[key + '_truncated'] = True
                result[key + '_chars'] = len(item)
        if len(value) > 100:
            result['_omitted_fields'] = len(value) - 100
        return result
    if isinstance(value, (list, tuple)):
        items = [_bounded(item, depth + 1) for item in value[:64]]
        if len(value) > 64:
            items.append({'_omitted_items': len(value) - 64})
        return items
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)[:PREVIEW_LIMIT]


class ProgressEmitter:
    def __init__(self, path, *, stdout=False):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open('w', encoding='utf-8')
        self.stdout = stdout
        self.started = time.monotonic()
        self.seq = 0
        self.lock = threading.Lock()
        self.stats = {'requests_started': 0, 'requests_finished': 0,
                      'requests_failed': 0}

    def emit(self, event, **fields):
        with self.lock:
            self.seq += 1
            if event == 'request_started':
                self.stats['requests_started'] += 1
            elif event == 'request_finished':
                self.stats['requests_finished'] += 1
                if fields.get('status') == 'ERROR' or fields.get('error'):
                    self.stats['requests_failed'] += 1
            row = _bounded({**_context.get(), **fields})
            row.update(schema_version=SCHEMA, event=event, seq=self.seq,
                       timestamp=datetime.now(timezone.utc).isoformat(),
                       elapsed_seconds=round(time.monotonic() - self.started, 3),
                       **self.stats)
            # Preserve transport timing separately from total run time.
            if 'elapsed_seconds' in fields:
                row['request_elapsed_seconds'] = fields['elapsed_seconds']
            raw = json.dumps(row, ensure_ascii=False, separators=(',', ':'),
                             allow_nan=False)
            # Large IR/AH checkpoints can have many short fields. Limit the
            # whole event as well as each leaf, while retaining envelope and
            # counters. The complete objects stay in the actual trace/WAL.
            if len(raw.encode('utf-8')) > EVENT_LIMIT:
                protected = {'schema_version', 'event', 'seq', 'timestamp', 'case_id',
                    'step_id', 'action', 'status', 'execution_status', 'completed',
                    'total', 'passed', 'failed', 'blocked', *self.stats}
                for key in sorted(set(row) - protected,
                                  key=lambda k: len(json.dumps(row[k], ensure_ascii=False)),
                                  reverse=True):
                    value = json.dumps(row[key], ensure_ascii=False)
                    if len(value) <= PREVIEW_LIMIT:
                        continue
                    row[key] = value[:PREVIEW_LIMIT]
                    row[key + '_truncated'] = True
                    row[key + '_serialized_chars'] = len(value)
                    raw = json.dumps(row, ensure_ascii=False, separators=(',', ':'),
                                     allow_nan=False)
                    if len(raw.encode('utf-8')) <= EVENT_LIMIT:
                        break
                if len(raw.encode('utf-8')) > EVENT_LIMIT:
                    omitted = []
                    for key in sorted(set(row) - protected,
                                      key=lambda k: len(json.dumps(row[k], ensure_ascii=False)),
                                      reverse=True):
                        omitted.append(key)
                        row.pop(key)
                        row['_omitted_progress_fields'] = omitted[:64]
                        raw = json.dumps(row, ensure_ascii=False, separators=(',', ':'),
                                         allow_nan=False)
                        if len(raw.encode('utf-8')) <= EVENT_LIMIT:
                            break
            self.file.write(raw + '\n')
            self.file.flush()
            if self.stdout:
                try:
                    print(PREFIX + raw, flush=True)
                except UnicodeEncodeError:
                    # Older Windows consoles may not be UTF-8. JSON escapes
                    # preserve the same payload rather than aborting a run.
                    print(PREFIX + json.dumps(row, ensure_ascii=True,
                                             separators=(',', ':')), flush=True)
            return row

    def close(self):
        with self.lock:
            if not self.file.closed:
                self.file.close()


def configure(path, *, stdout=False):
    global _active
    if _active is not None:
        _active.close()
    _active = ProgressEmitter(path, stdout=stdout)
    return _active


def close():
    global _active
    active, _active = _active, None
    if active is not None:
        active.close()


@contextmanager
def context(**fields):
    token = _context.set({**_context.get(), **fields})
    try:
        yield
    finally:
        _context.reset(token)


def emit(event, **fields):
    """No-op outside a configured run; observation failures cannot affect it."""
    if _active is None:
        return None
    try:
        return _active.emit(event, **fields)
    except (OSError, ValueError, TypeError):
        return None
