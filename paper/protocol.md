# Research protocol (draft — must be frozen before final test)

## Task
Given an audio clip of a technical term spoken by a Vietnamese speaker, retrieve the *exact lexical term* from a candidate vocabulary compiled from relevant learning materials. This is not general semantic matching: a Vietnamese translation is not the same spoken term as its English equivalent.

## Research questions
- RQ1: Can frozen audio/text backbones with learned projections retrieve seen/unseen technical terms from Vietnamese-accented speech?
- RQ2: Does a phonetic representation and phonetic-aware loss improve hard-negative disambiguation?
- RQ3: How do unseen speakers, terms, noisy environments and new subject areas affect retrieval?
- RQ4 (downstream only): Does retrieval improve PhoWhisper term recognition without increasing false insertions?

## Dataset & splits
- Primary setting: isolated term recordings, multiple speakers and accents, precise verified labels.
- Secondary setting: target-term spans inside longer code-switched sentences; evaluate localization independently.
- Disjoint speaker test and disjoint term test (prefer intersection of both); hold out a subject/course where feasible.
- Collect **no-term negative** audio to measure false activation.
- Record prompt vs verified transcript independently. Include speaker pseudonym, device, codec, timestamps, course, glossary version, consent and human label provenance.
- Derive sample size using pilot variability; goals in README/TODO are estimates, not power calculations.

## Controls
1. Acoustic embedding vs text embedding with random/frozen projections (sanity control).
2. Trainable dual encoder with symmetric InfoNCE, multi-positive handling.
3. Text/phoneme encoder and phoneme-only matching.
4. Proposed fused contrastive method and hard negatives.
5. Strong published speech-text/keyword retrieval baselines if reproducible, matched to task.

## Metrics
Primary: Recall@1, Recall@5, MRR on speaker/term-disjoint test; report confidence intervals clustered by speaker. Secondary: hard-negative recall, no-term false-positive rate, retrieval latency and GPU RAM. Later integration: WER, CER, term recall, false insertion rate and real-time factor.

## Analysis
Lock splits and hyperparameters before held-out tests; ensure term text may appear in *retrieval index at inference* but no held-out term audio/labels leak into training. Report effect sizes, bootstrap confidence intervals, errors for Vietnamese-accented pronunciation, and negative results. Do not infer ASR improvement from retrieval improvements alone.

## Ethics & rights
Explicit opt-in consent before recording; independent of class grades; authorized institutional approval, withdrawal/delete workflows, minimization of survey attributes, access controls and limited retention. No participant data in Git; use controlled data access or derived aggregates. Verify textbooks' extraction/copyright permissions.
