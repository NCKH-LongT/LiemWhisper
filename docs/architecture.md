# System architecture (planned)

```text
Student Browser (Next.js, MediaRecorder)           Admin/Reviewer Browser
             |                                               |
             +---------- HTTPS / Auth / RBAC ----------------+
                                     |
                           FastAPI Collection API
                           |        |        |
                       PostgreSQL  Queue   Audit/Consent
                                    |
                           Media Upload Worker
                                    |
                    Restricted Google Drive Folder
                                    |
                    Approved Corpus Export (private)
                                    |
        Dataset validation / speech-text-phoneme alignment
                                    |
                         FAISS / retrieval research
```

## Boundaries
- Browser never sees Drive credentials or other participants' recordings.
- Backend holds metadata, versioned prompts, consent, assignments, review and storage state.
- Queue worker retries upload without duplicate records and verifies hashes.
- A separate offline research job reads only approved exports within consent scope.
- Research vector index contains approved text/audio-derived embeddings only as authorized.
- Paper workspace stores findings and de-identified tables, not raw data.

## Key entities
`Course -> Dataset -> DatasetVersion -> Prompt -> Assignment -> Recording -> Review`.
`Participant -> Consent -> SurveyResponse`.
`Recording -> StorageObject` (Drive file ID, checksum, status), `Recording -> TranscriptRevision / TermSpan / LanguageSpan`.

## Suggested access roles
**Admin:** manage courses, prompts, assignments, reviewer access and exports.
**Reviewer:** restricted assigned recordings, verified labels and review decisions.
**Student:** own consent/survey/assignments/submissions only.
**Researcher:** separately authorized exports with pseudonymous IDs, never participant identity map by default.
