# Data governance / security baseline

Voice is potentially identifying personal data. A research data collection site must not record until informed consent and any needed institutional approval are in place.

1. **Purpose & scope:** consent separately for research collection, internal training/evaluation, optional publication, and any cloud-based processing. Never use silence as consent.
2. **Voluntariness:** participation and withdrawal must not affect class grade; provide an alternative activity where applicable.
3. **Pseudonymization:** separate participant identity from recordings. Use internal random IDs, no name/email in filenames, manifests or paper screenshots.
4. **Drive:** access restricted to named research staff. Prefer Shared Drive or organizational workspace permissions; service account on backend only. No anyone-with-link sharing.
5. **Metadata:** PostgreSQL enforces RBAC, links prompt version to audio checksum, preserves annotation provenance and records access/export audits.
6. **Retention:** decide and publish an actual retention period before real collection; support withdrawal, deletion and backup/derived-dataset handling.
7. **Validation:** size, type, duration, decoded audio checks, malware/path safety, idempotent requests, rate limits and access logs. Treat all upload metadata as untrusted.
8. **Research integrity:** human-verbatim labels distinct from displayed prompts, no-test contamination; annotate spoken term spans, switches and uncertain speech.
9. **Public repo:** never commit audio, survey responses, IDs, storage URLs, account secrets, model outputs containing student speech or raw exports.
10. **Cloud providers:** document which personal data is sent to each provider. Obtain relevant approval for Drive and any LLM/embedding service.
11. **Copyright:** verify permission for textbook-derived prompts and glossary extraction, especially if redistributing them.

This is a planning checklist, not confirmation of legal/ethics compliance. Have your institution review the actual forms, retention policy and infrastructure before recruitment.
