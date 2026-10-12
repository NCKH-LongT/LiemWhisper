"""Storage subsystem supporting local disk, full SQL audio, and dual sql_drive modes.
Provides HTTP Range streaming responses and outbox synchronization hooks.
"""
import re
from pathlib import Path
from typing import Any
from fastapi import HTTPException
from starlette.responses import Response


class RangeNotSatisfiableError(Exception):
    def __init__(self, total: int):
        self.total = total


def validate_storage_backend(storage_mode: str) -> None:
    if storage_mode == "drive":
        raise HTTPException(
            status_code=503,
            detail="STORAGE_BACKEND='drive' is deprecated and unsupported. Use 'sql_drive' for dual SQL + Google Drive mode."
        )
    if storage_mode not in ("local", "sql", "sql_drive"):
        raise HTTPException(
            status_code=503,
            detail=f"Unsupported storage backend: '{storage_mode}'"
        )


def store_audio_bytes(
    recording_id: str,
    body: bytes,
    ext: str,
    mime: str,
    storage_mode: str,
    db_conn: Any,
    audio_dir: Path
) -> str:
    validate_storage_backend(storage_mode)

    if storage_mode == "local":
        audio_dir.mkdir(parents=True, exist_ok=True)
        path = audio_dir / f"{recording_id}.{ext}"
        path.write_bytes(body)
        return str(path)

    # 'sql' or 'sql_drive'
    db_conn.execute(
        "INSERT INTO recording_audio(recording_id, body) VALUES (?, ?)",
        (recording_id, body)
    )

    if storage_mode == "sql_drive":
        from app.worker import enqueue_upload_job
        enqueue_upload_job(db_conn, recording_id)

    return f"sql://{recording_id}"


def get_audio_bytes(
    recording_id: str,
    storage_key: str,
    storage_mode: str,
    db_conn: Any
) -> bytes:
    if storage_key.startswith("sql://") or storage_mode in ("sql", "sql_drive"):
        row = db_conn.execute(
            "SELECT body FROM recording_audio WHERE recording_id=?",
            (recording_id,)
        ).fetchone()
        if not row or row[0] is None:
            raise FileNotFoundError(f"Audio not found in database for recording {recording_id}")
        return bytes(row[0])

    p = Path(storage_key)
    if not p.is_file():
        raise FileNotFoundError(f"Audio file missing on disk: {storage_key}")
    return p.read_bytes()


_RANGE_RE = re.compile(r"^bytes=(\d*)-(\d*)$")


def parse_range_header(range_header: str, total_bytes: int) -> tuple[int, int] | None:
    m = _RANGE_RE.match(range_header.strip())
    if not m:
        return None

    raw_start, raw_end = m.group(1), m.group(2)

    if not raw_start and not raw_end:
        return None

    if not raw_start:
        # Suffix range: bytes=-500 (last 500 bytes)
        suffix_length = int(raw_end)
        if suffix_length <= 0:
            raise RangeNotSatisfiableError(total_bytes)
        start = max(0, total_bytes - suffix_length)
        end = total_bytes - 1
        return start, end

    start = int(raw_start)
    if raw_end:
        end = int(raw_end)
    else:
        end = total_bytes - 1

    if total_bytes == 0 or start >= total_bytes or end < start:
        raise RangeNotSatisfiableError(total_bytes)

    end = min(end, total_bytes - 1)
    return start, end


def stream_audio_response(body: bytes, mime: str, range_header: str | None = None) -> Response:
    total_len = len(body)

    if range_header:
        try:
            r = parse_range_header(range_header, total_len)
            if r is not None:
                start, end = r
                chunk = body[start:end + 1]
                headers = {
                    "Content-Range": f"bytes {start}-{end}/{total_len}",
                    "Accept-Ranges": "bytes",
                    "Content-Length": str(len(chunk)),
                    "Content-Type": mime,
                }
                return Response(
                    content=chunk,
                    status_code=206,
                    headers=headers,
                    media_type=mime
                )
        except RangeNotSatisfiableError:
            return Response(
                status_code=416,
                headers={
                    "Content-Range": f"bytes */{total_len}",
                    "Accept-Ranges": "bytes",
                }
            )

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(total_len),
        "Content-Type": mime,
    }
    return Response(content=body, status_code=200, headers=headers, media_type=mime)
