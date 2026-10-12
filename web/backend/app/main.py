"""LiemWhisper recording-collection API — Production-ready collection platform.

Supports multi-format audio (WebM, MP4/AAC, WAV, OGG), range-request streaming,
bulk prompt import, reviewer studio, real-time stats, and export manifest/archive.
"""
import csv
import hashlib
import io
import json
import os
import re
import secrets
import sqlite3
import time
import uuid
import zipfile
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DATA_ROOT = PROJECT_ROOT / "private-data"
ROOT = Path(os.getenv("DATA_ROOT", str(DEFAULT_DATA_ROOT))).resolve()
DB = ROOT / "collection.sqlite3"
STORAGE = os.getenv("STORAGE_BACKEND", "local")
MAX_BYTES = int(os.getenv("MAX_AUDIO_BYTES", "15000000"))  # 15MB limit
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "liemwhisper-admin-secret-2026")
ORIGINS_ENV = os.getenv("WEB_PUBLIC_URL", "*")
ALLOWED_ORIGINS = [o.strip() for o in ORIGINS_ENV.split(",") if o.strip()] or ["*"]

ROOT.mkdir(parents=True, exist_ok=True)
AUDIO_DIR = ROOT / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="LiemWhisper Collection API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if "*" not in ALLOWED_ORIGINS else ["*"],
    allow_credentials=True if "*" not in ALLOWED_ORIGINS else False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@contextmanager
def db():
    conn = sqlite3.connect(DB, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.execute("PRAGMA journal_mode=WAL")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS courses(
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            created_at INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS prompts(
            id TEXT PRIMARY KEY,
            course_id TEXT NOT NULL REFERENCES courses(id) ON DELETE CASCADE,
            text TEXT NOT NULL,
            language TEXT NOT NULL DEFAULT 'vi-en',
            target_terms TEXT DEFAULT '[]',
            difficulty TEXT DEFAULT 'normal',
            category TEXT DEFAULT '',
            published INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL DEFAULT 0
        );
        CREATE TABLE IF NOT EXISTS participants(
            id TEXT PRIMARY KEY,
            token_hash TEXT NOT NULL UNIQUE,
            participant_code TEXT DEFAULT '',
            consent_version TEXT NOT NULL,
            consent_at INTEGER NOT NULL,
            survey TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS recordings(
            id TEXT PRIMARY KEY,
            participant_id TEXT NOT NULL REFERENCES participants(id) ON DELETE CASCADE,
            prompt_id TEXT NOT NULL REFERENCES prompts(id) ON DELETE CASCADE,
            storage_key TEXT NOT NULL,
            sha256 TEXT NOT NULL,
            mime TEXT NOT NULL,
            bytes INTEGER NOT NULL,
            duration_seconds REAL DEFAULT 0.0,
            format TEXT DEFAULT 'webm',
            status TEXT NOT NULL DEFAULT 'pending_review',
            transcript TEXT,
            reviewer_notes TEXT DEFAULT '',
            reviewed_at INTEGER DEFAULT 0,
            created_at INTEGER NOT NULL,
            UNIQUE(participant_id, prompt_id)
        );
        """)
        # Safe migrations for existing DB schemas
        existing_prompts_cols = [r[1] for r in c.execute("PRAGMA table_info(prompts)").fetchall()]
        if "target_terms" not in existing_prompts_cols:
            c.execute("ALTER TABLE prompts ADD COLUMN target_terms TEXT DEFAULT '[]'")
        if "difficulty" not in existing_prompts_cols:
            c.execute("ALTER TABLE prompts ADD COLUMN difficulty TEXT DEFAULT 'normal'")
        if "category" not in existing_prompts_cols:
            c.execute("ALTER TABLE prompts ADD COLUMN category TEXT DEFAULT ''")
        if "created_at" not in existing_prompts_cols:
            c.execute("ALTER TABLE prompts ADD COLUMN created_at INTEGER NOT NULL DEFAULT 0")

        existing_part_cols = [r[1] for r in c.execute("PRAGMA table_info(participants)").fetchall()]
        if "participant_code" not in existing_part_cols:
            c.execute("ALTER TABLE participants ADD COLUMN participant_code TEXT DEFAULT ''")

        existing_rec_cols = [r[1] for r in c.execute("PRAGMA table_info(recordings)").fetchall()]
        if "duration_seconds" not in existing_rec_cols:
            c.execute("ALTER TABLE recordings ADD COLUMN duration_seconds REAL DEFAULT 0.0")
        if "format" not in existing_rec_cols:
            c.execute("ALTER TABLE recordings ADD COLUMN format TEXT DEFAULT 'webm'")
        if "reviewer_notes" not in existing_rec_cols:
            c.execute("ALTER TABLE recordings ADD COLUMN reviewer_notes TEXT DEFAULT ''")
        if "reviewed_at" not in existing_rec_cols:
            c.execute("ALTER TABLE recordings ADD COLUMN reviewed_at INTEGER DEFAULT 0")

init_db()

def admin(x_admin_key: str | None = None, key: str | None = None):
    supplied = x_admin_key or key
    if not ADMIN_KEY or not supplied or not secrets.compare_digest(ADMIN_KEY, supplied):
        raise HTTPException(403, "Admin credential required")

def participant(x_participant_token: str | None = None, token: str | None = None):
    supplied = x_participant_token or token
    if not supplied:
        raise HTTPException(401, "Participant token required")
    supplied_clean = supplied.strip()
    h = hashlib.sha256(supplied_clean.encode()).hexdigest()
    with db() as c:
        row = c.execute(
            "SELECT id, participant_code FROM participants WHERE token_hash=? OR (participant_code != '' AND LOWER(participant_code)=LOWER(?))",
            (h, supplied_clean)
        ).fetchone()
    if not row:
        raise HTTPException(401, "Invalid participant token")
    return row["id"]

def detect_audio_format(body: bytes, content_type: str) -> tuple[str, str]:
    """Detect file extension and normalized mime type across WebM, MP4, WAV, OGG."""
    ct = (content_type or "").lower()
    # WebM: EBML header
    if body.startswith(b"\x1a\x45\xdf\xa3") or "webm" in ct:
        return "webm", "audio/webm"
    # WAV: RIFF...WAVE
    if (len(body) >= 12 and body[:4] == b"RIFF" and body[8:12] == b"WAVE") or "wav" in ct:
        return "wav", "audio/wav"
    # OGG / Opus
    if body.startswith(b"OggS") or "ogg" in ct or "opus" in ct:
        return "ogg", "audio/ogg"
    # MP4 / M4A / AAC (Safari / iOS)
    if (len(body) >= 12 and (body[4:8] == b"ftyp" or b"mp4" in body[:32] or b"M4A" in body[:32])) or "mp4" in ct or "aac" in ct or "m4a" in ct:
        return "mp4", "audio/mp4"
    # Generic fallback
    if "audio" in ct:
        return "webm", ct
    return "webm", "audio/webm"

def store_audio(recording_id: str, body: bytes, ext: str, mime: str) -> str:
    if STORAGE == "drive":
        folder = os.getenv("GOOGLE_DRIVE_FOLDER_ID")
        if not folder:
            raise HTTPException(503, "Drive folder not configured")
        try:
            from googleapiclient.discovery import build
            from googleapiclient.http import MediaIoBaseUpload
            from google.auth import default
            creds, _ = default(scopes=["https://www.googleapis.com/auth/drive.file"])
            drive = build("drive", "v3", credentials=creds, cache_discovery=False)
            media = MediaIoBaseUpload(io.BytesIO(body), mimetype=mime, resumable=False)
            obj = drive.files().create(
                body={"name": f"{recording_id}.{ext}", "parents": [folder]},
                media_body=media,
                fields="id",
                supportsAllDrives=True
            ).execute()
            return obj["id"]
        except Exception as exc:
            raise HTTPException(503, "Private Drive upload failed") from exc

    if STORAGE != "local":
        raise HTTPException(503, "Unsupported storage backend")

    filename = f"{recording_id}.{ext}"
    path = AUDIO_DIR / filename
    path.write_bytes(body)
    return str(path)

def extract_potential_english_terms(text: str) -> list[str]:
    """Extract English technical words/phrases to highlight or tag."""
    pattern = r"\b[A-Za-z][A-Za-z0-9_\-]*(?:\s+[A-Za-z][A-Za-z0-9_\-]+)*\b"
    candidates = re.findall(pattern, text)
    stopwords = {"va", "la", "cac", "nhung", "trong", "khi", "cho", "duoc", "co", "khong", "thi", "de", "mot", "den", "voi"}
    terms = []
    for c in candidates:
        word = c.strip()
        if len(word) >= 2 and word.lower() not in stopwords:
            terms.append(word)
    seen = set()
    return [t for t in terms if not (t.lower() in seen or seen.add(t.lower()))]

# ----------------- Input / Output Models -----------------

class CourseInput(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    description: str = Field(default="", max_length=1000)

class PromptInput(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    language: str = Field(default="vi-en", pattern="^(vi|en|vi-en)$")
    target_terms: list[str] = Field(default_factory=list)
    difficulty: str = Field(default="normal", pattern="^(basic|normal|advanced)$")
    category: str = Field(default="", max_length=100)

class BulkPromptsInput(BaseModel):
    prompts: list[str] = Field(default_factory=list)
    raw_text: str = ""
    language: str = "vi-en"
    category: str = ""
    difficulty: str = "normal"
    publish_immediately: bool = True

class SignupInput(BaseModel):
    consent: bool
    consent_version: str = Field(default="v1.0", min_length=1, max_length=30)
    participant_code: str = Field(default="", max_length=60)
    familiarity: str = Field(default="", max_length=100)
    english_level: str = Field(default="", max_length=100)
    microphone: str = Field(default="", max_length=100)
    environment: str = Field(default="", max_length=100)

class ReviewInput(BaseModel):
    approved: bool | None = None
    status: str = Field(default="approved", pattern="^(approved|rejected|rerecord)$")
    transcript: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=1000)

class AdminLoginInput(BaseModel):
    key: str = Field(min_length=1, max_length=200)

class StudentLoginInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=100)

# ----------------- Authentication Endpoints -----------------

@app.post("/api/v1/auth/admin-login")
def auth_admin_login(data: AdminLoginInput):
    k = data.key.strip()
    if not ADMIN_KEY or not secrets.compare_digest(ADMIN_KEY, k):
        raise HTTPException(401, "Mật khẩu quản trị (Admin Key) không chính xác.")
    return {
        "success": True,
        "role": "admin",
        "token": ADMIN_KEY,
        "message": "Đăng nhập quản trị thành công."
    }

@app.post("/api/v1/auth/student-login")
def auth_student_login(data: StudentLoginInput):
    ident = data.identifier.strip()
    h = hashlib.sha256(ident.encode()).hexdigest()
    with db() as c:
        row = c.execute(
            """SELECT id, participant_code, consent_version, consent_at, survey
               FROM participants
               WHERE token_hash=? OR (participant_code != '' AND LOWER(participant_code)=LOWER(?))""",
            (h, ident)
        ).fetchone()
    if not row:
        raise HTTPException(404, "Không tìm thấy tài khoản với mã này. Vui lòng kiểm tra lại hoặc đăng ký mới.")

    survey = json.loads(row["survey"]) if row["survey"] else {}
    return {
        "success": True,
        "role": "student",
        "participant_id": row["id"],
        "participant_code": row["participant_code"],
        "token": ident,
        "survey": survey
    }

# ----------------- Health & Capabilities -----------------

@app.get("/health")
def health():
    return {
        "status": "ok",
        "storage": STORAGE,
        "production_ready": True,
        "version": "1.0.0"
    }

@app.get("/api/v1/capabilities")
def capabilities():
    return {
        "recording_upload_enabled": True,
        "google_drive_enabled": STORAGE == "drive",
        "supported_audio_formats": ["audio/webm", "audio/mp4", "audio/wav", "audio/ogg"],
        "version": "1.0.0"
    }

# ----------------- Course & Prompt Management -----------------

@app.post("/api/v1/admin/courses")
def create_course(data: CourseInput, x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    id_ = str(uuid.uuid4())
    now = int(time.time())
    with db() as c:
        c.execute("INSERT INTO courses VALUES (?,?,?,?)", (id_, data.title, data.description, now))
    return {"id": id_, "title": data.title, "description": data.description}

@app.get("/api/v1/admin/courses")
def list_admin_courses(x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    with db() as c:
        rows = c.execute("""
            SELECT c.id, c.title, c.description, c.created_at,
                   COUNT(p.id) as prompt_count,
                   SUM(CASE WHEN p.published = 1 THEN 1 ELSE 0 END) as published_count
            FROM courses c
            LEFT JOIN prompts p ON p.course_id = c.id
            GROUP BY c.id
            ORDER BY c.created_at DESC
        """).fetchall()
        return [dict(r) for r in rows]

@app.delete("/api/v1/admin/courses/{course_id}")
def delete_course(course_id: str, x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    with db() as c:
        n = c.execute("DELETE FROM courses WHERE id=?", (course_id,)).rowcount
    if not n:
        raise HTTPException(404, "Course not found")
    return {"deleted": True, "id": course_id}

@app.post("/api/v1/admin/courses/{course_id}/prompts")
def create_prompt(course_id: str, data: PromptInput, x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    id_ = str(uuid.uuid4())
    terms = data.target_terms or extract_potential_english_terms(data.text)
    terms_json = json.dumps(terms, ensure_ascii=False)
    now = int(time.time())
    with db() as c:
        if not c.execute("SELECT 1 FROM courses WHERE id=?", (course_id,)).fetchone():
            raise HTTPException(404, "Course not found")
        c.execute(
            """INSERT INTO prompts(id, course_id, text, language, target_terms, difficulty, category, published, created_at)
               VALUES (?,?,?,?,?,?,?,0,?)""",
            (id_, course_id, data.text.strip(), data.language, terms_json, data.difficulty, data.category, now)
        )
    return {"id": id_, "published": False, "target_terms": terms}

@app.post("/api/v1/admin/courses/{course_id}/prompts/bulk")
def bulk_create_prompts(course_id: str, data: BulkPromptsInput, x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    lines = list(data.prompts)
    if data.raw_text.strip():
        lines.extend([line.strip() for line in data.raw_text.splitlines() if line.strip()])

    if not lines:
        raise HTTPException(400, "No prompts provided")

    with db() as c:
        if not c.execute("SELECT 1 FROM courses WHERE id=?", (course_id,)).fetchone():
            raise HTTPException(404, "Course not found")
        now = int(time.time())
        created = []
        for line in lines:
            line = line.strip()
            if not line or len(line) < 3:
                continue
            pid = str(uuid.uuid4())
            terms = extract_potential_english_terms(line)
            terms_json = json.dumps(terms, ensure_ascii=False)
            pub = 1 if data.publish_immediately else 0
            c.execute(
                """INSERT INTO prompts(id, course_id, text, language, target_terms, difficulty, category, published, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (pid, course_id, line, data.language, terms_json, data.difficulty, data.category, pub, now)
            )
            created.append({"id": pid, "text": line, "target_terms": terms})
    return {"created_count": len(created), "published": data.publish_immediately, "prompts": created}

@app.post("/api/v1/admin/prompts/{prompt_id}/publish")
def publish(prompt_id: str, x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    with db() as c:
        n = c.execute("UPDATE prompts SET published=1 WHERE id=?", (prompt_id,)).rowcount
    if not n:
        raise HTTPException(404, "Prompt not found")
    return {"published": True, "id": prompt_id}

@app.post("/api/v1/admin/prompts/{prompt_id}/unpublish")
def unpublish(prompt_id: str, x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    with db() as c:
        n = c.execute("UPDATE prompts SET published=0 WHERE id=?", (prompt_id,)).rowcount
    if not n:
        raise HTTPException(404, "Prompt not found")
    return {"published": False, "id": prompt_id}

@app.delete("/api/v1/admin/prompts/{prompt_id}")
def delete_prompt(prompt_id: str, x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    with db() as c:
        n = c.execute("DELETE FROM prompts WHERE id=?", (prompt_id,)).rowcount
    if not n:
        raise HTTPException(404, "Prompt not found")
    return {"deleted": True, "id": prompt_id}

# ----------------- Student / Public Endpoints -----------------

@app.get("/api/v1/courses")
def public_courses():
    with db() as c:
        rows = c.execute("""
            SELECT c.id, c.title, c.description, COUNT(p.id) AS prompt_count
            FROM courses c
            JOIN prompts p ON p.course_id = c.id
            WHERE p.published = 1
            GROUP BY c.id
            ORDER BY c.title ASC
        """).fetchall()
        return [dict(r) for r in rows]

@app.post("/api/v1/participants")
def signup(data: SignupInput):
    if not data.consent:
        raise HTTPException(400, "Explicit consent is required")
    token = secrets.token_urlsafe(32)
    id_ = str(uuid.uuid4())
    code = data.participant_code.strip() or f"P_{secrets.token_hex(3).upper()}"
    survey_data = {
        "familiarity": data.familiarity,
        "english_level": data.english_level,
        "microphone": data.microphone,
        "environment": data.environment
    }
    with db() as c:
        c.execute(
            """INSERT INTO participants(id, token_hash, participant_code, consent_version, consent_at, survey)
               VALUES (?,?,?,?,?,?)""",
            (id_, hashlib.sha256(token.encode()).hexdigest(), code, data.consent_version, int(time.time()), json.dumps(survey_data))
        )
    return {
        "participant_id": id_,
        "participant_token": token,
        "participant_code": code,
        "message": "Đăng ký thành công. Hệ thống đã lưu mã truy cập của bạn."
    }

@app.get("/api/v1/participants/me")
def participant_me(x_participant_token: str | None = Header(None), token: str | None = Query(None)):
    pid = participant(x_participant_token, token)
    with db() as c:
        row = c.execute("SELECT id, participant_code, consent_version, consent_at, survey FROM participants WHERE id=?", (pid,)).fetchone()
        recs = c.execute("SELECT COUNT(*) as count FROM recordings WHERE participant_id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "Participant not found")
    survey = json.loads(row["survey"]) if row["survey"] else {}
    return {
        "participant_id": row["id"],
        "participant_code": row["participant_code"],
        "consent_version": row["consent_version"],
        "total_recordings": recs["count"] if recs else 0,
        "survey": survey
    }

@app.post("/api/v1/participants/withdraw")
def participant_withdraw(x_participant_token: str | None = Header(None), token: str | None = Query(None)):
    """Withdraw research consent and delete all recordings."""
    pid = participant(x_participant_token, token)
    deleted_files = 0
    with db() as c:
        rows = c.execute("SELECT storage_key FROM recordings WHERE participant_id=?", (pid,)).fetchall()
        for r in rows:
            key = r["storage_key"]
            if key and STORAGE == "local":
                p = Path(key)
                if p.is_file():
                    try:
                        p.unlink()
                        deleted_files += 1
                    except Exception:
                        pass
        c.execute("DELETE FROM recordings WHERE participant_id=?", (pid,))
        c.execute("DELETE FROM participants WHERE id=?", (pid,))
    return {"withdrawn": True, "deleted_recordings": len(rows), "deleted_files": deleted_files}

@app.get("/api/v1/tasks")
def tasks(course_id: str, x_participant_token: str | None = Header(None), token: str | None = Query(None)):
    pid = participant(x_participant_token, token)
    with db() as c:
        rows = c.execute("""
            SELECT p.id, p.text, p.language, p.target_terms, p.difficulty, p.category,
                   r.id AS recording_id, r.status, r.duration_seconds
            FROM prompts p
            LEFT JOIN recordings r ON r.prompt_id = p.id AND r.participant_id = ?
            WHERE p.course_id = ? AND p.published = 1
            ORDER BY p.rowid ASC
        """, (pid, course_id)).fetchall()
        tasks_list = []
        for r in rows:
            d = dict(r)
            try:
                d["target_terms"] = json.loads(d["target_terms"]) if d["target_terms"] else []
            except Exception:
                d["target_terms"] = []
            tasks_list.append(d)
        return tasks_list

@app.post("/api/v1/recordings")
async def upload_recording(
    prompt_id: str = Form(...),
    audio: UploadFile = File(...),
    duration: float = Form(0.0),
    x_participant_token: str | None = Header(None),
    token: str | None = Query(None)
):
    pid = participant(x_participant_token, token)
    with db() as c:
        if not c.execute("SELECT 1 FROM prompts WHERE id=? AND published=1", (prompt_id,)).fetchone():
            raise HTTPException(404, "Prompt unavailable")
        if c.execute("SELECT 1 FROM recordings WHERE prompt_id=? AND participant_id=?", (prompt_id, pid)).fetchone():
            raise HTTPException(409, "Bạn đã nộp bản ghi cho câu này rồi")

    body = await audio.read(MAX_BYTES + 1)
    if len(body) < 100:
        raise HTTPException(422, "File âm thanh quá ngắn hoặc rỗng")
    if len(body) > MAX_BYTES:
        raise HTTPException(413, "Dung lượng file vượt quá giới hạn 15MB")

    ext, norm_mime = detect_audio_format(body, audio.content_type)
    rec_id = str(uuid.uuid4())
    storage_key = store_audio(rec_id, body, ext, norm_mime)
    now = int(time.time())
    file_sha256 = hashlib.sha256(body).hexdigest()

    with db() as c:
        try:
            c.execute("""
                INSERT INTO recordings(id, participant_id, prompt_id, storage_key, sha256, mime, bytes,
                                       duration_seconds, format, status, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,'pending_review',?)
            """, (rec_id, pid, prompt_id, storage_key, file_sha256, norm_mime, len(body), duration, ext, now))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Bạn đã nộp bản ghi cho câu này rồi") from exc

    return {
        "recording_id": rec_id,
        "format": ext,
        "bytes": len(body),
        "duration_seconds": duration,
        "status": "pending_review",
        "message": "Nộp bản ghi thành công"
    }

# ----------------- Audio Streaming -----------------

@app.get("/api/v1/admin/recordings/{recording_id}/audio")
def admin_audio_stream(
    recording_id: str,
    x_admin_key: str | None = Header(None),
    key: str | None = Query(None)
):
    admin(x_admin_key, key)
    with db() as c:
        r = c.execute("SELECT storage_key, mime, format FROM recordings WHERE id=?", (recording_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Recording not found")

    if STORAGE == "local":
        path = Path(r["storage_key"]).resolve()
        if not path.is_file() or not path.is_relative_to(AUDIO_DIR.resolve()):
            raise HTTPException(404, "Audio file missing on disk")
        return FileResponse(
            path,
            media_type=r["mime"],
            filename=path.name,
            content_disposition_type="inline"
        )
    raise HTTPException(501, "Drive review streaming not implemented directly")

@app.get("/api/v1/recordings/{recording_id}/audio")
def participant_audio_stream(
    recording_id: str,
    x_participant_token: str | None = Header(None),
    token: str | None = Query(None)
):
    pid = participant(x_participant_token, token)
    with db() as c:
        r = c.execute("SELECT storage_key, mime FROM recordings WHERE id=? AND participant_id=?", (recording_id, pid)).fetchone()
    if not r:
        raise HTTPException(404, "Recording not found")

    if STORAGE == "local":
        path = Path(r["storage_key"]).resolve()
        if not path.is_file():
            raise HTTPException(404, "Audio file missing")
        return FileResponse(
            path,
            media_type=r["mime"],
            filename=path.name,
            content_disposition_type="inline"
        )
    raise HTTPException(501, "Audio streaming backend unsupported")

# ----------------- Admin Review Studio -----------------

@app.get("/api/v1/admin/recordings")
def admin_recordings_queue(
    course_id: str | None = None,
    status: str | None = None,
    limit: int = 200,
    x_admin_key: str | None = Header(None),
    key: str | None = Query(None)
):
    admin(x_admin_key, key)
    query = """
        SELECT r.id, r.prompt_id, p.text, p.target_terms, p.language, c.title AS course_title,
               part.participant_code, r.status, r.transcript, r.reviewer_notes,
               r.duration_seconds, r.bytes, r.mime, r.format, r.created_at, r.reviewed_at
        FROM recordings r
        JOIN prompts p ON p.id = r.prompt_id
        JOIN courses c ON c.id = p.course_id
        JOIN participants part ON part.id = r.participant_id
        WHERE 1=1
    """
    params = []
    if course_id:
        query += " AND p.course_id = ?"
        params.append(course_id)
    if status and status != "all":
        query += " AND r.status = ?"
        params.append(status)
    query += " ORDER BY r.created_at DESC LIMIT ?"
    params.append(limit)

    with db() as c:
        rows = c.execute(query, params).fetchall()
        result = []
        for r in rows:
            d = dict(r)
            try:
                d["target_terms"] = json.loads(d["target_terms"]) if d["target_terms"] else []
            except Exception:
                d["target_terms"] = []
            result.append(d)
        return result

@app.post("/api/v1/admin/recordings/{recording_id}/review")
def review_recording(
    recording_id: str,
    data: ReviewInput,
    x_admin_key: str | None = Header(None),
    key: str | None = Query(None)
):
    admin(x_admin_key, key)
    target_status = data.status
    if data.approved is not None:
        target_status = "approved" if data.approved else "rejected"

    now = int(time.time())
    with db() as c:
        n = c.execute("""
            UPDATE recordings
            SET status=?, transcript=?, reviewer_notes=?, reviewed_at=?
            WHERE id=?
        """, (target_status, data.transcript, data.notes, now, recording_id)).rowcount
    if not n:
        raise HTTPException(404, "Recording not found")
    return {"status": target_status, "recording_id": recording_id}

# ----------------- Admin Analytics & Stats -----------------

@app.get("/api/v1/admin/stats")
def admin_stats(x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    with db() as c:
        courses_count = c.execute("SELECT COUNT(*) FROM courses").fetchone()[0]
        prompts_total = c.execute("SELECT COUNT(*) FROM prompts").fetchone()[0]
        prompts_published = c.execute("SELECT COUNT(*) FROM prompts WHERE published=1").fetchone()[0]
        part_count = c.execute("SELECT COUNT(*) FROM participants").fetchone()[0]

        recs_total = c.execute("SELECT COUNT(*) FROM recordings").fetchone()[0]
        recs_approved = c.execute("SELECT COUNT(*) FROM recordings WHERE status='approved'").fetchone()[0]
        recs_rejected = c.execute("SELECT COUNT(*) FROM recordings WHERE status='rejected'").fetchone()[0]
        recs_rerecord = c.execute("SELECT COUNT(*) FROM recordings WHERE status='rerecord'").fetchone()[0]
        recs_pending = c.execute("SELECT COUNT(*) FROM recordings WHERE status='pending_review'").fetchone()[0]

        approved_duration = c.execute("SELECT COALESCE(SUM(duration_seconds), 0) FROM recordings WHERE status='approved'").fetchone()[0]
        total_duration = c.execute("SELECT COALESCE(SUM(duration_seconds), 0) FROM recordings").fetchone()[0]

        course_breakdown = c.execute("""
            SELECT c.id, c.title,
                   COUNT(DISTINCT p.id) as prompts_count,
                   COUNT(r.id) as recordings_count,
                   SUM(CASE WHEN r.status='approved' THEN 1 ELSE 0 END) as approved_count
            FROM courses c
            LEFT JOIN prompts p ON p.course_id = c.id
            LEFT JOIN recordings r ON r.prompt_id = p.id
            GROUP BY c.id
            ORDER BY c.title ASC
        """).fetchall()

        return {
            "total_courses": courses_count,
            "total_prompts": prompts_total,
            "published_prompts": prompts_published,
            "total_participants": part_count,
            "total_recordings": recs_total,
            "approved_recordings": recs_approved,
            "rejected_recordings": recs_rejected,
            "rerecord_recordings": recs_rerecord,
            "pending_recordings": recs_pending,
            "approved_duration_minutes": round(approved_duration / 60.0, 2),
            "total_duration_minutes": round(total_duration / 60.0, 2),
            "courses": [dict(r) for r in course_breakdown]
        }

# ----------------- Export Dataset Manifest & ZIP -----------------

def get_approved_dataset_rows():
    with db() as c:
        return c.execute("""
            SELECT r.id as recording_id, r.participant_id, part.participant_code,
                   p.course_id, c.title as course_title,
                   p.id as prompt_id, p.text as prompt_text,
                   r.transcript as verbatim_transcript,
                   p.target_terms, p.language, p.difficulty, p.category,
                   r.duration_seconds, r.bytes, r.mime, r.format, r.sha256,
                   r.storage_key, r.created_at, r.reviewed_at,
                   part.survey
            FROM recordings r
            JOIN prompts p ON p.id = r.prompt_id
            JOIN courses c ON c.id = p.course_id
            JOIN participants part ON part.id = r.participant_id
            WHERE r.status = 'approved'
            ORDER BY r.created_at ASC
        """).fetchall()

@app.get("/api/v1/admin/export/manifest.json")
def export_manifest_json(x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    rows = get_approved_dataset_rows()
    output = []
    for r in rows:
        item = dict(r)
        item.pop("storage_key", None)
        item["audio_file"] = f"{item['recording_id']}.{item['format']}"
        try:
            item["target_terms"] = json.loads(item["target_terms"]) if item["target_terms"] else []
        except Exception:
            item["target_terms"] = []
        try:
            item["survey"] = json.loads(item["survey"]) if item["survey"] else {}
        except Exception:
            item["survey"] = {}
        output.append(item)
    return output

@app.get("/api/v1/admin/export/manifest.csv")
def export_manifest_csv(x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    rows = get_approved_dataset_rows()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([
        "recording_id", "participant_code", "course_title", "prompt_text",
        "verbatim_transcript", "target_terms", "duration_seconds", "audio_file", "sha256"
    ])
    for r in rows:
        writer.writerow([
            r["recording_id"],
            r["participant_code"],
            r["course_title"],
            r["prompt_text"],
            r["verbatim_transcript"] or r["prompt_text"],
            r["target_terms"],
            r["duration_seconds"],
            f"{r['recording_id']}.{r['format']}",
            r["sha256"]
        ])
    return Response(
        content=buf.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="liemwhisper_manifest.csv"'}
    )

@app.get("/api/v1/admin/export/archive.zip")
def export_archive_zip(x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    rows = get_approved_dataset_rows()
    zip_buffer = io.BytesIO()

    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest_items = []
        for r in rows:
            item = dict(r)
            item.pop("storage_key", None)
            item["audio_file"] = f"audio/{item['recording_id']}.{item['format']}"
            try:
                item["target_terms"] = json.loads(item["target_terms"]) if item["target_terms"] else []
            except Exception:
                item["target_terms"] = []
            try:
                item["survey"] = json.loads(item["survey"]) if item["survey"] else {}
            except Exception:
                item["survey"] = {}
            manifest_items.append(item)
        zf.writestr("manifest.json", json.dumps(manifest_items, ensure_ascii=False, indent=2))

        csv_buf = io.StringIO()
        writer = csv.writer(csv_buf)
        writer.writerow([
            "recording_id", "participant_code", "course_title", "prompt_text",
            "verbatim_transcript", "target_terms", "duration_seconds", "audio_file", "sha256"
        ])
        for r in rows:
            writer.writerow([
                r["recording_id"],
                r["participant_code"],
                r["course_title"],
                r["prompt_text"],
                r["verbatim_transcript"] or r["prompt_text"],
                r["target_terms"],
                r["duration_seconds"],
                f"audio/{r['recording_id']}.{r['format']}",
                r["sha256"]
            ])
        zf.writestr("manifest.csv", csv_buf.getvalue())

        for r in rows:
            storage_key = r["storage_key"]
            if storage_key and STORAGE == "local":
                p = Path(storage_key)
                if p.is_file():
                    zf.write(p, arcname=f"audio/{r['recording_id']}.{r['format']}")

    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="liemwhisper_approved_dataset.zip"'}
    )
