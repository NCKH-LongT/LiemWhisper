# LiemWhisper — TODO / Research & Development Backlog

> Status: planned unless checked and supported by a merged implementation and a verification record. Priority: secure collection platform first, independent retrieval experiment second.

## Phase 0 — Governance and project setup
- [x] Define product/research scope and directory layout in README.
- [ ] Confirm university ethics/IRB-equivalent review before recruiting students.
- [ ] Define consent and withdrawal procedure (no academic penalty for refusing).
- [ ] Define dataset license, speaker anonymity, retention, deletion and access roles.
- [ ] Create local dev environment, formatting, lint, tests, container setup and Jenkins pipeline.
- [ ] Protect secrets and personally identifiable data; document backups.

## Phase 1 — Backend / Admin — MVP
- [ ] FastAPI app, PostgreSQL schema, Alembic migrations, Swagger docs and healthcheck.
- [ ] RBAC: Admin, Reviewer, Student; authentication, session expiry, access audit.
- [ ] Course CRUD and dataset/version CRUD; import/upload approved text prompts.
- [ ] Sentence/utterance prompts: language, expected text, glossary tags, difficulty, source/license.
- [ ] Generate unique, balanced prompt assignments per consenting participant.
- [ ] Survey configuration; consent records with policy version and timestamp.
- [ ] Issue one-time/idempotent recording upload tokens and upload limits.
- [ ] Server-side Drive integration with queue, retries, checksum, state machine and duplicate detection.
- [ ] Reviewer labeling API: audio playback, verbatim correction, language/term spans, approve/reject/re-record.
- [ ] Admin dashboard: collection progress, coverage per prompt, review queue, approved minutes.
- [ ] Export approved, consent-eligible manifest with pseudonymous IDs and access-control checks.
- [ ] Automated tests: RBAC isolation, expired consent, invalid audio, storage outage/retry, deletion and export filters.

## Phase 2 — Student web recording — MVP
- [ ] Responsive Next.js pages: invitation/login, informed consent, survey, task queue.
- [ ] Browser microphone permissions, record/stop, playback, re-record and submit.
- [ ] Present exact server-provided prompt text, course, terms and recording guidance.
- [ ] Persist assignment state on server and clearly indicate pending/confirmed uploads.
- [ ] Handle mic denied, browser reload, poor connectivity, unsupported MediaRecorder formats.
- [ ] Accessibility and mobile browser test (Chrome/Edge/Safari), user acceptance testing.
- [ ] Restrict collection to authorized participants and prevent prompt access leakage.

## Phase 3 — Data quality and annotation
- [ ] Dataset manifest schema with speaker, audio, prompt, transcript, language labels, term spans.
- [ ] Verify raw sample rate/codec/duration; derive 16-kHz mono WAV without overwriting originals.
- [ ] Quality checks: clipping, silence, duplicates, truncated utterances, low-volume recordings.
- [ ] At least two independent annotators for a subset, adjudication protocol and agreement reporting.
- [ ] Split by speaker and target term; create out-of-domain test when data supports it.
- [ ] Human-verified transcript != expected prompt; flag incomplete or altered readings.
- [ ] Publish only aggregate/anonymized statistics unless explicit rights allow release of samples.

## Phase 4 — Research baselines
- [ ] Freeze model/checkpoint revisions and experimental configuration.
- [ ] Frozen PhoWhisper speech encoder + pooled projection.
- [ ] Multilingual text encoder + projection; normalize to shared 256/512-dimensional space.
- [ ] Baseline text G2P/IPA encoder and phoneme-only retrieval.
- [ ] Symmetric InfoNCE with duplicate-positive handling.
- [ ] FAISS vector search and Top-K retrieval on isolated spoken technical terms.
- [ ] Baseline against lexical matching, untrained projections and existing speech–text retrieval approaches.
- [ ] Evaluate Recall@1, Recall@5, MRR, hard-negative accuracy, calibration and latency.
- [ ] Report confidence intervals clustered by speaker, with clean unseen-term test.

## Phase 5 — Proposed phonetic-aware method
- [ ] Phoneme supervision using independently validated pronunciation labels and variants.
- [ ] Acoustic confusability-based hard negatives (e.g., test case / test data).
- [ ] Compare text-only, phoneme-only and fused text+phoneme encoders.
- [ ] Ablation phonetic loss, fusion weights, projection dimension and frozen vs LoRA encoder.
- [ ] Include speech segments with **no glossary terms** and report false positive insertions.
- [ ] Test fresh-course glossary without ASR retraining.

## Phase 6 — Downstream ASR (optional, after retrieval result)
- [ ] Localize suspicious audio spans (forced alignment/sliding-window).
- [ ] Retrieve candidates from book-derived glossary.
- [ ] Verify candidates using original audio; no auto-correction based solely on book relevance.
- [ ] Compare PhoWhisper raw, hotwords, semantic retrieval, phonetic retrieval and proposed fusion.
- [ ] Evaluate WER/CER, technical-term recall, erroneous insertions and real-time factor.
- [ ] Keep raw transcript and corrected transcript separate, especially in exam scoring.

## Phase 7 — Paper and reproducibility
- [ ] Literature review matrix with primary-source citation and precise prior contributions.
- [ ] Preregister RQs, dataset protocol, splits, losses and primary metrics.
- [ ] Produce reproducible configs, fixed seeds, pinned checkpoints and scripts.
- [ ] Report negative results, failure cases, speaker variability and ethics.
- [ ] Draft Introduction / Related Work / Method / Experimental Setup / Results / Limitations.
- [ ] Check suitable CFP/journal scope, indexing/quartile for the publication year, fees and deadlines.
- [ ] Never report fabricated evaluation numbers or leak research participants' audio/PII.

## Suggested acceptance gates
- **M1 Collection pilot:** consented test users can submit and review recordings with recoverable storage.
- **M2 Valid dataset:** verified manifests, license/consent, annotation consistency and leakage-free splits.
- **M3 Retrieval baseline:** training script runs on a small sample and produces reproducible Recall@K.
- **M4 Proposed method:** ablations demonstrate whether phonetics improve unseen-speaker/term retrieval.
- **M5 Paper:** results tables correspond to archived experiment configs and outputs.
