# Data collection web platform

Planned architecture:
- `client/`: Next.js/TypeScript for student and admin/reviewer UI.
- `backend/`: FastAPI/Pydantic + PostgreSQL, server-side Google Drive adapter and asynchronous upload worker.
- Recording workflow: explicit consent -> minimum survey -> server-assigned prompt -> record/playback/re-record -> authenticated upload -> reviewer verification -> approved export.

**Current status:** directories and planning docs only; no deployed application. Avoid treating audio sent with a displayed sentence as a verified verbatim label.

### Proposed client pages
`/login`, `/consent`, `/survey`, `/tasks`, `/record/[assignmentId]`, `/progress`, `/admin/courses`, `/admin/datasets`, `/admin/review`, `/admin/exports`.

### Suggested API
`POST /auth/login`; `GET /courses`; `POST /admin/datasets`; `POST /admin/datasets/{id}/prompts`; `POST /consents`; `POST /surveys`; `GET /assignments/next`; `POST /recordings`; `GET /recordings/{id}`; `POST /reviews/{id}`; `POST /admin/exports`.

For security, implement authentication, rate limits, upload allowlist, server-side validation, RBAC and consent checks before accepting any real audio.
