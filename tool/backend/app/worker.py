"""Durable outbox worker for Google Drive synchronization.
Handles idempotent uploads with preallocated Drive IDs, SHA256 integrity verification,
retry loops, withdrawal race conditions, and persistent deletion tombstones.
"""
import hashlib
import logging
import time
import uuid
from typing import Any, Callable

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


def enqueue_upload_job(db_conn: Any, recording_id: str) -> str:
    job_id = str(uuid.uuid4())
    now = int(time.time())
    db_conn.execute(
        """INSERT INTO drive_sync_jobs(id, recording_id, action, status, drive_file_id, attempts, created_at, updated_at)
           VALUES (?, ?, 'upload', 'pending', NULL, 0, ?, ?)""",
        (job_id, recording_id, now, now)
    )
    return job_id


def enqueue_delete_job(db_conn: Any, recording_id: str, drive_file_id: str | None) -> str:
    job_id = str(uuid.uuid4())
    now = int(time.time())
    # Cancel pending upload jobs for this recording
    db_conn.execute(
        "UPDATE drive_sync_jobs SET status='cancelled', updated_at=? WHERE recording_id=? AND action='upload' AND status IN ('pending', 'uploading', 'retrying')",
        (now, recording_id)
    )
    if drive_file_id:
        db_conn.execute(
            """INSERT INTO drive_sync_jobs(id, recording_id, action, status, drive_file_id, attempts, created_at, updated_at)
               VALUES (?, ?, 'delete', 'pending', ?, 0, ?, ?)""",
            (job_id, recording_id, drive_file_id, now, now)
        )
    return job_id


def process_outbox(
    db_factory: Callable[[], Any],
    drive_client: Any = None,
    limit: int = 10
) -> int:
    """Processes pending and retrying outbox jobs.
    Uses preallocated Drive IDs persisted before upload, verifies download SHA256,
    and handles delete tombstones idempotently.
    """
    if drive_client is None:
        from app.drive import get_drive_client
        try:
            drive_client = get_drive_client(db_factory)
        except Exception as exc:
            logger.warning("Google Drive client unavailable: %s", exc)
            return 0

    with db_factory() as c:
        rows = c.execute(
            """SELECT id, recording_id, action, status, drive_file_id, attempts
               FROM drive_sync_jobs
               WHERE status IN ('pending', 'retrying')
               ORDER BY created_at ASC
               LIMIT ?""",
            (limit,)
        ).fetchall()
        jobs = [dict(r) for r in rows]

    processed_count = 0

    for job in jobs:
        job_id = job["id"]
        rec_id = job["recording_id"]
        action = job["action"]
        attempts = job["attempts"] + 1
        file_id = job["drive_file_id"]
        now = int(time.time())

        if action == "upload":
            with db_factory() as c:
                # Check if job was cancelled
                curr = c.execute("SELECT status FROM drive_sync_jobs WHERE id=?", (job_id,)).fetchone()
                if not curr or curr["status"] == "cancelled":
                    continue

                # Check if recording still exists (withdrawal race)
                rec = c.execute(
                    "SELECT id, sha256, format, mime, storage_key FROM recordings WHERE id=?",
                    (rec_id,)
                ).fetchone()
                if not rec:
                    c.execute("UPDATE drive_sync_jobs SET status='cancelled', updated_at=? WHERE id=?", (now, job_id))
                    if file_id:
                        try:
                            drive_client.delete(file_id)
                        except Exception:
                            pass
                    continue

                # Preallocate Drive ID if not yet allocated, and persist immediately before uploading
                if not file_id:
                    try:
                        file_id = drive_client.allocate_id()
                        c.execute(
                            "UPDATE drive_sync_jobs SET drive_file_id=?, status='uploading', updated_at=? WHERE id=?",
                            (file_id, now, job_id)
                        )
                        c.execute("UPDATE recordings SET drive_file_id=? WHERE id=?", (file_id, rec_id))
                    except Exception as exc:
                        err_msg = str(exc)
                        new_status = "failed" if attempts >= MAX_RETRIES else "retrying"
                        c.execute(
                            "UPDATE drive_sync_jobs SET status=?, attempts=?, last_error=?, updated_at=? WHERE id=?",
                            (new_status, attempts, err_msg, now, job_id)
                        )
                        continue

                # Fetch audio bytes from database or local file
                audio_row = c.execute(
                    "SELECT body FROM recording_audio WHERE recording_id=?",
                    (rec_id,)
                ).fetchone()
                audio_bytes = None
                if audio_row and audio_row[0] is not None:
                    audio_bytes = bytes(audio_row[0])
                elif rec and "storage_key" in rec and rec["storage_key"] and not str(rec["storage_key"]).startswith("sql://"):
                    from pathlib import Path
                    p = Path(rec["storage_key"])
                    if p.is_file():
                        audio_bytes = p.read_bytes()

                if audio_bytes is None:
                    err_msg = f"Audio body missing in database for recording {rec_id}"
                    c.execute(
                        "UPDATE drive_sync_jobs SET status='failed', attempts=?, last_error=?, updated_at=? WHERE id=?",
                        (attempts, err_msg, now, job_id)
                    )
                    continue

            # Perform Drive upload
            try:
                filename = f"{rec_id}.{rec['format']}"
                drive_client.put(file_id=file_id, name=filename, body=audio_bytes, mime=rec["mime"])

                # Verify SHA256 by downloading back
                downloaded = drive_client.download(file_id)
                down_sha256 = hashlib.sha256(downloaded).hexdigest()
                if down_sha256 != rec["sha256"]:
                    raise ValueError(f"Drive upload SHA256 mismatch: expected {rec['sha256']}, downloaded {down_sha256}")

                # Commit synced state, verifying no withdrawal occurred during upload
                with db_factory() as c:
                    check_rec = c.execute("SELECT id FROM recordings WHERE id=?", (rec_id,)).fetchone()
                    if not check_rec:
                        try:
                            drive_client.delete(file_id)
                        except Exception:
                            pass
                        c.execute("UPDATE drive_sync_jobs SET status='cancelled', updated_at=? WHERE id=?", (now, job_id))
                    else:
                        c.execute("UPDATE drive_sync_jobs SET status='synced', updated_at=? WHERE id=?", (now, job_id))
                        c.execute("UPDATE recordings SET drive_sync_status='synced' WHERE id=?", (rec_id,))
                        processed_count += 1
            except Exception as exc:
                err_msg = str(exc)
                new_status = "failed" if attempts >= MAX_RETRIES else "retrying"
                with db_factory() as c:
                    c.execute(
                        "UPDATE drive_sync_jobs SET status=?, attempts=?, last_error=?, updated_at=? WHERE id=?",
                        (new_status, attempts, err_msg, now, job_id)
                    )
                    if new_status == "failed":
                        c.execute("UPDATE recordings SET drive_sync_status='failed' WHERE id=?", (rec_id,))

        elif action == "delete":
            try:
                if file_id:
                    drive_client.delete(file_id)
                with db_factory() as c:
                    c.execute("UPDATE drive_sync_jobs SET status='completed', updated_at=? WHERE id=?", (now, job_id))
                processed_count += 1
            except Exception as exc:
                err_msg = str(exc)
                new_status = "failed" if attempts >= MAX_RETRIES else "retrying"
                with db_factory() as c:
                    c.execute(
                        "UPDATE drive_sync_jobs SET status=?, attempts=?, last_error=?, updated_at=? WHERE id=?",
                        (new_status, attempts, err_msg, now, job_id)
                    )

    return processed_count


def backfill_unsynced_drive_jobs(db_factory: Callable[[], Any]) -> int:
    """Finds all recordings not yet marked synced on Google Drive and enqueues upload jobs."""
    now = int(time.time())
    enqueued = 0
    with db_factory() as c:
        rows = c.execute("""
            SELECT r.id
            FROM recordings r
            WHERE (r.drive_sync_status IS NULL OR r.drive_sync_status != 'synced')
              AND NOT EXISTS (
                  SELECT 1 FROM drive_sync_jobs j
                  WHERE j.recording_id = r.id
                    AND j.action = 'upload'
                    AND j.status IN ('pending', 'uploading', 'retrying', 'synced')
              )
        """).fetchall()

        for row in rows:
            rec_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
            job_id = str(uuid.uuid4())
            c.execute(
                """INSERT INTO drive_sync_jobs(id, recording_id, action, status, drive_file_id, attempts, created_at, updated_at)
                   VALUES (?, ?, 'upload', 'pending', NULL, 0, ?, ?)""",
                (job_id, rec_id, now, now)
            )
            c.execute(
                "UPDATE recordings SET drive_sync_status = 'pending' WHERE id = ? AND (drive_sync_status IS NULL OR drive_sync_status = 'disabled')",
                (rec_id,)
            )
            enqueued += 1

    return enqueued


def process_all_outbox(
    db_factory: Callable[[], Any],
    drive_client: Any = None,
    max_total: int = 50
) -> int:
    """Runs process_outbox in loops until queue is drained or max_total is reached."""
    total = 0
    while total < max_total:
        limit = min(10, max_total - total)
        count = process_outbox(db_factory, drive_client=drive_client, limit=limit)
        if count == 0:
            break
        total += count
    return total

