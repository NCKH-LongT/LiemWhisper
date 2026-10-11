"""LiemWhisper recording-collection API (pilot, not production hardened)."""
import hashlib
import io
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import contextmanager
from pathlib import Path

from fastapi import FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel, Field

ROOT = Path(os.getenv("DATA_ROOT", "./private-data")).resolve()
DB = ROOT / "collection.sqlite3"
STORAGE = os.getenv("STORAGE_BACKEND", "local")
MAX_BYTES = int(os.getenv("MAX_AUDIO_BYTES", "10000000"))
ADMIN_KEY = os.getenv("ADMIN_API_KEY", "")
ORIGIN = os.getenv("WEB_PUBLIC_URL", "http://localhost:3000")
ROOT.mkdir(parents=True, exist_ok=True)
app = FastAPI(title="LiemWhisper Collection API", version="0.2.0")
app.add_middleware(CORSMiddleware, allow_origins=[ORIGIN], allow_methods=["GET","POST"], allow_headers=["*"])

@contextmanager
def db():
    conn = sqlite3.connect(DB, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()

with db() as c:
    c.executescript("""
    CREATE TABLE IF NOT EXISTS courses(id TEXT PRIMARY KEY, title TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS prompts(id TEXT PRIMARY KEY, course_id TEXT NOT NULL REFERENCES courses(id),
        text TEXT NOT NULL, language TEXT NOT NULL DEFAULT 'vi-en', published INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS participants(id TEXT PRIMARY KEY, token_hash TEXT NOT NULL UNIQUE,
        consent_version TEXT NOT NULL, consent_at INTEGER NOT NULL, survey TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS recordings(id TEXT PRIMARY KEY, participant_id TEXT NOT NULL REFERENCES participants(id),
        prompt_id TEXT NOT NULL REFERENCES prompts(id), storage_key TEXT NOT NULL, sha256 TEXT NOT NULL,
        mime TEXT NOT NULL, bytes INTEGER NOT NULL, status TEXT NOT NULL DEFAULT 'pending_review',
        transcript TEXT, created_at INTEGER NOT NULL, UNIQUE(participant_id,prompt_id));
    """)

def admin(x_admin_key: str | None):
    if not ADMIN_KEY or not x_admin_key or not secrets.compare_digest(ADMIN_KEY, x_admin_key):
        raise HTTPException(403, "Admin credential required")

def participant(x_participant_token: str | None):
    if not x_participant_token:
        raise HTTPException(401, "Participant token required")
    h = hashlib.sha256(x_participant_token.encode()).hexdigest()
    with db() as c:
        row = c.execute("SELECT id FROM participants WHERE token_hash=?", (h,)).fetchone()
    if not row:
        raise HTTPException(401, "Invalid participant token")
    return row["id"]

def store(recording_id: str, body: bytes, mime: str):
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
            obj = drive.files().create(body={"name": recording_id + ".webm", "parents": [folder]},
                media_body=media, fields="id", supportsAllDrives=True).execute()
            return obj["id"]
        except Exception as exc:
            raise HTTPException(503, "Private Drive upload failed") from exc
    if STORAGE != "local":
        raise HTTPException(503, "Unsupported storage backend")
    folder = ROOT / "audio"
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / (recording_id + ".webm")
    path.write_bytes(body)
    return str(path)

class CourseInput(BaseModel):
    title: str = Field(min_length=3, max_length=160)

class PromptInput(BaseModel):
    text: str = Field(min_length=3, max_length=2000)
    language: str = Field(default="vi-en", pattern="^(vi|en|vi-en)$")

class SignupInput(BaseModel):
    consent: bool
    consent_version: str = Field(min_length=1, max_length=30)
    familiarity: str = Field(default="", max_length=100)
    english_level: str = Field(default="", max_length=100)
    microphone: str = Field(default="", max_length=100)

class ReviewInput(BaseModel):
    approved: bool
    transcript: str = Field(min_length=1, max_length=4000)

@app.get("/health")
def health():
    return {"status": "ok", "storage": STORAGE, "production_ready": False}

@app.get("/api/v1/capabilities")
def capabilities():
    return {"recording_upload_enabled": True, "google_drive_enabled": STORAGE == "drive",
            "authentication": "admin-key and pseudonymous bearer token (pilot)",
            "production_ready": False}

@app.post("/api/v1/admin/courses")
def create_course(data: CourseInput, x_admin_key: str | None = Header(None)):
    admin(x_admin_key)
    id_ = str(uuid.uuid4())
    with db() as c:
        c.execute("INSERT INTO courses VALUES (?,?)", (id_, data.title))
    return {"id": id_, "title": data.title}

@app.post("/api/v1/admin/courses/{course_id}/prompts")
def create_prompt(course_id: str, data: PromptInput, x_admin_key: str | None = Header(None)):
    admin(x_admin_key)
    id_ = str(uuid.uuid4())
    with db() as c:
        if not c.execute("SELECT 1 FROM courses WHERE id=?", (course_id,)).fetchone():
            raise HTTPException(404, "Course not found")
        c.execute("INSERT INTO prompts VALUES (?,?,?,?,0)", (id_, course_id, data.text, data.language))
    return {"id": id_, "published": False}

@app.post("/api/v1/admin/prompts/{prompt_id}/publish")
def publish(prompt_id: str, x_admin_key: str | None = Header(None)):
    admin(x_admin_key)
    with db() as c:
        n = c.execute("UPDATE prompts SET published=1 WHERE id=?", (prompt_id,)).rowcount
    if not n:
        raise HTTPException(404, "Prompt not found")
    return {"published": True}

@app.get("/api/v1/courses")
def courses():
    with db() as c:
        return [dict(row) for row in c.execute(
            "SELECT DISTINCT c.id,c.title FROM courses c JOIN prompts p ON p.course_id=c.id WHERE p.published=1")]

@app.post("/api/v1/participants")
def signup(data: SignupInput):
    if not data.consent:
        raise HTTPException(400, "Explicit consent is required")
    token, id_ = secrets.token_urlsafe(32), str(uuid.uuid4())
    import json
    survey = json.dumps({"familiarity": data.familiarity, "english_level": data.english_level,
                          "microphone": data.microphone})
    with db() as c:
        c.execute("INSERT INTO participants VALUES (?,?,?,?,?)",
                  (id_, hashlib.sha256(token.encode()).hexdigest(), data.consent_version, int(time.time()), survey))
    return {"participant_id": id_, "participant_token": token, "warning": "Save token; not recoverable"}

@app.get("/api/v1/tasks")
def tasks(course_id: str, x_participant_token: str | None = Header(None)):
    pid = participant(x_participant_token)
    with db() as c:
        return [dict(row) for row in c.execute("""
        SELECT p.id,p.text,p.language, r.id AS recording_id, r.status
        FROM prompts p LEFT JOIN recordings r ON r.prompt_id=p.id AND r.participant_id=?
        WHERE p.course_id=? AND p.published=1 ORDER BY p.rowid""", (pid, course_id))]

@app.post("/api/v1/recordings")
async def upload(prompt_id: str = Form(...), audio: UploadFile = File(...),
                 x_participant_token: str | None = Header(None)):
    pid = participant(x_participant_token)
    if audio.content_type not in ("audio/webm", "audio/webm;codecs=opus"):
        raise HTTPException(415, "Only WebM/Opus audio accepted in pilot")
    with db() as c:
        if not c.execute("SELECT 1 FROM prompts WHERE id=? AND published=1", (prompt_id,)).fetchone():
            raise HTTPException(404, "Prompt unavailable")
        if c.execute("SELECT 1 FROM recordings WHERE prompt_id=? AND participant_id=?", (prompt_id, pid)).fetchone():
            raise HTTPException(409, "Already submitted this prompt")
    body = await audio.read(MAX_BYTES + 1)
    if len(body) < 100 or len(body) > MAX_BYTES or not body.startswith(b"\x1a\x45\xdf\xa3"):
        raise HTTPException(422, "Invalid WebM audio or upload size")
    id_ = str(uuid.uuid4())
    key = store(id_, body, audio.content_type)
    with db() as c:
        try:
            c.execute("""INSERT INTO recordings(id,participant_id,prompt_id,storage_key,sha256,mime,bytes,created_at)
                VALUES (?,?,?,?,?,?,?,?)""",
                (id_, pid, prompt_id, key, hashlib.sha256(body).hexdigest(), audio.content_type,
                 len(body), int(time.time())))
        except sqlite3.IntegrityError as exc:
            raise HTTPException(409, "Already submitted this prompt") from exc
    return {"recording_id": id_, "status": "pending_review"}

@app.get("/api/v1/admin/recordings")
def review_queue(x_admin_key: str | None = Header(None)):
    admin(x_admin_key)
    with db() as c:
        return [dict(row) for row in c.execute("""SELECT r.id,r.prompt_id,p.text,r.status,r.transcript,
          r.created_at,r.bytes FROM recordings r JOIN prompts p ON p.id=r.prompt_id
          ORDER BY r.created_at DESC LIMIT 200""")]

@app.get("/api/v1/admin/recordings/{recording_id}/audio")
def admin_audio(recording_id: str, x_admin_key: str | None = Header(None)):
    admin(x_admin_key)
    with db() as c:
        r = c.execute("SELECT storage_key,mime FROM recordings WHERE id=?", (recording_id,)).fetchone()
    if not r:
        raise HTTPException(404, "Not found")
    if STORAGE == "local":
        path = Path(r["storage_key"]).resolve()
        if not path.is_relative_to((ROOT / "audio").resolve()) or not path.is_file():
            raise HTTPException(404, "File unavailable")
        return Response(path.read_bytes(), media_type=r["mime"])
    raise HTTPException(501, "Drive review streaming not implemented")

@app.post("/api/v1/admin/recordings/{recording_id}/review")
def review(recording_id: str, data: ReviewInput, x_admin_key: str | None = Header(None)):
    admin(x_admin_key)
    with db() as c:
        n = c.execute("UPDATE recordings SET status=?, transcript=? WHERE id=?",
                      ("approved" if data.approved else "rejected", data.transcript, recording_id)).rowcount
    if not n:
        raise HTTPException(404, "Recording not found")
    return {"status": "approved" if data.approved else "rejected"}
