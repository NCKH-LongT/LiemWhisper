# LiemWhisper collection API

**Planned:** FastAPI, PostgreSQL, SQLAlchemy, Alembic, background worker and Google Drive API integration. No operational service is claimed in this scaffold.

Proposed tables: `users`, `participants`, `consents`, `survey_responses`, `courses`, `datasets`, `dataset_versions`, `prompts`, `assignments`, `recordings`, `transcripts`, `language_spans`, `term_spans`, `reviews`, `storage_objects`, `audit_events`.

Key constraints: one assignment references immutable prompt version; recording stores pseudonymous speaker, Drive file ID, cryptographic checksum, duration, codec, statuses and reviewed verbatim label separately; never permit participants to select arbitrary Drive file IDs. Implement withdrawal and deletion consistently across DB/Drive/exports.
