# Pilot implementation status — 2026-10-11

## Delivered to main
- FastAPI API: course/prompt creation, prompt publishing, consent and survey, pseudonymous tokens, task listing, WebM upload, admin review.
- SQLite local metadata and backend-side Google Drive upload option using ADC; local private audio storage for development.
- Next.js browser interface: consent/survey, course selection, record/stop/playback/re-record/upload, admin course/prompt/review controls.
- Integration smoke test covering admin access, consent, assignment, upload and review.

## Not yet ready for student data
1. Institutionally approved consent language and withdrawal/deletion workflow.
2. Secure SSO/session-based authentication for admins and participants. Pilot admin-key UI must NOT be Internet exposed.
3. True audio decoding/duration/format validation (pilot currently checks WebM magic + bytes only), anti-malware and rate limiting.
4. Google Drive download/playback for reviewers; upload transaction reconciliation and retry queue.
5. Production PostgreSQL, migrations, audits, versioning, backup and restore drills.
6. Recording duration limit, browser compatibility, accessibility and final end-to-end testing.
7. Multiple task audio UI should be restricted to prevent applying a previously recorded blob to another prompt; use one selected recording target before expanding pilots.

## Operational rule
Do not deploy to a public URL or invite students yet. Use dummy/synthetic recordings for technical validation only. Test automation is committed but has not been executed by the remote GitHub connector.
