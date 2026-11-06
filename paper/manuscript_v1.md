# A Contrastive Audio-Text Retrieval Approach for Recovering Unseen English Software Testing Terminology in Vietnamese Code-Switched Speech

> **Author:** LiemWhisper Research Team  
> **Target Venue:** Interspeech / ACL / EMNLP Findings (Multimodal Speech & NLP Track)  
> **Status:** Stage 1 — Protocol Specification & Comprehensive First Draft (V1.0)  
> **Central Thesis:** *A contrastive audio-text retrieval approach for recovering unseen English software testing terminology from Vietnamese code-switched speech, with utterance-level acoustic representations providing complementary evidence beyond text-only prompt context.*

---

## 1. Abstract

Code-switched automatic speech recognition (ASR) frequently fails on specialized technical terminology due to vocabulary mismatch, phonetic borrowing, and severe class imbalance. In professional and educational domains, such as software quality assurance, missing an English technical term (e.g., *Equivalence Partitioning*, *Code Coverage*) severely degrades transcript utility. While large speech foundation models like Whisper transcribe native Vietnamese fluently, they exhibit high error rates on domain-specific English terms. Post-hoc generative neural rewriting risks hallucinating factual modifications and distorting accurate native context. 

In this work, we propose a decoupled contrastive retrieval framework that pairs a frozen ASR backbone with a lightweight audio-text dual-encoder projection head. Operating on whole-utterance acoustic representations and canonical English glossary definitions, our system retrieves candidate technical terms directly in a shared semantic-acoustic embedding space ($d=256$) without modifying the underlying ASR transcript. On a benchmark of 508 Vietnamese technical oral responses covering 6 held-out ISTQB software testing terms (756 occurrences), our proposed method achieves a Micro Recall@3 of 66.01% and Recall@5 of 95.24%, recovering terms where Whisper Small achieves only 25.26% exact-match recall. Furthermore, an information-theoretic audit reveals that while prompt topical context accounts for 49.87% Micro Recall@3, acoustic speech representations provide a substantial complementary gain of $+16.14$ percentage points. Our findings demonstrate that utterance-level acoustic representations offer a robust, non-destructive mechanism for domain-specific terminology grounding in code-switched speech.

---

## 2. Five Methodological Commitments (Locked Scientific Principles)

1. **Top-K Retrieval Focus over Universal ASR Replacement:**  
   Our proposed model (E0) does not claim universal superiority over Whisper Small at Top-1 (Micro R@1: 26.98% vs 25.26%; Macro R@1: 20.96% vs 23.43%). Its empirical strength lies in candidate retrieval at Top-3 (66.01%) and Top-5 (95.24%), recovering terminology dropped by ASR decoders into a verified candidate pool.
2. **Cautious Attribution of Acoustic Value-Add:**  
   The $+16.14\text{ pp}$ boost over the Text-Only Prompt Baseline is formally defined as an empirical *performance gain over the text-only baseline*, rather than an unconfounded causal effect, acknowledging the shared representation space and dual-encoder alignment.
3. **Transparent Reporting of Statistical Power:**  
   In the pilot diagnostic study ($N=30$ spans across 5 speakers), the Exact Cluster Permutation Test yields a two-sided $p = 0.1250$ (one-sided $p = 0.0625$, with a cluster bootstrap tail proportion of $P^*(\Delta^* \ge 0) = 0.06\%$). We state that E0 exhibits a consistent positive trend across 4 of 5 speakers, but has not achieved two-sided statistical significance at the $\alpha = 0.05$ level under strict cluster permutation due to the limited number of speaker clusters.
4. **Transparent Disclosure of Benchmark Structure (Prompt Confounding):**  
   The 508 test benchmark features an empirical Normalized Mutual Information of $74.36\%$ between Term and Prompt. Because the 6 unseen terms naturally co-cluster within 4 oral exam questions, this topical correlation is explicitly documented and analyzed in the main text as a domain characteristic, rather than relegated to an afterthought.
5. **Architectural Demarcation of Selective Correction (V2):**  
   Tri-state decision gates and proposed metrics (CGR, TCP, TCR, FCR-1, FCR-2) are formally classified as architectural directions for future work, preventing any premature empirical claims.

---

## 3. Paper Section Outline & Evidence Mapping

### Section 1: Introduction
- **Problem Statement:** Code-switching in professional domains (Vietnamese dialogue interspersed with ISTQB English technical terminology).
- **Failure Mode of Monolithic ASR:** Pretrained models (Whisper, PhoWhisper) suppress rare foreign tokens or map them onto phonetically similar native Vietnamese syllables (e.g., *"Bug Report"* $\to$ *"bớt report"*).
- **Dilemma:** Generative rewriters (Seq2Seq / T5) hallucinate or alter fluent native words, while frozen ASR loses technical terminology.
- **Proposed Paradigm:** A decoupled, non-destructive architecture. ASR transcribes the sentence; a multimodal dual-encoder retrieves candidate technical terms into an auxiliary evidence layer.
- **Core Research Question:** *Can utterance-level multimodal representations reliably retrieve zero-shot technical terminology, providing complementary evidence beyond text-only prompt context?*

### Section 2: Related Work
- Code-switched Speech Recognition (Vietnamese-English).
- Zero-Shot Spoken Term Retrieval (Audio-Text Contrastive Learning: CLAP, AudioCLIP).
- Multimodal Alignment in Low-Resource & Domain-Specific Speech.
- Post-ASR Error Correction vs. Non-Destructive Retrieval.

### Section 3: Methodology
- **Backbone Architecture:**
  - Acoustic Branch: Frozen Whisper-Tiny encoder ($d=384$), mean-pooled over time.
  - Text Branch: Frozen T5-Small encoder ($d=512$), mean-pooled over subwords.
  - Shared Embedding Space: Linear projection heads ($384 \to 256$ and $512 \to 256$) with $L_2$ unit-sphere normalization.
- **Contrastive Objective:**
  - Supervised Audio-to-Text Prototype Classification Loss with temperature $\tau = 0.07$:
    $$\mathcal{L} = -\frac{1}{B}\sum_{i=1}^B \log \frac{\exp(\langle z_{a_i}, z_{t_{y_i}}\rangle / \tau)}{\sum_{k=1}^K \exp(\langle z_{a_i}, z_{t_k}\rangle / \tau)}$$
- **Inference & Indexing:**
  - Candidate terminology library indexed using FAISS `IndexFlatIP` ($d=256$, Cosine Similarity).
  - Retrieval executed in $<1.0\text{ ms}$.

### Section 4: Experimental Setup
- **Dataset:** 2,096 Vietnamese oral exam recordings across 15 distinct questions (Q01–Q15) spoken by university software engineering students.
- **Zero-Shot Split Design:**
  - 18 Training Terms (Q02–Q09, Q11–Q13; 1,588 audios, 134 unique speakers).
  - 6 Strictly Unseen Evaluation Terms (Q01, Q10, Q14, Q15; 508 audios, 756 gold occurrences).
  - Unseen Terms: `Bug Report`, `Code Coverage`, `Equivalence Partitioning`, `Load Testing`, `Statement Coverage`, `Stress Testing`.
- **Evaluation Metrics:**
  - Macro Recall@K (Per-recording average).
  - Micro Recall@K (Per-occurrence weighted average across 756 instances).
  - Setting A (Full 24-term open vocabulary pool in FAISS).
  - Setting B (Isolated 6-term unseen candidate pool in FAISS).

### Section 5: Main Results (508-Audio Benchmark)

| Evaluation Setting | System | Macro R@1 | Macro R@3 | Macro R@5 | Micro R@1 | Micro R@3 | Micro R@5 |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **Baseline ASR** | Whisper-Small (Frozen ASR) | 23.43% | — | — | 25.26% | — | — |
| **Setting B** *(6 Unseen Terms)* | Text-Only Prompt Baseline | 12.11% | 50.00% | 87.50% | 16.27% | 49.87% | 83.33% |
| | **E0 Multimodal Representation** | **20.96%** | **57.78%** | **95.47%** | **26.98%** | **66.01%** | **95.24%** |
| | *Net Acoustic Gain ($\Delta$)* | *+8.85 pp* | *+7.78 pp* | *+7.97 pp* | *+10.71 pp* | *+16.14 pp* | *+11.91 pp* |
| **Setting A** *(All 24 Terms)* | **E0 Multimodal Representation** | 2.95% | 12.50% | 23.43% | 3.97% | 15.48% | 28.17% |

*Key Findings:*
1. Whisper-Small misses $\sim 75\%$ of technical term occurrences in verbatim transcription.
2. E0 matches Whisper-Small at Top-1 (26.98% vs 25.26%), but achieves 66.01% at Top-3 and 95.24% at Top-5.
3. Acoustic speech representations provide an empirical gain of $+16.14\text{ pp}$ over text-only prompt context.

### Section 6: Diagnostic & Ablation Studies (Oracle Alignment Pilot)

Comparison on $N=30$ test spans across 5 speakers and 6 unseen terms:

| Model Architecture | Input Processing Condition | Setting B R@1 | Setting B R@3 | Setting B R@5 | Mean Margin | Median Margin | Skewness |
| :--- | :--- | :---: | :---: | :---: | :---: | :---: | :---: |
| **E0** | Global Utterance Representation | 23.33% | **80.00%** | **100.00%** | -0.1040 | -0.0393 | -1.11 |
| **E1b** | Contextualized Span Pooling | 23.33% | 60.00% | 86.67% | -0.5296 | -0.3187 | -0.22 |
| **E1b-Crop** | Crop-Only Local Acoustic | — | 50.00% | 83.33% | -1.0220 | -1.4531 | +0.93 |

*Statistical Audit (Speaker Cluster as Primary Unit):*
- Exact Cluster Permutation Test ($2^5 = 32$ configurations): $p = 0.0625$ (one-sided), $p = 0.1250$ (two-sided).
- Cluster Bootstrap (10,000 draws): Mean $\Delta = -19.98\%$, 95% Percentile CI: $[-30.00\%, -10.00\%]$, Tail Proportion $P^*(\Delta^* \ge 0) = 0.06\%$.
- Secondary Span-Level Tests: McNemar's exact $p = 0.1094$, Paired Permutation $p = 0.1093$.
- Analysis of Margin Collapse in E1b-Crop: Distribution is positively skewed ($+0.93$), with 43.3% of spans collapsing into $[-2.0, -1.5)$, while 16.7% maintain positive margins up to $+0.75$, pulling the mean to $-1.0220$ while the median remains $-1.4531$.

### Section 7: Discussion
- **Mechanism of Utterance-Level Contextualization:** Why whole-utterance encoding resists acoustic boundary distortion.
- **Acoustic Grounding vs. Prompt Memorization:** Detailed analysis of Prompt Q10 (where E0 achieves 0% R@1, disproving simple prompt memorization) vs Q14/Q15.
- **Complementary Roles of Speech and Language:** Text sets the prior; acoustics disambiguate co-occurring technical terms.

### Section 8: Limitations
1. **Benchmark Prompt Co-clustering:** High NMI ($74.36\%$) reflects natural exam prompt structure but couples terms with specific questions.
2. **Limited Speaker Clusters in Pilot:** $N=5$ speakers limits the resolution of exact cluster permutation tests.
3. **Decoupled vs. End-to-End ASR Integration:** The model provides a candidate retrieval card layer rather than in-place text rewriting.

### Section 9: Conclusion & Future Directions
- Summary of core contributions.
- Future work: Local CTC Acoustic Verification and calibrated tri-state selective correction (V2).

---

## 4. Empirical Provenance & Artifact Checklist

| Checkpoint / Artifact | File Path | SHA-256 Hash |
| :--- | :--- | :--- |
| **E0 Model Weights** | `Data/models/contrastive_open_vocab/best_contrastive_model.pt` | `5b38a183d539b700c2be95a28562d2924372551cf9fc078e35a11c8cb5f8d956` |
| **E1b Model Weights** | `Data/models/e1b_span_model.pt` | `51231848fec1008479e0bf01f357fbb7009477a33114d4e3cb4dd25714777598` |
| **508 Benchmark Predictions**| `Data/benchmark_results/unseen_predictions_508.csv` | `46334f53cabe134d13ffb1d9df659549f39007f354f3be1897b2be29e4eb57b6` |
| **30-Span Evaluation File** | `Data/models/test_30_detailed_eval.csv` | `42d8b41d70343918a0e883833b9ee3f0449d0caaeaa605655a6d368d4f4aa00d` |
| **Reproducibility Manifest** | `Data/reproducibility_package_manifest.json` | *Prepared with full library versions & deterministic flags* |
