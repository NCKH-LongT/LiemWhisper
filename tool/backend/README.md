# LiemWhisper recording API — pilot

Implemented in `app/main.py` with FastAPI, SQLite metadata, secure random participant tokens (only their SHA256 hash is stored), explicit consent flag and survey, versioned-by-identity prompt IDs, recording uploads and basic admin reviews.

**Safety:** this is a developer pilot, **not** a production-grade service. Missing: institutional research approval, robust organization auth/SSO, participant withdrawal/deletion, strong upload inspection and duration limits, administrative audit trail, Drive playback, migrations, transaction-safe storage reconciliation, rate limiting, automatic assignment quotas, prompt/version editing, backup policy. Do not deploy publicly or collect real students' voice until these are implemented and assessed.

## Local start

```bash
cd tool/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
export ADMIN_API_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(32))')"
export WEB_PUBLIC_URL=http://localhost:3000
# Default storage remains repository-root/private-data; override DATA_ROOT only intentionally.
export STORAGE_BACKEND=local
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Visit http://127.0.0.1:8000/docs and http://127.0.0.1:8000/health. `private-data` is gitignored.

## Google Drive backend (optional pilot)

The backend uses Google Application Default Credentials (ADC), not browser credentials.

```bash
export STORAGE_BACKEND=drive
export GOOGLE_DRIVE_FOLDER_ID=YOUR_PRIVATE_FOLDER_ID
export GOOGLE_APPLICATION_CREDENTIALS=/secure/path/google-service-account.json
```

Grant the principal write access to the restricted folder or configured Shared Drive. `drive.file` scope and Shared Drive permissions must be tested with the actual account. The backend uploads new recordings server-side, storing only the resulting Drive file ID in SQLite. **Audio playback from Drive is not implemented**, and a Drive upload followed by metadata DB failure could leave an orphaned object; production requires cleanup/reconciliation and resumable uploads. Never put credentials in the repository or client environment.

## Endpoints

- `POST /api/v1/admin/courses` with `x-admin-key`
- `POST /api/v1/admin/courses/{id}/prompts` and `POST /api/v1/admin/prompts/{id}/publish`
- `GET /api/v1/courses` for published courses
- `POST /api/v1/participants` with explicit consent and short survey; returns one-time participant token
- `GET /api/v1/tasks?course_id=...` with `x-participant-token`
- `POST /api/v1/recordings` as multipart `prompt_id` and WebM audio, with participant token
- `GET /api/v1/admin/recordings` for review queue
- `GET /api/v1/admin/recordings/{id}/audio` local-storage only
- `POST /api/v1/admin/recordings/{id}/review` with reviewed verbatim transcript and decision

WebM/Opus supported on Chrome/Edge; Safari recording currently unsupported. Review transcriptions are human labels; never blindly use presented prompt as ground truth.

Run tests with `pytest -q`. Avoid mixing tests and real data by setting `DATA_ROOT` to a temporary directory before importing the app.
