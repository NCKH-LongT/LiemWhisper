# Literature Review Matrix (starting list; verify primary text before claims)

| Paper | Relevant idea | Reproduction/experiment question |
|---|---|---|
| Radford et al. (2023), *Robust Speech Recognition via Large-Scale Weak Supervision* — https://proceedings.mlr.press/v202/radford23a.html | Whisper backbone | What is PhoWhisper/Whisper performance on our speech? |
| Le et al. (2024), *PhoWhisper: Automatic Speech Recognition for Vietnamese* — https://arxiv.org/abs/2406.02555 | Vietnamese ASR checkpoint | Can frozen PhoWhisper encoder support spoken-term retrieval? |
| Ao et al. (2022), *SpeechT5: Unified-Modal Encoder-Decoder Pre-Training for Spoken Language Processing* — https://aclanthology.org/2022.acl-long.393/ | Shared speech/text representations | What is the nearest comparable cross-modal alignment baseline? |
| Seon et al. (2025), *RECAST: Retrieval-Augmented Contextual ASR via Decoder-State Keyword Spotting* — https://aclanthology.org/2025.findings-emnlp.203/ | Contextual word retrieval from ASR | Does our phonetic retrieval improve on contextual keyword retrieval? |
| Peng et al. (2024), *CB-Whisper: Contextual Biasing Whisper Using Open-Vocabulary Keyword-Spotting* — https://aclanthology.org/2024.lrec-main.262/ | TTS/keyword spotting for contextual ASR | How strong is a term-list / phonetic keyword baseline? |

Read each paper, verify authors/metadata/datasets/methods, and add actual measured baselines before using this for submission. Do not imply results for LiemWhisper exist.
