# Research workspace — audio/text/phoneme alignment

Research question: Can phonetic-aware contrastive training align audio of Vietnamese-accented English technical terms and corresponding lexical text in a shared vector space, improving retrieval of unseen terms/speakers?

## Proposed modules in src/liemwhisper
`data/`: manifests, annotation validation and leakage-resistant splits.
`encoders/`: frozen PhoWhisper encoder, multilingual text encoder, G2P/phoneme encoder.
`alignment/`: pooling/projections, contrastive losses, multi-positive handling.
`retrieval/`: FAISS indexing, cosine search, hard-negative mining.
`evaluation/`: Recall@1/5, MRR, uncertainty, error analysis and efficiency.
`asr/`: optional PhoWhisper downstream integration.

## Minimal experiment
1. Build verified pairs of short spoken-term audio and written term; keep speaker and term metadata.
2. Train speech and text projection heads with a symmetric contrastive objective.
3. Test held-out speakers; separately test terms never used in training.
4. Add phoneme supervision/variants and confusable negatives.
5. Compare retrieval quality and false positives, not only loss curves.
6. Only then test in-sentence localization and ASR correction.

Train/dev/test manifests and any speaker-identifying artifacts stay **outside the repository**. Log dataset version, anonymized sample counts, checkpoint hashes, random seed, compute, hyperparameters and all results. Do not claim research accuracy until evaluated.
