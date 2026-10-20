"""Durable outbox worker for Google Drive synchronization.
Handles idempotent uploads with preallocated Drive IDs, SHA256 integrity verification,
retry loops, withdrawal race conditions, and persistent deletion tombstones.
"""
import csv
import hashlib
import io
import logging
import re
import time
import uuid
from typing import Any, Callable
from app.drive_lock import serialized_drive

logger = logging.getLogger(__name__)

MAX_RETRIES = 5


def participant_folder(db_factory, client, participant_id, name):
    """Persist the folder ID before creating it, so crash/retry reuses that ID."""
    if not hasattr(client, "get_or_create_subfolder"):
        return None
    with db_factory() as c:
        row = c.execute("SELECT drive_folder_id FROM participants WHERE id=?", (participant_id,)).fetchone()
        if not row:
            raise RuntimeError("Participant no longer exists")
        folder_id = row["drive_folder_id"]
        if not folder_id:
            if hasattr(client, "ensure_folder"):
                folder_id = client.allocate_id()
            else:
                folder_id = client.get_or_create_subfolder(name)
            c.execute("UPDATE participants SET drive_folder_id=? WHERE id=?", (folder_id, participant_id))
    if hasattr(client, "ensure_folder"):
        client.ensure_folder(folder_id, name)
    return folder_id


def enqueue_upload_job(db_conn: Any, recording_id: str) -> str:
    # Check if an active or synced upload job already exists
    existing = db_conn.execute(
        "SELECT id FROM drive_sync_jobs WHERE recording_id=? AND action='upload' AND status IN ('pending', 'uploading', 'retrying', 'synced')",
        (recording_id,)
    ).fetchone()
    if existing:
        return existing[0] if isinstance(existing, (tuple, list)) else existing["id"]

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


def get_prompt_question_number(db_conn: Any, course_id: str | None, prompt_id: str | None) -> int:
    """Returns the 1-based question number (1, 2, 3...) of prompt_id in course_id,
    strictly matching the student studio tasks order: ORDER BY created_at ASC, id ASC.
    """
    if not course_id or not prompt_id:
        return 1

    # First check published prompts (active student tasks order)
    rows = db_conn.execute(
        "SELECT id FROM prompts WHERE course_id = ? AND published = 1 ORDER BY created_at ASC, id ASC",
        (course_id,)
    ).fetchall()
    prompt_ids = [r[0] if isinstance(r, (tuple, list)) else r["id"] for r in rows]
    if prompt_id in prompt_ids:
        return prompt_ids.index(prompt_id) + 1

    # Fallback to all course prompts if prompt was unpublished later
    all_rows = db_conn.execute(
        "SELECT id FROM prompts WHERE course_id = ? ORDER BY created_at ASC, id ASC",
        (course_id,)
    ).fetchall()
    all_ids = [r[0] if isinstance(r, (tuple, list)) else r["id"] for r in all_rows]
    if prompt_id in all_ids:
        return all_ids.index(prompt_id) + 1

    return 1


@serialized_drive
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
               WHERE status IN ('pending', 'retrying', 'uploading')
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
                if not curr or curr["status"] not in ("pending", "retrying", "uploading"):
                    continue

                # Check if recording still exists (withdrawal race)
                rec = c.execute("""
                    SELECT r.id, r.participant_id, r.prompt_id, r.sha256, r.format, r.mime, r.storage_key, r.drive_file_id,
                           p.participant_code, p.name as participant_name, p.email as participant_email, p.drive_folder_id,
                           pr.course_id
                    FROM recordings r
                    LEFT JOIN participants p ON p.id = r.participant_id
                    LEFT JOIN prompts pr ON pr.id = r.prompt_id
                    WHERE r.id = ?
                """, (rec_id,)).fetchone()
                if not rec:
                    c.execute("UPDATE drive_sync_jobs SET status='cancelled', updated_at=? WHERE id=?", (now, job_id))
                    if file_id:
                        try:
                            drive_client.delete(file_id)
                        except Exception:
                            pass
                    continue

                # Question order within the course
                q_order = get_prompt_question_number(c, rec["course_id"], rec["prompt_id"]) if rec else 1

                code = (rec["participant_code"] or "").strip() if rec else ""
                if not code and rec and rec["participant_id"]:
                    code = f"SV_{rec['participant_id'][:6]}"
                name = (rec["participant_name"] or "").strip() if rec else ""
                email = (rec["participant_email"] or "").strip() if rec else ""

                if code and name:
                    folder_name = f"{code} - {name}"
                elif code and email:
                    folder_name = f"{code} - {email}"
                elif code:
                    folder_name = f"{code}"
                else:
                    folder_name = "Chua_phan_loai"

                cau_label = f"Cau{q_order:02d}"
                filename = f"{code}_{cau_label}_{rec_id[:8]}.{rec['format']}" if code else f"{rec_id}.{rec['format']}"

                # Reuse existing file_id from recording if not attached to job
                if rec and rec.get("drive_file_id"):
                    file_id = rec["drive_file_id"]
                    c.execute("UPDATE drive_sync_jobs SET drive_file_id=? WHERE id=?", (file_id, job_id))

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

            # Subfolder in Drive for participant - reuse stored folder_id if available
            # Perform Drive upload
            try:
                parent_folder_id = participant_folder(db_factory, drive_client, rec["participant_id"], folder_name)
                if parent_folder_id and hasattr(drive_client, "get_or_create_subfolder"):
                    actual_file_id = drive_client.put(file_id=file_id, name=filename, body=audio_bytes, mime=rec["mime"], parent_id=parent_folder_id)
                else:
                    actual_file_id = drive_client.put(file_id=file_id, name=filename, body=audio_bytes, mime=rec["mime"])

                if actual_file_id and actual_file_id != file_id:
                    file_id = actual_file_id

                # Verify SHA256 by downloading back
                downloaded = drive_client.download(file_id)
                down_sha256 = hashlib.sha256(downloaded).hexdigest()
                if down_sha256 != rec["sha256"]:
                    raise ValueError(f"Drive upload SHA256 mismatch: expected {rec['sha256']}, downloaded {down_sha256}")

                # Commit synced state, verifying no withdrawal occurred during upload
                with db_factory() as c:
                    check_rec = c.execute("SELECT id, sha256 FROM recordings WHERE id=?", (rec_id,)).fetchone()
                    if not check_rec:
                        try:
                            drive_client.delete(file_id)
                        except Exception:
                            pass
                        c.execute("UPDATE drive_sync_jobs SET status='cancelled', updated_at=? WHERE id=?", (now, job_id))
                    elif check_rec["sha256"] != rec["sha256"]:
                        # A newer recording arrived while the old bytes were uploading.
                        c.execute("UPDATE drive_sync_jobs SET status='pending', attempts=0, updated_at=? WHERE id=?", (now, job_id))
                    else:
                        c.execute("UPDATE drive_sync_jobs SET status='synced', drive_file_id=?, updated_at=? WHERE id=?", (file_id, now, job_id))
                        c.execute("UPDATE recordings SET drive_sync_status='synced', drive_file_id=? WHERE id=?", (file_id, rec_id))
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


@serialized_drive
def backfill_unsynced_drive_jobs(db_factory: Callable[[], Any]) -> int:
    """Finds all recordings not yet marked synced on Google Drive and enqueues upload jobs."""
    now = int(time.time())
    enqueued = 0
    with db_factory() as c:
        rows = c.execute("""
            SELECT r.id, r.drive_file_id
            FROM recordings r
            WHERE (r.drive_sync_status IS NULL OR r.drive_sync_status NOT IN ('synced', 'failed'))
              AND NOT EXISTS (
                  SELECT 1 FROM drive_sync_jobs j
                  WHERE j.recording_id = r.id
                    AND j.action = 'upload'
                    AND j.status IN ('pending', 'uploading', 'retrying', 'synced')
              )
        """).fetchall()

        for row in rows:
            rec_id = row[0] if isinstance(row, (tuple, list)) else row["id"]
            existing_fid = row[1] if isinstance(row, (tuple, list)) else row.get("drive_file_id")
            job_id = str(uuid.uuid4())
            c.execute(
                """INSERT INTO drive_sync_jobs(id, recording_id, action, status, drive_file_id, attempts, created_at, updated_at)
                   VALUES (?, ?, 'upload', 'pending', ?, 0, ?, ?)""",
                (job_id, rec_id, existing_fid, now, now)
            )
            c.execute(
                "UPDATE recordings SET drive_sync_status = 'pending' WHERE id = ? AND (drive_sync_status IS NULL OR drive_sync_status = 'disabled')",
                (rec_id,)
            )
            enqueued += 1

    return enqueued


@serialized_drive
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

    # If real Drive client is available, organize existing files into subfolders and update CSV index
    client = drive_client
    if client is None:
        try:
            from app.drive import get_drive_client
            client = get_drive_client(db_factory)
        except Exception:
            pass

    if total and client and hasattr(client, "upload_or_update_file"):
        try:
            sync_drive_manifest_csv(db_factory, client)
        except Exception as exc:
            logger.warning("Error organizing Drive files / updating manifest CSV: %s", exc)

    return total


@serialized_drive
def sync_drive_manifest_csv(db_factory: Callable[[], Any], drive_client: Any) -> None:
    """Creates or updates a clean UTF-8 CSV lookup manifest directly in the Google Drive root folder."""
    if not hasattr(drive_client, "upload_or_update_file"):
        return

    with db_factory() as c:
        rows = c.execute("""
            SELECT r.id as recording_id,
                   r.prompt_id,
                   pr.course_id,
                   COALESCE(p.participant_code, '') as participant_code,
                   COALESCE(p.name, '') as participant_name,
                   COALESCE(p.email, '') as participant_email,
                   COALESCE(pr.text, '') as prompt_text,
                   r.duration_seconds,
                   r.format,
                   r.created_at,
                   r.drive_file_id
            FROM recordings r
            LEFT JOIN participants p ON p.id = r.participant_id
            LEFT JOIN prompts pr ON pr.id = r.prompt_id
            WHERE r.drive_sync_status = 'synced' AND r.drive_file_id IS NOT NULL
            ORDER BY p.participant_code ASC, r.created_at ASC
        """).fetchall()

        if not rows:
            return

        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow([
            "STT",
            "Mã Thí Sinh",
            "Họ và Tên",
            "Email",
            "Thư Mục Drive",
            "Tên File Drive",
            "Câu Hỏi",
            "Thời Lượng (giây)",
            "Định Dạng",
            "Thời Gian Thu Âm",
            "Link Nghe Trực Tiếp Trên Drive"
        ])

        for idx, r in enumerate(rows, 1):
            code = (r["participant_code"] or "").strip() or "Chua_cap_ma"
            name = (r["participant_name"] or "").strip()
            email = (r["participant_email"] or "").strip()
            folder_display = f"{code} - {name}" if name else f"{code} - {email}" if email else code
            short_id = (r["recording_id"] or "")[:8]
            q_order = get_prompt_question_number(c, r["course_id"], r["prompt_id"])
            cau_label = f"Cau{q_order:02d}"
            file_name_display = f"{code}_{cau_label}_{short_id}.{r['format']}"
            dt_str = time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(r['created_at'])) if r['created_at'] else ''
            file_id = r['drive_file_id'] or ''
            drive_link = f"https://drive.google.com/file/d/{file_id}/view" if file_id else ''

            prompt_clean = (r['prompt_text'] or '').replace('\n', ' ')[:100]
            writer.writerow([
                idx,
                code,
                name or 'Không tên',
                email,
                folder_display,
                file_name_display,
                f"Câu {q_order}: {prompt_clean}",
                r['duration_seconds'],
                r['format'],
                dt_str,
                drive_link
            ])

    csv_bytes = ("\ufeff" + buf.getvalue()).encode("utf-8")
    try:
        drive_client.upload_or_update_file(
            filename="Danh_sach_ban_thu.csv",
            body=csv_bytes,
            mime="text/csv; charset=utf-8"
        )
    except Exception as exc:
        logger.warning("Failed to update Danh_sach_ban_thu.csv on Drive: %s", exc)


@serialized_drive
def organize_existing_drive_files(db_factory: Callable[[], Any], drive_client: Any) -> int:
    """Moves and renames existing Drive files into their participant subfolders."""
    if not hasattr(drive_client, "move_and_rename_file") or not hasattr(drive_client, "get_or_create_subfolder"):
        return 0

    organized = 0
    with db_factory() as c:
        rows = c.execute("""
            SELECT r.id as rec_id, r.participant_id, r.prompt_id, r.format, r.drive_file_id,
                   p.participant_code, p.name as participant_name, p.email as participant_email,
                   pr.course_id
            FROM recordings r
            LEFT JOIN participants p ON p.id = r.participant_id
            LEFT JOIN prompts pr ON pr.id = r.prompt_id
            WHERE r.drive_sync_status = 'synced' AND r.drive_file_id IS NOT NULL
        """).fetchall()

    subfolder_cache = {}

    for r in rows:
        rec_id = r["rec_id"]
        file_id = r["drive_file_id"]
        if not file_id:
            continue

        code = (r["participant_code"] or "").strip() or f"SV{r['participant_id'][:6]}"
        name = (r["participant_name"] or "").strip()
        email = (r["participant_email"] or "").strip()

        if name:
            folder_name = f"{code} - {name}"
        elif email:
            folder_name = f"{code} - {email}"
        else:
            folder_name = f"{code}"

        if r["participant_id"] not in subfolder_cache:
            try:
                subfolder_cache[r["participant_id"]] = participant_folder(db_factory, drive_client, r["participant_id"], folder_name)
            except Exception:
                continue
        subfolder_id = subfolder_cache[r["participant_id"]]
        if subfolder_id and r.get("participant_id"):
            with db_factory() as c_up:
                c_up.execute(
                    "UPDATE participants SET drive_folder_id=? WHERE id=? AND (drive_folder_id IS NULL OR drive_folder_id='')",
                    (subfolder_id, r["participant_id"])
                )

        # Calculate question order
        with db_factory() as c:
            q_order = get_prompt_question_number(c, r["course_id"], r["prompt_id"])

        cau_label = f"Cau{q_order:02d}"
        new_filename = f"{code}_{cau_label}_{rec_id[:8]}.{r['format']}"

        try:
            ok = drive_client.move_and_rename_file(file_id=file_id, new_name=new_filename, target_parent_id=subfolder_id)
            if ok:
                organized += 1
        except Exception:
            pass

    return organized

