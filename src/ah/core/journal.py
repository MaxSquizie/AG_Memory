"""Checksummed atomic journal frames and a process-shared, reentrant writer lock."""
from __future__ import annotations
import hashlib
import json
import os
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from threading import RLock, local


class JournalIntegrityError(RuntimeError):
    pass

_LOCKS: dict[str, RLock] = {}
_LOCKS_GUARD = RLock()
_LOCAL = local()


def _fsync_dir_best_effort(path: Path) -> None:
    try:
        fd = os.open(str(path.parent), os.O_RDONLY)
        try: os.fsync(fd)
        finally: os.close(fd)
    except OSError:
        pass


def canonical_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


class JournalChannel:
    def __init__(self, path: str | Path):
        self._path = Path(path).resolve()
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._key = str(self._path)
        with _LOCKS_GUARD:
            self._lock = _LOCKS.setdefault(self._key, RLock())
        with self.atomic():
            if not self._path.exists():
                self._path.touch()
                _fsync_dir_best_effort(self._path)
            self._head = self.recover()

    @contextmanager
    def atomic(self):
        """Shared boundary for batch, goals, binding CAS and retraction (DB-N)."""
        with self._lock:
            held = getattr(_LOCAL, 'held', {})
            _LOCAL.held = held
            if self._key in held:
                held[self._key] += 1
                try: yield
                finally: held[self._key] -= 1
                return
            lockpath = self._path.with_suffix(self._path.suffix + '.lock')
            with open(lockpath, 'a+b') as fh:
                if os.name == 'nt':
                    import msvcrt
                    if fh.tell() == 0:
                        fh.write(b'0'); fh.flush()
                    fh.seek(0); msvcrt.locking(fh.fileno(), msvcrt.LK_LOCK, 1)
                else:
                    import fcntl
                    fcntl.flock(fh.fileno(), fcntl.LOCK_EX)
                held[self._key] = 1
                reads = getattr(_LOCAL, 'reads', {})
                _LOCAL.reads = reads
                try: yield
                finally:
                    # Never carry verified frames past the outer writer lock.
                    reads.pop(self._key, None)
                    del held[self._key]
                    if os.name == 'nt':
                        fh.seek(0); msvcrt.locking(fh.fileno(), msvcrt.LK_UNLCK, 1)
                    else:
                        fcntl.flock(fh.fileno(), fcntl.LOCK_UN)

    def _stamp(self):
        stat = self._path.stat()
        return (stat.st_dev, stat.st_ino, stat.st_size, stat.st_mtime_ns, stat.st_ctime_ns)

    def _read(self, repair_tail=False):
        # A commit calls head/scan/append many times while holding this same
        # process-shared lock. Re-parsing and re-hashing a book-sized BATCH on
        # every nested call is unnecessary. The cache lasts only this outer
        # critical section; file changes invalidate it even within the lock.
        reads = getattr(_LOCAL, 'reads', {})
        cached = reads.get(self._key)
        if cached is not None and self._path.exists() and cached[0] == self._stamp():
            return cached[1]
        raw = self._path.read_bytes() if self._path.exists() else b''
        chunks = raw.splitlines(keepends=True)
        records = []; offset = 0
        for i, line in enumerate(chunks):
            if not line.endswith(b'\n'):
                if i != len(chunks)-1 or not repair_tail:
                    raise JournalIntegrityError('INTEGRITY_ERROR: incomplete journal tail')
                with open(self._path, 'r+b') as f:
                    f.truncate(offset); f.flush(); os.fsync(f.fileno())
                break
            try:
                rec = json.loads(line)
                if not isinstance(rec, dict) or type(rec.get('seq')) is not int or rec['seq'] != len(records)+1:
                    raise ValueError('noncontiguous seq')
                if not isinstance(rec.get('payload'), dict) or not isinstance(rec.get('channel'), str):
                    raise ValueError('invalid record schema')
                checksum = rec.get('checksum')
                body = {k:v for k,v in rec.items() if k != 'checksum'}
                if checksum is not None and checksum != hashlib.sha256(canonical_json(body).encode()).hexdigest():
                    raise ValueError('checksum mismatch')
            except (ValueError, TypeError, UnicodeDecodeError) as exc:
                raise JournalIntegrityError(f'INTEGRITY_ERROR: journal frame {i+1}: {exc}') from exc
            records.append(rec); offset += len(line)
        if self._key in getattr(_LOCAL, 'held', {}):
            reads[self._key] = (self._stamp(), records)
        return records

    def append(self, channel: str, payload: dict, run_id: str = '') -> int:
        with self.atomic():
            records = self._read(repair_tail=True)
            seq = len(records)+1
            body = {'seq':seq, 'channel':channel, 'run_id':run_id, 'payload':payload}
            checksum = hashlib.sha256(canonical_json(body).encode()).hexdigest()
            encoded = (canonical_json({**body,'checksum':checksum})+'\n').encode('utf-8')
            # Never publish an incremented head before fsync succeeded.
            reads = getattr(_LOCAL, 'reads', {})
            reads.pop(self._key, None)  # failed/partial append must be re-read
            with open(self._path,'ab') as f:
                f.write(encoded); f.flush(); os.fsync(f.fileno())
            # Cache the exact durable representation, not caller-owned payloads.
            records.append(json.loads(encoded))
            reads[self._key] = (self._stamp(), records)
            self._head = seq
            return seq

    def read_global_head(self):
        with self.atomic(): return len(self._read(repair_tail=True))

    def scan_unprocessed(self, after_seq=0, channel=None, *, payload_kinds=None):
        with self.atomic():
            # Verify the complete stream first, then copy only requested rows.
            # In particular, terminal/ownership readers do not need a deep
            # copy of every document-sized BATCH merely to skip it afterwards.
            kinds = frozenset(payload_kinds) if payload_kinds is not None else None
            return deepcopy([r for r in self._read(repair_tail=True)
                             if r['seq'] > after_seq and (channel is None or r['channel']==channel)
                             and (kinds is None or r['payload'].get('kind') in kinds)])

    def recover(self):
        with self.atomic():
            self._head = len(self._read(repair_tail=True))
            return self._head

    def _iter_valid(self):
        yield from self.scan_unprocessed()

    @property
    def path(self): return self._path
