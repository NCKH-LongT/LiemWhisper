"""Serialize Drive mutations across threads and backend processes."""
import os
import threading
from contextlib import contextmanager
from functools import wraps

_mutex = threading.RLock()
_local = threading.local()

class DriveBusy(Exception):
    pass


@contextmanager
def drive_lock(db_factory, blocking=True):
    # Reentrant because a full sync invokes the individually protected helpers.
    if not _mutex.acquire(blocking=blocking):
        raise DriveBusy()
    try:
        if getattr(_local, "active", False):
            yield
            return
        from app.database import get_data_root, is_postgres
        with _process_lock(db_factory, is_postgres(), get_data_root(), blocking):
            _local.active = True
            try:
                yield
            finally:
                _local.active = False
    finally:
        _mutex.release()


@contextmanager
def _process_lock(db_factory, postgres, root, blocking=True):
    if postgres:
        # Dedicated transaction also works with transaction-pooled connections.
        # Commit/rollback or a disconnected worker releases the lock automatically.
        with db_factory() as c:
            if blocking:
                c.execute("SELECT pg_advisory_xact_lock(742193861)")
            elif not c.execute("SELECT pg_try_advisory_xact_lock(742193861)").fetchone()[0]:
                raise DriveBusy()
            yield
        return
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".drive-sync.lock").open("a+b") as handle:
        if os.name == "nt":
            import msvcrt
            handle.seek(0, 2)
            if handle.tell() == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            try:
                msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK if blocking else msvcrt.LK_NBLCK, 1)
            except OSError as exc:
                raise DriveBusy() from exc
        else:
            import fcntl
            try:
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB))
            except BlockingIOError as exc:
                raise DriveBusy() from exc
        try:
            yield
        finally:
            if os.name == "nt":
                handle.seek(0)
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def serialized_drive(fn):
    @wraps(fn)
    def wrapped(db_factory, *args, **kwargs):
        with drive_lock(db_factory):
            return fn(db_factory, *args, **kwargs)
    return wrapped
