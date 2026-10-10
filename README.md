# LiemWhisper

**LiemWhisper — Vietnamese–English Code-Switched Speech & Technical-Term Retrieval Research**

> Status: research scaffold / specification. This repository does **not yet** contain a trained alignment model, a validated dataset, or a production-ready recording platform.

## Research objective

Learn an **audio–text shared embedding space** for recognizing and retrieving English technical terms spoken inside Vietnamese sentences, including Vietnamese-accented English. Initial domain: **Software Testing**; later evaluate transfer to **Software Requirements Engineering** and an unseen course.

**Research hypothesis:** phonetic-aware cross-modal contrastive learning can improve spoken technical-term retrieval, especially for unseen terms and speakers, without retraining an entire ASR model for every new textbook.

- Speech baseline: PhoWhisper / Whisper; optionally freeze its speech encoder.
- Text baseline: multilingual text encoder, with a phoneme/G2P variant.
- Alignment: projection heads + symmetric contrastive loss, hard negatives, optional phonetic-aware learning.
- Retrieval: cosine similarity + FAISS, evaluated first at **isolated term clips**; in-sentence spotting is a later milestone.
- Downstream: optional retrieval-assisted PhoWhisper correction, always grounded in original audio, preserving what the student actually said.

## System scope

The project consists of three independently developed workstreams:

1. **Data collection platform:** admin creates courses, datasets, sentences/prompts and assignments. Student gives informed research consent, completes a short survey, records sentences received from server, plays back, and submits a labeled audio example. Admin reviews and approves/rejects each recording.
2. **Research source:** dataset validation, speaker-disjoint and term-disjoint splits, baselines, dual encoders, contrastive training, evaluation and optional ASR integration.
3. **Paper workspace:** literature matrix, protocol, experimental log and article drafts. Claims and results must come from reproducible experiments.

### Suggested monorepo layout

```text
LiemWhisper/
├── README.md
├── todo.md
├── .gitignore
├── .env.example
├── web/
│   ├── README.md
│   ├── client/                 # student/admin browser application
│   └── backend/                # API, authentication, DB, Drive integration
├── research/
│   ├── README.md
│   └── src/liemwhisper/       # training and evaluation modules (planned)
├── paper/
│   ├── README.md
│   ├── protocol.md
│   └── literature-matrix.md
└── docs/
    ├── architecture.md
    └── data-governance.md
```

Git does not track empty directories; the provided README/placeholder files establish the structure.

## Collection workflow

```text
Admin: Create course -> dataset -> versioned prompt list -> publish
Student: Consent -> survey -> assigned prompt -> record -> playback -> submit
API: Validate metadata/audio -> private storage -> metadata and labels in DB
Reviewer: Listen -> accept / reject / ask for rerecord -> lock approved labels
Research: export consent-eligible approved corpus -> audit -> freeze splits
```

Each recording is one **utterance instance** identified by `recording_id`, associated with `prompt_id`, `speaker_pseudonym`, `course_id` and a versioned exact script. Text displayed to the student is an initial **prompt label**, not automatically verified evidence of what was spoken. A reviewer must verify the verbatim transcript and any language or term annotations.

**Suggested survey** (collect the minimum necessary): age band or adult eligibility, voluntary language proficiency self-report, prior software-course familiarity, audio device category and recording environment. Do not require sensitive or unnecessary demographics.

**Audio**: request user permission via browser, record one prompted sentence at a time, retain original upload and its hash, keep format/sample rate/length and device metadata; normalize to 16kHz mono WAV only as a derivative for modeling. Require a reasonable maximum duration, format validation, upload limits and safe retry with idempotency key.

## Google Drive storage

Private Google Drive is a **binary storage destination**, not the primary metadata database.

- Browser -> backend upload; **never expose Drive credentials or a service-account key to the browser**.
- Server stores audio in a restricted Drive folder and stores `drive_file_id`, checksum, storage state, consent scope, prompt version, label status and reviewer history in PostgreSQL.
- Use a dedicated service account with a Shared Drive or a clearly authorized delegated setup. The service account needs actual folder permissions; a Drive folder ID alone is insufficient.
- Per-recording lifecycle: `pending_upload -> uploaded -> pending_review -> approved/rejected -> exported`; retries must be idempotent and failures recoverable.
- Restrict access to organizers/reviewers; define retention/deletion, withdrawal/revocation and audit logging. **Never publish student audio, transcripts, identifiers or Drive credentials to GitHub.**
- Folder hierarchy example: `LiemWhisper/{course_id}/{dataset_version}/{speaker_pseudonym}/{recording_id}.webm` (path is a convention, access rights remain authoritative).

See [docs/data-governance.md](docs/data-governance.md) and [docs/architecture.md](docs/architecture.md).

## Suggested technology choices

| Layer | Initial choice |
| --- | --- |
| Web client | Next.js / React + TypeScript; MediaRecorder |
| Backend | FastAPI + Pydantic |
| Auth | Managed university sign-in or secure account login with RBAC |
| Metadata DB | PostgreSQL + Alembic |
| Media storage | Google Drive API, server-side |
| Async processing | Worker/queue for validation and Drive upload |
| Speech experiments | PyTorch, Transformers, PhoWhisper, torchaudio |
| Embeddings | frozen speech/text backbones, trainable projection heads |
| Retrieval | FAISS; cosine similarity |
| Deployment | Docker Compose + Jenkins (no required GitHub Actions) |

These are architectural choices, **not a claim that all services have been implemented**.

## MVP acceptance criteria

- Admin can create courses and versioned sentence sets; publish/unpublish a dataset.
- Student explicitly consents, fills survey, receives assigned prompts and records/submits one audio file per prompt.
- Every file is linked to its immutable prompt version and a pseudonymous participant ID.
- Server stores binary in restricted Drive and metadata in DB, using idempotency and asynchronous retry.
- Reviewer can listen, flag incorrect readings and approve a corrected verbatim label.
- Approved, consent-eligible data can be exported with manifest and hashes, without identity leakage or cross-split duplication.
- Research pipeline reports Recall@1/5, MRR, unseen-speaker/term retrieval, hard negatives, latency and downstream ASR WER/CER when integrated.

## Research protocol essentials

The primary task is **lexical/phonetic spoken-term retrieval**, not generic semantic speech retrieval. Audio saying “kiểm thử hồi quy” must **not** be labeled as having said “regression testing”, despite semantic equivalence. Include utterances without target terms and near-pronunciation distractors. Keep **speaker-disjoint**, **term-disjoint**, and when feasible **course-disjoint** evaluation. Avoid test contamination from glossary construction and hyperparameter tuning.

Keep separate: (1) a sentence prompt shown to the participant, (2) verified spoken transcript, and (3) technical terms actually spoken with span/timestamp provenance. Weak labels from prompts are not verified transcriptions.

Do not report speculative accuracy or claim novelty solely from combining pretrained models. See [paper/protocol.md](paper/protocol.md).

## Work plan

See [todo.md](todo.md) for phased tasks, deliverables and definition of done. Scaffold status is not production readiness.

## Setup status

This initial repository commit supplies documentation and a minimal development scaffold. Refer to `web/README.md` and `research/README.md` for the intended setup. Configure `.env` from `.env.example` on the server only; never commit keys.

## Data and licensing

Use the university's applicable research-ethics process before collecting voices. Participation is voluntary and separate from grading. Textbook terms can be indexed where permitted, but uploading entire copyrighted books or redistributing them requires rights. Model and corpus licenses must be reviewed before publication.
