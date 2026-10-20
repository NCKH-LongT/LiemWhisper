"""Persistent cleanup progress; HTTP requests never wait on Drive operations."""
import json
import logging
from threading import Thread
import time
import uuid

from app.drive_lock import DriveBusy, drive_lock

STALE_SECONDS = 300


def _initialize(db):
    with db() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS drive_cleanup_state (
            id TEXT PRIMARY KEY, job_id TEXT, status TEXT NOT NULL,
            phase TEXT NOT NULL, processed INTEGER NOT NULL, total INTEGER NOT NULL,
            result TEXT, updated_at INTEGER NOT NULL)""")
        c.execute("""INSERT INTO drive_cleanup_state VALUES
            ('default', '', 'idle', '', 0, 0, NULL, 0) ON CONFLICT(id) DO NOTHING""")


def cleanup_status(db):
    _initialize(db)
    with db() as c:
        c.execute("""UPDATE drive_cleanup_state SET status='failed',
            phase='Tác vụ bị gián đoạn. Vui lòng chạy lại để tiếp tục an toàn.'
            WHERE id='default' AND status='running' AND updated_at < ?""",
            (int(time.time()) - STALE_SECONDS,))
        row = dict(c.execute("SELECT * FROM drive_cleanup_state WHERE id='default'").fetchone())
    if row["result"]:
        row["result"] = json.loads(row["result"])
    return row


def start_cleanup(db):
    cleanup_status(db)
    job_id = uuid.uuid4().hex
    with db() as c:
        claimed = c.execute("""UPDATE drive_cleanup_state SET job_id=?, status='running',
            phase='Đang chờ lượt đồng bộ Drive', processed=0, total=0, result=NULL, updated_at=?
            WHERE id='default' AND status != 'running' RETURNING job_id""",
            (job_id, int(time.time()))).fetchone()
    if claimed:
        try:
            Thread(target=_run_cleanup, args=(db, job_id), daemon=True).start()
        except Exception:
            _update(db, job_id, "failed", "Không thể khởi động tác vụ. Vui lòng thử lại.", 0, 0)
            raise
    return cleanup_status(db)


def _update(db, job_id, status, phase, processed, total, result=None):
    with db() as c:
        c.execute("""UPDATE drive_cleanup_state SET status=?, phase=?, processed=?,
            total=?, result=?, updated_at=? WHERE id='default' AND job_id=?""",
            (status, phase, processed, total, json.dumps(result) if result else None,
             int(time.time()), job_id))


def _run_cleanup(db, job_id):
    from app.drive import get_drive_client
    from app.drive_cleanup import cleanup_duplicates
    processed = total = 0
    def report(phase, count, size):
        nonlocal processed, total
        processed, total = count, size
        _update(db, job_id, "running", phase, count, size)
    try:
        while True:
            try:
                with drive_lock(db, blocking=False):
                    report("Đang kết nối Google Drive", 0, 0)
                    result = cleanup_duplicates(db, get_drive_client(db), progress=report)
                    _update(db, job_id, "success", result["message"], total, total, result)
                    return
            except DriveBusy:
                report("Đang chờ lượt đồng bộ Drive", 0, 0)
                time.sleep(2)
    except Exception:
        logging.getLogger(__name__).exception("Drive cleanup background job failed")
        _update(db, job_id, "failed",
                "Không thể hoàn tất dọn trùng. Kiểm tra kết nối Drive và log backend; các mục chưa xác minh được giữ lại.",
                processed, total)
