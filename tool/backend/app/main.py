"""LiemWhisper recording-collection API — Production-ready collection platform.

Supports multi-format audio (WebM, MP4/AAC, WAV, OGG), range-request streaming,
bulk prompt import, reviewer studio, real-time stats, and export manifest/archive.
Full audio in SQL and durable Google Drive sync via outbox architecture.
"""
import csv
import hashlib
import io
import json
import os
import re
import secrets
import time
import uuid
import zipfile
from pathlib import Path
import urllib.request
try:
    import requests
except ImportError:
    requests = None
from fastapi import BackgroundTasks, FastAPI, File, Form, Header, HTTPException, Query, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel, Field

from app.database import db, get_data_root, init_db

from app.auth import (
    add_admin_email,
    admin_login,
    create_admin_session,
    is_admin_email,
    list_admin_emails,
    participant_login,
    remove_admin_email,
    require_admin,
    revoke_admin,
    setup_auth,
)
from app.drive import is_drive_connected, register_drive_routes
from app.storage import (
    get_audio_bytes,
    store_audio_bytes,
    stream_audio_response,
    validate_storage_backend,
)
from app.worker import enqueue_delete_job

ROOT = get_data_root()
STORAGE = os.getenv("STORAGE_BACKEND", "local")
MAX_BYTES = int(os.getenv("MAX_AUDIO_BYTES", "15000000"))  # 15MB limit
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "liemwhisper-admin-secret-2026")
GOOGLE_CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID", "")
ORIGINS_ENV = os.getenv("WEB_PUBLIC_URL", "*")
ALLOWED_ORIGINS = [o.strip() for o in ORIGINS_ENV.split(",") if o.strip()] or ["*"]

AUDIO_DIR = ROOT / "audio"
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

init_db()
setup_auth(db)


def auto_seed_default_prompts(force: bool = False) -> dict:
    """Synchronize the SWT corpus while preserving recordings and custom courses."""
    from app.prompt_seed import sync_swt_prompts

    try:
        return sync_swt_prompts(db, force=force)
    except Exception as exc:
        print(f"Notice: auto_seed_default_prompts exception: {exc}")
        return {"status": "exception", "exception": str(exc)}


auto_seed_default_prompts()

import asyncio
from contextlib import asynccontextmanager

async def periodic_outbox_sync():
    """Background periodic loop to sync pending recordings to Google Drive."""
    await asyncio.sleep(5)
    while True:
        try:
            if is_drive_connected(db):
                from app.worker import backfill_unsynced_drive_jobs, process_all_outbox
                await asyncio.to_thread(backfill_unsynced_drive_jobs, db)
                await asyncio.to_thread(process_all_outbox, db, 20)
        except asyncio.CancelledError:
            break
        except Exception:
            pass
        await asyncio.sleep(20)

@asynccontextmanager
async def lifespan(app: FastAPI):
    worker_task = None
    if os.getenv("TESTING") != "true":
        worker_task = asyncio.create_task(periodic_outbox_sync())
    try:
        yield
    finally:
        if worker_task:
            worker_task.cancel()
            try:
                await worker_task
            except asyncio.CancelledError:
                pass

app = FastAPI(title="LiemWhisper Collection API", version="1.0.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS if "*" not in ALLOWED_ORIGINS else ["*"],
    allow_credentials=True if "*" not in ALLOWED_ORIGINS else False,
    allow_methods=["*"],
    allow_headers=["*"],
)



def admin(x_admin_key: str | None = None, key: str | None = None):
    supplied = x_admin_key or key
    if not supplied:
        raise HTTPException(403, "Admin credential required")
    try:
        require_admin(db, supplied)
        return
    except HTTPException:
        pass
    if ADMIN_KEY and secrets.compare_digest(ADMIN_KEY, supplied):
        return
    raise HTTPException(403, "Admin credential required")


register_drive_routes(app, db, admin)


def participant(x_participant_token: str | None = None, token: str | None = None):
    supplied = x_participant_token or token
    if not supplied:
        raise HTTPException(401, "Participant token required")
    row = participant_login(db, supplied)
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


def get_client_ip(request: Request | None) -> str:
    """Safely extract client IP from reverse proxy or direct socket."""
    if not request:
        return "unknown"
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


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
    birth_year: int | None = Field(default=None, ge=1970, le=2015)
    academic_year: str = Field(default="", max_length=50)
    environment_noise: str = Field(default="", max_length=100)
    accent_region: str = Field(default="", max_length=50)

class ReviewInput(BaseModel):
    approved: bool | None = None
    status: str = Field(default="approved", pattern="^(approved|rejected|rerecord)$")
    transcript: str = Field(default="", max_length=4000)
    notes: str = Field(default="", max_length=1000)

class AdminLoginInput(BaseModel):
    key: str = Field(min_length=1, max_length=200)

class StudentLoginInput(BaseModel):
    identifier: str = Field(min_length=1, max_length=100)

class GoogleAuthInput(BaseModel):
    credential: str

class GoogleOnboardInput(BaseModel):
    temp_token: str
    consent: bool
    consent_version: str = Field(default="v1.0", min_length=1, max_length=30)
    participant_code: str = Field(default="", max_length=60)
    english_level: str = Field(min_length=1, max_length=100)
    class_name: str = Field(default="", max_length=100)
    referring_lecturer: str = Field(default="", max_length=150)
    accent_region: str = Field(default="Miền Bắc", max_length=50)
    birth_year: int | None = Field(default=None, ge=1970, le=2015)
    academic_year: str = Field(default="", max_length=50)
    microphone: str = Field(default="Điện thoại", max_length=100)
    environment: str = Field(default="Phòng yên tĩnh", max_length=100)


def extract_student_code(email: str) -> str:
    """Extract student ID from email if present (e.g. se194007@fpt.edu.vn -> SE194007)."""
    match = re.search(r"([a-zA-Z]{2}\d{5,6})", email)
    if match:
        return match.group(1).upper()
    return ""


def verify_google_id_token(credential: str) -> dict:
    """Verify Google OAuth2 ID token using Google tokeninfo with urllib and fallbacks."""
    if not credential or not isinstance(credential, str):
        raise HTTPException(400, "Mã xác thực Google không hợp lệ")

    # Method 1: Standard urllib (zero third-party dependencies)
    try:
        url = f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}"
        req = urllib.request.Request(url, headers={"User-Agent": "LiemWhisper-Backend/1.0"})
        with urllib.request.urlopen(req, timeout=10) as response:
            if response.status == 200:
                payload = json.loads(response.read().decode("utf-8"))
                if "error" in payload or "error_description" in payload:
                    raise HTTPException(401, f"Google token không hợp lệ: {payload.get('error_description')}")
                if not payload.get("email"):
                    raise HTTPException(400, "Tài khoản Google không có email")
                return payload
    except HTTPException:
        raise
    except Exception:
        pass

    # Method 2: requests if available
    if requests is not None:
        try:
            resp = requests.get(
                f"https://oauth2.googleapis.com/tokeninfo?id_token={credential}",
                timeout=8
            )
            if resp.status_code == 200:
                payload = resp.json()
                if "error" in payload or "error_description" in payload:
                    raise HTTPException(401, f"Google token không hợp lệ: {payload.get('error_description')}")
                if not payload.get("email"):
                    raise HTTPException(400, "Tài khoản Google không có email")
                return payload
        except HTTPException:
            raise
        except Exception:
            pass

    # Method 3: google.oauth2.id_token if installed
    try:
        from google.oauth2 import id_token
        from google.auth.transport import requests as google_requests
        return id_token.verify_oauth2_token(credential, google_requests.Request())
    except Exception as exc:
        raise HTTPException(401, f"Không thể xác minh token Google: {exc}")


# ----------------- Authentication Endpoints -----------------

@app.post("/api/v1/auth/admin-login")
def auth_admin_login(data: AdminLoginInput):
    k = data.key.strip()
    try:
        session_token = admin_login(db, k, ADMIN_KEY)
        return {
            "success": True,
            "role": "admin",
            "token": session_token,
            "message": "Đăng nhập quản trị thành công."
        }
    except ValueError:
        if ADMIN_KEY and secrets.compare_digest(ADMIN_KEY, k):
            return {
                "success": True,
                "role": "admin",
                "token": ADMIN_KEY,
                "message": "Đăng nhập quản trị thành công."
            }
        raise HTTPException(401, "Mật khẩu quản trị (Admin Key) không chính xác.")

@app.post("/api/v1/auth/admin-logout")
def auth_admin_logout(x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    supplied = x_admin_key or key
    if supplied:
        revoke_admin(db, supplied)
    return {"success": True, "message": "Đã đăng xuất thành công."}

@app.post("/api/v1/auth/student-login")
def auth_student_login(data: StudentLoginInput):
    ident = data.identifier.strip()
    try:
        row = participant_login(db, ident)
        survey = json.loads(row["survey"]) if row.get("survey") else {}
        return {
            "success": True,
            "role": "student",
            "participant_id": row["id"],
            "participant_code": row["participant_code"],
            "token": ident,
            "survey": survey
        }
    except HTTPException:
        with db() as c:
            code_match = c.execute(
                "SELECT 1 FROM participants WHERE participant_code != '' AND LOWER(participant_code)=LOWER(?)",
                (ident,)
            ).fetchone()
        if code_match:
            raise HTTPException(
                401,
                "Vui lòng nhập Mã truy cập bí mật (token) được cấp khi đăng ký, không phải mã sinh viên hiển thị."
            )
        raise HTTPException(404, "Không tìm thấy tài khoản với mã này. Vui lòng kiểm tra lại hoặc đăng ký mới.")

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
        "google_drive_enabled": STORAGE == "sql_drive",
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


@app.get("/api/v1/admin/prompts")
def admin_list_prompts(
    course_id: str | None = None,
    search: str | None = None,
    x_admin_key: str | None = Header(None),
    key: str | None = Query(None)
):
    """Retrieve all prompts across courses with count of submitted recordings."""
    admin(x_admin_key, key)
    with db() as c:
        query = """
            SELECT p.id, p.course_id, p.text, p.target_terms, p.language, p.difficulty, p.category, p.published, p.created_at,
                   c.title AS course_title,
                   COUNT(r.id) AS recordings_count
            FROM prompts p
            LEFT JOIN courses c ON c.id = p.course_id
            LEFT JOIN recordings r ON r.prompt_id = p.id
        """
        where_clauses = []
        params = []
        if course_id:
            where_clauses.append("p.course_id = ?")
            params.append(course_id)
        if search and search.strip():
            where_clauses.append("p.text LIKE ?")
            params.append(f"%{search.strip()}%")
        if where_clauses:
            query += " WHERE " + " AND ".join(where_clauses)
        query += """
            GROUP BY p.id, p.course_id, p.text, p.target_terms, p.language, p.difficulty, p.category, p.published, p.created_at, c.title
            ORDER BY c.title ASC, p.created_at ASC, p.id ASC
        """
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


# ----------------- Admin Gmail & Role Management -----------------

class AdminEmailInput(BaseModel):
    email: str = Field(min_length=3, max_length=150)


@app.get("/api/v1/admin/admins")
def admin_get_admins(x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    """Retrieve all authorized admin email addresses."""
    admin(x_admin_key, key)
    return {
        "status": "success",
        "admins": list_admin_emails(db)
    }


@app.post("/api/v1/admin/admins")
def admin_add_admin(data: AdminEmailInput, x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    """Grant admin role to a Google email address."""
    admin(x_admin_key, key)
    clean_email = data.email.strip().lower()
    res = add_admin_email(db, clean_email, created_by="admin")
    return {
        "status": "success",
        "admin": res,
        "message": f"Đã cấp quyền Quản trị viên thành công cho {clean_email}."
    }


@app.delete("/api/v1/admin/admins/{email}")
def admin_delete_admin(email: str, x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    """Revoke admin role from an email address."""
    admin(x_admin_key, key)
    clean_email = email.strip().lower()
    success = remove_admin_email(db, clean_email)
    if not success:
        raise HTTPException(404, f"Không tìm thấy email {clean_email} trong danh sách quản trị viên.")
    return {
        "status": "success",
        "message": f"Đã thu hồi quyền Quản trị viên của {clean_email}."
    }


@app.get("/api/v1/admin/participants")
def admin_get_participants(
    search: str | None = None,
    limit: int = 500,
    x_admin_key: str | None = Header(None),
    key: str | None = Query(None)
):
    """Retrieve participants with statistics, counts, email and admin status."""
    admin(x_admin_key, key)
    with db() as c:
        query = """
            SELECT p.id, p.participant_code, p.email, p.name, p.onboarded, p.consent_at, p.completed_at, p.is_admin, p.drive_folder_id,
                   COUNT(r.id) AS recordings_count,
                   COALESCE(SUM(r.duration_seconds), 0.0) AS total_duration_seconds
            FROM participants p
            LEFT JOIN recordings r ON r.participant_id = p.id
        """
        params = []
        if search and search.strip():
            s = f"%{search.strip()}%"
            query += " WHERE (p.participant_code LIKE ? OR p.name LIKE ? OR p.email LIKE ?)"
            params.extend([s, s, s])
        query += """
            GROUP BY p.id, p.participant_code, p.email, p.name, p.onboarded, p.consent_at, p.completed_at, p.is_admin, p.drive_folder_id
            ORDER BY p.consent_at DESC
        """
        if limit > 0:
            query += " LIMIT ?"
            params.append(limit)
        rows = c.execute(query, params).fetchall()
        return {
            "status": "success",
            "participants": [dict(r) for r in rows]
        }


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
        if not rows:
            auto_seed_default_prompts()
            rows = c.execute("""
                SELECT c.id, c.title, c.description, COUNT(p.id) AS prompt_count
                FROM courses c
                JOIN prompts p ON p.course_id = c.id
                WHERE p.published = 1
                GROUP BY c.id
                ORDER BY c.title ASC
            """).fetchall()
        return [dict(r) for r in rows]


@app.api_route("/api/v1/courses/seed-default", methods=["GET", "POST"])
def manual_seed_default(force: bool = False):
    diag = auto_seed_default_prompts(force=force)
    with db() as c:
        courses_rows = c.execute("SELECT id, title, description FROM courses").fetchall()
        p_count = c.execute("SELECT COUNT(*) FROM prompts WHERE published=1").fetchone()
    return {
        "status": "success",
        "diagnostic": diag,
        "courses": [dict(r) for r in courses_rows],
        "published_prompts": p_count[0] if p_count else 0
    }

@app.post("/api/v1/participants")
def signup(data: SignupInput, request: Request):
    if not data.consent:
        raise HTTPException(400, "Explicit consent is required")
    token = secrets.token_urlsafe(32)
    id_ = str(uuid.uuid4())
    code = data.participant_code.strip() or f"P_{secrets.token_hex(3).upper()}"
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")[:250]
    survey_data = {
        "familiarity": data.familiarity,
        "english_level": data.english_level,
        "microphone": data.microphone,
        "environment": data.environment,
        "birth_year": data.birth_year,
        "academic_year": data.academic_year,
        "environment_noise": data.environment_noise,
        "accent_region": data.accent_region,
        "client_ip": client_ip,
        "user_agent": user_agent,
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


@app.post("/api/v1/auth/google")
def auth_google(data: GoogleAuthInput, request: Request):
    """Authenticate with Google ID token, returning session or triggering onboarding."""
    payload = verify_google_id_token(data.credential)
    google_id = payload.get("sub", "")
    email = payload.get("email", "").lower().strip()
    name = payload.get("name", "")
    picture = payload.get("picture", "")

    user_is_admin = is_admin_email(db, email)
    admin_session_token = create_admin_session(db) if user_is_admin else None

    with db() as c:
        row = c.execute(
            """SELECT id, participant_code, token_hash, consent_version, consent_at, survey, email, google_id, name, onboarded, is_admin
               FROM participants
               WHERE google_id=? OR (email=? AND email != '')""",
            (google_id, email)
        ).fetchone()

        now = int(time.time())
        client_ip = get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")[:250]

        if row:
            token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(token.encode()).hexdigest()
            is_admin_flag = 1 if user_is_admin else (row["is_admin"] if "is_admin" in row.keys() else 0)
            c.execute(
                "UPDATE participants SET token_hash=?, google_id=?, name=?, email=?, is_admin=? WHERE id=?",
                (token_hash, google_id, name, email, is_admin_flag, row["id"])
            )

            is_onboarded = bool(row["onboarded"] and row["onboarded"] == 1)
            if is_onboarded:
                return {
                    "status": "success",
                    "needs_onboarding": False,
                    "participant_token": token,
                    "participant_code": row["participant_code"],
                    "participant_id": row["id"],
                    "email": email,
                    "name": name,
                    "picture": picture,
                    "is_admin": user_is_admin,
                    "admin_token": admin_session_token,
                    "role": "admin" if user_is_admin else "student",
                    "message": "Đăng nhập Google thành công" + (" với quyền Quản trị viên" if user_is_admin else "")
                }
            else:
                return {
                    "status": "success",
                    "needs_onboarding": True,
                    "temp_token": token,
                    "email": email,
                    "name": name,
                    "picture": picture,
                    "suggested_code": row["participant_code"] or extract_student_code(email),
                    "is_admin": user_is_admin,
                    "admin_token": admin_session_token,
                    "role": "admin" if user_is_admin else "student"
                }
        else:
            pid = str(uuid.uuid4())
            temp_token = secrets.token_urlsafe(32)
            token_hash = hashlib.sha256(temp_token.encode()).hexdigest()
            suggested_code = extract_student_code(email)
            draft_survey = {
                "email": email,
                "name": name,
                "client_ip": client_ip,
                "user_agent": user_agent,
            }
            c.execute(
                """INSERT INTO participants(id, token_hash, participant_code, consent_version, consent_at, survey, email, google_id, name, onboarded, is_admin)
                   VALUES (?,?,?,?,?,?,?,?,?,0,?)""",
                (pid, token_hash, suggested_code, "v1.0", now, json.dumps(draft_survey), email, google_id, name, 1 if user_is_admin else 0)
            )
            return {
                "status": "success",
                "needs_onboarding": True,
                "temp_token": temp_token,
                "email": email,
                "name": name,
                "picture": picture,
                "suggested_code": suggested_code,
                "is_admin": user_is_admin,
                "admin_token": admin_session_token,
                "role": "admin" if user_is_admin else "student"
            }


@app.post("/api/v1/auth/google/onboard")
def auth_google_onboard(data: GoogleOnboardInput, request: Request):
    """Complete first-time Google participant onboarding with consent and survey."""
    if not data.english_level.strip():
        raise HTTPException(422, "Vui lòng chọn trình độ tiếng Anh.")
    if not data.consent:
        raise HTTPException(400, "Xác nhận tự nguyện tham gia (Consent) là bắt buộc.")

    token_hash = hashlib.sha256(data.temp_token.encode()).hexdigest()
    with db() as c:
        row = c.execute(
            "SELECT id, participant_code, email, name, survey FROM participants WHERE token_hash=?",
            (token_hash,)
        ).fetchone()
        if not row:
            raise HTTPException(401, "Phiên xác thực Google không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại Google.")

        code = data.participant_code.strip()
        if not code:
            code = extract_student_code(row["email"]) or f"P_{secrets.token_hex(3).upper()}"

        client_ip = get_client_ip(request)
        user_agent = request.headers.get("user-agent", "")[:250]

        survey_data = {
            "email": row["email"],
            "name": row["name"],
            "student_id": data.participant_code.strip(),
            "english_level": data.english_level.strip(),
            "class_name": data.class_name.strip(),
            "referring_lecturer": data.referring_lecturer.strip(),
            "accent_region": data.accent_region,
            "birth_year": data.birth_year,
            "academic_year": data.academic_year,
            "microphone": data.microphone,
            "environment": data.environment,
            "client_ip": client_ip,
            "user_agent": user_agent,
        }

        user_is_admin = is_admin_email(db, row["email"])
        admin_session_token = create_admin_session(db) if user_is_admin else None

        now = int(time.time())
        c.execute(
            """UPDATE participants
               SET participant_code=?, consent_version=?, consent_at=?, survey=?, onboarded=1, is_admin=?
               WHERE id=?""",
            (code, data.consent_version, now, json.dumps(survey_data), 1 if user_is_admin else 0, row["id"])
        )

    return {
        "status": "success",
        "participant_token": data.temp_token,
        "participant_code": code,
        "participant_id": row["id"],
        "email": row["email"],
        "name": row["name"],
        "is_admin": user_is_admin,
        "admin_token": admin_session_token,
        "role": "admin" if user_is_admin else "student",
        "message": "Đăng ký thành công. Chào mừng bạn đến với LiemWhisper!"
    }


@app.get("/api/v1/participants/me")
def participant_me(x_participant_token: str | None = Header(None), token: str | None = Query(None)):
    pid = participant(x_participant_token, token)
    with db() as c:
        row = c.execute("SELECT id, participant_code, consent_version, consent_at, survey, email, name, completed_at, is_admin FROM participants WHERE id=?", (pid,)).fetchone()
        recs = c.execute("SELECT COUNT(*) as count FROM recordings WHERE participant_id=?", (pid,)).fetchone()
    if not row:
        raise HTTPException(404, "Participant not found")
    survey = json.loads(row["survey"]) if row["survey"] else {}
    email = row.get("email", "") or ""
    user_is_admin = is_admin_email(db, email) or bool(row.get("is_admin"))
    return {
        "participant_id": row["id"],
        "participant_code": row["participant_code"],
        "email": email,
        "name": row.get("name", "") or "",
        "consent_version": row["consent_version"],
        "total_recordings": recs["count"] if recs else 0,
        "completed_at": row.get("completed_at", 0) or 0,
        "is_admin": user_is_admin,
        "survey": survey
    }

@app.post("/api/v1/participants/complete")
def participant_complete(
    background_tasks: BackgroundTasks = None,
    x_participant_token: str | None = Header(None),
    token: str | None = Query(None)
):
    """Mark participant recording session as completed and trigger thank-you email."""
    pid = participant(x_participant_token, token)
    now = int(time.time())
    with db() as c:
        row = c.execute("SELECT id, participant_code, email, name, completed_at FROM participants WHERE id=?", (pid,)).fetchone()
        if not row:
            raise HTTPException(404, "Participant not found")

        # Anti-spam: If session is already completed, do not re-dispatch email or overwrite timestamp
        if row.get("completed_at"):
            recs_count = c.execute("SELECT COUNT(*) as count FROM recordings WHERE participant_id=?", (pid,)).fetchone()["count"]
            return {
                "status": "success",
                "completed": True,
                "already_completed": True,
                "completed_at": row["completed_at"],
                "total_recordings": recs_count,
                "email": (row.get("email") or "").strip(),
                "email_delivery": {"already_sent": True, "sent": True, "simulated": False},
                "message": "Bài thi của bạn đã được xác nhận hoàn thành trước đó."
            }

        recs_count = c.execute("SELECT COUNT(*) as count FROM recordings WHERE participant_id=?", (pid,)).fetchone()["count"]
        c.execute("UPDATE participants SET completed_at=? WHERE id=?", (now, pid))

    email = (row.get("email") or "").strip()
    name = (row.get("name") or "").strip()
    code = (row.get("participant_code") or "").strip()

    email_status = {}
    if email:
        from app.mailer import send_thank_you_email
        email_status = send_thank_you_email(
            to_email=email,
            participant_name=name,
            participant_code=code,
            total_recordings=recs_count
        )

    if background_tasks is not None:
        def _bg_drive_sync():
            try:
                if is_drive_connected(db):
                    from app.worker import backfill_unsynced_drive_jobs, process_all_outbox
                    backfill_unsynced_drive_jobs(db)
                    process_all_outbox(db, max_total=50)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Completion drive sync error: %s", e)
        background_tasks.add_task(_bg_drive_sync)

    return {
        "status": "success",
        "completed": True,
        "completed_at": now,
        "total_recordings": recs_count,
        "email": email,
        "email_delivery": email_status,
        "message": "Chúc mừng bạn đã hoàn thành bài thu âm! Thư cảm ơn đã được gửi đến email của bạn."
    }

@app.post("/api/v1/participants/withdraw")
def participant_withdraw(x_participant_token: str | None = Header(None), token: str | None = Query(None)):
    """Withdraw research consent and delete all recordings. Persists deletion tombstones for Drive."""
    pid = participant(x_participant_token, token)
    deleted_files = 0
    with db() as c:
        rows = c.execute("SELECT id, storage_key, drive_file_id FROM recordings WHERE participant_id=?", (pid,)).fetchall()
        for r in rows:
            rec_id = r["id"]
            key = r["storage_key"]
            if key and STORAGE == "local":
                p = Path(key)
                if p.is_file():
                    try:
                        p.unlink()
                        deleted_files += 1
                    except Exception:
                        pass
            if STORAGE == "sql_drive" or r["drive_file_id"]:
                enqueue_delete_job(c, rec_id, r["drive_file_id"])
            c.execute("DELETE FROM recording_audio WHERE recording_id=?", (rec_id,))
        c.execute("DELETE FROM recordings WHERE participant_id=?", (pid,))
        c.execute("DELETE FROM participants WHERE id=?", (pid,))
    return {"withdrawn": True, "deleted_recordings": len(rows), "deleted_files": deleted_files}

@app.get("/api/v1/tasks")
def tasks(course_id: str, x_participant_token: str | None = Header(None), token: str | None = Query(None)):
    pid = participant(x_participant_token, token)
    with db() as c:
        rows = c.execute("""
            SELECT p.id, p.text, p.language, p.target_terms, p.difficulty, p.category,
                   r.id AS recording_id, r.status, r.duration_seconds, r.drive_sync_status
            FROM prompts p
            LEFT JOIN recordings r ON r.prompt_id = p.id AND r.participant_id = ?
            WHERE p.course_id = ? AND p.published = 1
            ORDER BY p.created_at ASC, p.id ASC
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
    request: Request = None,
    background_tasks: BackgroundTasks = None,
    x_participant_token: str | None = Header(None),
    token: str | None = Query(None)
):
    validate_storage_backend(STORAGE)
    pid = participant(x_participant_token, token)
    with db() as c:
        part_row = c.execute("SELECT completed_at FROM participants WHERE id=?", (pid,)).fetchone()
        if part_row and part_row.get("completed_at"):
            raise HTTPException(403, "Bài thi đã hoàn thành, không thể nộp thêm hoặc sửa đổi bản ghi âm.")
        if not c.execute("SELECT 1 FROM prompts WHERE id=? AND published=1", (prompt_id,)).fetchone():
            raise HTTPException(404, "Prompt unavailable")
        existing_rec = c.execute(
            "SELECT id, storage_key, drive_file_id FROM recordings WHERE prompt_id=? AND participant_id=?",
            (prompt_id, pid)
        ).fetchone()

    body = await audio.read(MAX_BYTES + 1)
    if len(body) < 100:
        raise HTTPException(422, "File âm thanh quá ngắn hoặc rỗng")
    if len(body) > MAX_BYTES:
        raise HTTPException(413, "Dung lượng file vượt quá giới hạn 15MB")

    ext, norm_mime = detect_audio_format(body, audio.content_type)
    now = int(time.time())
    file_sha256 = hashlib.sha256(body).hexdigest()
    drive_ready = is_drive_connected(db)
    initial_sync_status = "pending" if (STORAGE == "sql_drive" or drive_ready) else "disabled"
    client_ip = get_client_ip(request)

    # If re-recording, preserve the existing recording ID and Drive file ID so only the latest audio is kept
    rec_id = existing_rec["id"] if existing_rec else str(uuid.uuid4())

    # Clean up old local storage file if extension/path changed
    if existing_rec and STORAGE == "local" and existing_rec["storage_key"]:
        old_path = Path(existing_rec["storage_key"])
        if old_path.is_file() and old_path.suffix != f".{ext}":
            try:
                old_path.unlink()
            except Exception:
                pass

    with db() as c:
        try:
            storage_key = store_audio_bytes(rec_id, body, ext, norm_mime, STORAGE, c, AUDIO_DIR)

            if existing_rec:
                # Update existing recording with the latest audio (idempotent overwrite)
                c.execute("""
                    UPDATE recordings
                    SET storage_key=?, sha256=?, mime=?, bytes=?, duration_seconds=?, format=?,
                        status='approved', created_at=?, drive_sync_status=?, client_ip=?
                    WHERE id=?
                """, (storage_key, file_sha256, norm_mime, len(body), duration, ext, now, initial_sync_status, client_ip, rec_id))

                if initial_sync_status == "pending":
                    from app.worker import enqueue_upload_job
                    c.execute(
                        "DELETE FROM drive_sync_jobs WHERE recording_id=? AND action='upload' AND status IN ('pending', 'retrying')",
                        (rec_id,)
                    )
                    enqueue_upload_job(c, rec_id)
            else:
                if initial_sync_status == "pending":
                    from app.worker import enqueue_upload_job
                    has_job = c.execute("SELECT 1 FROM drive_sync_jobs WHERE recording_id=? AND action='upload'", (rec_id,)).fetchone()
                    if not has_job:
                        enqueue_upload_job(c, rec_id)

                c.execute("""
                    INSERT INTO recordings(id, participant_id, prompt_id, storage_key, sha256, mime, bytes,
                                           duration_seconds, format, status, created_at, drive_sync_status, client_ip)
                    VALUES (?,?,?,?,?,?,?,?,?,'approved',?,?,?)
                """, (rec_id, pid, prompt_id, storage_key, file_sha256, norm_mime, len(body), duration, ext, now, initial_sync_status, client_ip))
        except Exception as exc:
            msg = str(exc)
            if "UNIQUE" in msg.upper() or "INTEGRITY" in msg.upper():
                raise HTTPException(409, "Bạn đã nộp bản ghi cho câu này rồi") from exc
            raise

    if initial_sync_status == "pending" and background_tasks is not None:
        def _bg_upload():
            try:
                from app.worker import process_all_outbox
                process_all_outbox(db, max_total=5)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning("Background drive upload error: %s", e)
        background_tasks.add_task(_bg_upload)

    return {
        "recording_id": rec_id,
        "format": ext,
        "bytes": len(body),
        "duration_seconds": duration,
        "status": "approved",
        "drive_sync_status": initial_sync_status,
        "message": "Nộp bản ghi thành công"
    }

# ----------------- Audio Streaming -----------------

@app.get("/api/v1/admin/recordings/{recording_id}/audio")
def admin_audio_stream(
    recording_id: str,
    range: str | None = Header(None),
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

        try:
            body = get_audio_bytes(recording_id, r["storage_key"], STORAGE, c)
        except FileNotFoundError:
            raise HTTPException(404, "Audio file missing")
        return stream_audio_response(body, r["mime"], range_header=range)

@app.get("/api/v1/recordings/{recording_id}/audio")
def participant_audio_stream(
    recording_id: str,
    range: str | None = Header(None),
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

        try:
            body = get_audio_bytes(recording_id, r["storage_key"], STORAGE, c)
        except FileNotFoundError:
            raise HTTPException(404, "Audio file missing")
        return stream_audio_response(body, r["mime"], range_header=range)

# ----------------- Admin Review Studio -----------------

@app.get("/api/v1/admin/recordings")
def admin_recordings_queue(
    course_id: str | None = None,
    participant_id: str | None = None,
    prompt_id: str | None = None,
    status: str | None = None,
    limit: int = 500,
    x_admin_key: str | None = Header(None),
    key: str | None = Query(None)
):
    admin(x_admin_key, key)
    query = """
        SELECT r.id, r.participant_id, r.prompt_id, p.course_id, p.text, p.target_terms, p.language, c.title AS course_title,
               part.participant_code, part.name AS participant_name, part.email AS participant_email,
               r.status, r.transcript, r.reviewer_notes,
               r.duration_seconds, r.bytes, r.mime, r.format, r.created_at, r.reviewed_at,
               r.drive_sync_status, r.drive_file_id
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
    if participant_id:
        query += " AND r.participant_id = ?"
        params.append(participant_id)
    if prompt_id:
        query += " AND r.prompt_id = ?"
        params.append(prompt_id)
    if status and status != "all":
        query += " AND r.status = ?"
        params.append(status)

    if participant_id:
        query += " ORDER BY p.created_at ASC, p.id ASC, r.created_at ASC"
    else:
        query += " ORDER BY r.created_at DESC"

    if limit > 0:
        query += " LIMIT ?"
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
        row = c.execute("SELECT drive_sync_status FROM recordings WHERE id=?", (recording_id,)).fetchone()
    drive_sync = row["drive_sync_status"] if row else None
    return {"status": target_status, "recording_id": recording_id, "drive_sync_status": drive_sync}

# ----------------- Admin Analytics & Stats -----------------

@app.get("/api/v1/admin/stats")
def admin_stats(x_admin_key: str | None = Header(None), key: str | None = Query(None)):
    admin(x_admin_key, key)
    with db() as c:
        courses_row = c.execute("SELECT COUNT(*) FROM courses").fetchone()
        courses_count = courses_row[0] if courses_row else 0
        prompts_total_row = c.execute("SELECT COUNT(*) FROM prompts").fetchone()
        prompts_total = prompts_total_row[0] if prompts_total_row else 0
        prompts_pub_row = c.execute("SELECT COUNT(*) FROM prompts WHERE published=1").fetchone()
        prompts_published = prompts_pub_row[0] if prompts_pub_row else 0
        part_row = c.execute("SELECT COUNT(*) FROM participants").fetchone()
        part_count = part_row[0] if part_row else 0

        recs_total_row = c.execute("SELECT COUNT(*) FROM recordings").fetchone()
        recs_total = recs_total_row[0] if recs_total_row else 0
        recs_app_row = c.execute("SELECT COUNT(*) FROM recordings WHERE status != 'rejected'").fetchone()
        recs_approved = recs_app_row[0] if recs_app_row else 0
        recs_rej_row = c.execute("SELECT COUNT(*) FROM recordings WHERE status='rejected'").fetchone()
        recs_rejected = recs_rej_row[0] if recs_rej_row else 0
        recs_rer_row = c.execute("SELECT COUNT(*) FROM recordings WHERE status='rerecord'").fetchone()
        recs_rerecord = recs_rer_row[0] if recs_rer_row else 0
        recs_pen_row = c.execute("SELECT COUNT(*) FROM recordings WHERE status='pending_review'").fetchone()
        recs_pending = recs_pen_row[0] if recs_pen_row else 0

        app_dur_row = c.execute("SELECT COALESCE(SUM(duration_seconds), 0) FROM recordings WHERE status != 'rejected'").fetchone()
        approved_duration = app_dur_row[0] if app_dur_row else 0
        tot_dur_row = c.execute("SELECT COALESCE(SUM(duration_seconds), 0) FROM recordings").fetchone()
        total_duration = tot_dur_row[0] if tot_dur_row else 0

        # Detailed duration statistics across all recordings
        dur_stats_row = c.execute("""
            SELECT COALESCE(SUM(duration_seconds), 0.0),
                   COALESCE(AVG(CASE WHEN duration_seconds > 0 THEN duration_seconds ELSE NULL END), 0.0),
                   COALESCE(MIN(CASE WHEN duration_seconds > 0 THEN duration_seconds ELSE NULL END), 0.0),
                   COALESCE(MAX(duration_seconds), 0.0)
            FROM recordings
        """).fetchone()
        tot_dur = dur_stats_row[0] if dur_stats_row else 0.0
        avg_dur = dur_stats_row[1] if dur_stats_row else 0.0
        min_dur = dur_stats_row[2] if dur_stats_row else 0.0
        max_dur = dur_stats_row[3] if dur_stats_row else 0.0

        # Detailed per-prompt duration statistics (count, total, avg, min, max)
        prompt_stats_rows = c.execute("""
            SELECT p.id as prompt_id,
                   p.text as prompt_text,
                   p.course_id,
                   c.title as course_title,
                   COUNT(r.id) as recordings_count,
                   COALESCE(SUM(r.duration_seconds), 0.0) as total_duration_seconds,
                   COALESCE(AVG(CASE WHEN r.duration_seconds > 0 THEN r.duration_seconds ELSE NULL END), 0.0) as avg_duration_seconds,
                   COALESCE(MIN(CASE WHEN r.duration_seconds > 0 THEN r.duration_seconds ELSE NULL END), 0.0) as min_duration_seconds,
                   COALESCE(MAX(r.duration_seconds), 0.0) as max_duration_seconds
            FROM prompts p
            JOIN courses c ON c.id = p.course_id
            LEFT JOIN recordings r ON r.prompt_id = p.id
            GROUP BY p.id, p.text, p.course_id, c.title, p.created_at
            ORDER BY c.title ASC, p.created_at ASC, p.id ASC
        """).fetchall()

        prompt_stats = []
        for r in prompt_stats_rows:
            prompt_stats.append({
                "prompt_id": r["prompt_id"],
                "prompt_text": r["prompt_text"],
                "course_id": r["course_id"],
                "course_title": r["course_title"],
                "recordings_count": int(r["recordings_count"]),
                "total_duration_seconds": round(float(r["total_duration_seconds"]), 1),
                "avg_duration_seconds": round(float(r["avg_duration_seconds"]), 1),
                "min_duration_seconds": round(float(r["min_duration_seconds"]), 1),
                "max_duration_seconds": round(float(r["max_duration_seconds"]), 1),
            })

        course_breakdown = c.execute("""
            SELECT c.id, c.title,
                   COUNT(DISTINCT p.id) as prompts_count,
                   COUNT(r.id) as recordings_count,
                   SUM(CASE WHEN r.status != 'rejected' THEN 1 ELSE 0 END) as approved_count
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
            "duration_stats": {
                "total_seconds": round(float(tot_dur), 1),
                "avg_seconds": round(float(avg_dur), 1),
                "min_seconds": round(float(min_dur), 1),
                "max_seconds": round(float(max_dur), 1),
            },
            "prompt_duration_stats": prompt_stats,
            "courses": [dict(r) for r in course_breakdown]
        }

# ----------------- Export Dataset Manifest & ZIP -----------------

def get_approved_dataset_rows():
    """Returns approved recordings. In sql_drive mode, restricts export strictly to verified synced files."""
    with db() as c:
        return c.execute("""
            SELECT r.id as recording_id, r.participant_id, part.participant_code,
                   p.course_id, c.title as course_title,
                   p.id as prompt_id, p.text as prompt_text,
                   r.transcript as verbatim_transcript,
                   p.target_terms, p.language, p.difficulty, p.category,
                   r.duration_seconds, r.bytes, r.mime, r.format, r.sha256,
                   r.storage_key, r.created_at, r.reviewed_at,
                   r.drive_sync_status, r.drive_file_id,
                   part.survey
            FROM recordings r
            JOIN prompts p ON p.id = r.prompt_id
            JOIN courses c ON c.id = p.course_id
            JOIN participants part ON part.id = r.participant_id
            WHERE r.status != 'rejected'
              AND (? != 'sql_drive' OR r.drive_sync_status = 'synced')
            ORDER BY r.created_at ASC
        """, (STORAGE,)).fetchall()

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

        with db() as c:
            for r in rows:
                rec_id = r["recording_id"]
                fmt = r["format"]
                if STORAGE == "local":
                    storage_key = r["storage_key"]
                    if storage_key:
                        p = Path(storage_key)
                        if p.is_file():
                            zf.write(p, arcname=f"audio/{rec_id}.{fmt}")
                elif STORAGE in ("sql", "sql_drive"):
                    audio_row = c.execute("SELECT body FROM recording_audio WHERE recording_id=?", (rec_id,)).fetchone()
                    if not audio_row or audio_row[0] is None:
                        raise HTTPException(500, f"Audio data missing in database for recording {rec_id}")
                    zf.writestr(f"audio/{rec_id}.{fmt}", bytes(audio_row[0]))

    zip_buffer.seek(0)
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="liemwhisper_approved_dataset.zip"'}
    )
