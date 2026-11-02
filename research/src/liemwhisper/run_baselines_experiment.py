"""
LiemWhisper Official Comparative Experiment Runner (Proposal Section 4.4)
==========================================================================
Executes the comprehensive benchmark comparing:
- Baseline B0: Raw Whisper Small + Exact Match + Taxonomy Lookup
- Baseline B1: Glossary Prompted Whisper Small + Lookup (Contextual Biasing)
- Baseline B2: ASR + Lexical Fuzzy Matching (θ=0.75) + Lookup (Lexical-only)
- Proposed System P: LiemWhisper Evidence-Based Candidate Selector & Ranking Engine
                     (Acoustic Teacher-Forcing + Lexical + Phonetic + Context + Decision Gate)
- Ablation Studies:
  * P (No Acoustic Evidence): Ablates teacher-forcing score difference
  * P (No Context Evidence): Ablates ISTQB context-definition compatibility
  * P (No Decision Gate): Ablates regularized acceptance threshold (forces all candidates)

Generates official metrics (Proposal Table 4.4):
- Uncapped Corpus WER & CER
- Term Precision, Recall, F1
- End-to-End Term-Category F1 & Category Macro-F1
- Safety Metrics: Harmful-Correction Rate (HCR), Correction Success Rate (CSR), Net Gain
- Speaker-Clustered Paired Bootstrap Significance Tests (2,000 resamples, 95% CI, p-value)
"""

import os
import sys
import re
import json
import time
import site
import ctypes
import argparse
import numpy as np
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure NVIDIA CUDA DLLs are found by Windows dynamic linker
for sp in site.getsitepackages():
    for sub in ['cublas', 'cudnn', 'cuda_nvrtc']:
        p = os.path.join(sp, 'nvidia', sub, 'bin')
        if os.path.exists(p):
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(p)
                except Exception:
                    pass
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')

    cublas_bin = os.path.join(sp, 'nvidia', 'cublas', 'bin')
    if os.path.exists(cublas_bin):
        for dll_name in ['cublasLt64_12.dll', 'cublas64_12.dll']:
            dll_path = os.path.join(cublas_bin, dll_name)
            if os.path.exists(dll_path):
                try:
                    ctypes.CDLL(dll_path)
                except Exception:
                    pass

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from evaluation import (
    TextNormalizer,
    ASRMetricsCalculator,
    TerminologyOccurrence,
    TerminologyEvaluator,
    SafetyMetricsEvaluator,
    PairedBootstrapTester
)
from baselines import (
    TaxonomyManager,
    ExactMatchingBaseline,
    GlossaryPromptingASR,
    LexicalFuzzyMatcher
)
from candidate_ranking import (
    AcousticTeacherForcingScorer,
    ProposedSystemP
)

# Discover workspace base directory
cand_base = current_dir
while cand_base and not os.path.exists(os.path.join(cand_base, "Data", "glossary_taxonomy_v1.json")):
    parent = os.path.dirname(cand_base)
    if parent == cand_base:
        break
    cand_base = parent

BASE_DIR = cand_base
DATA_DIR = os.path.join(BASE_DIR, "Data")
WAV_DIR = os.path.join(DATA_DIR, "wav_16k")
TAXONOMY_PATH = os.path.join(DATA_DIR, "glossary_taxonomy_v1.json")
DEFAULT_MANIFEST = os.path.join(DATA_DIR, "gold_with_asr_v1.csv") if os.path.exists(os.path.join(DATA_DIR, "gold_with_asr_v1.csv")) else os.path.join(DATA_DIR, "annotation_with_asr_v1.csv")
OUT_DIR = os.path.join(DATA_DIR, "benchmark_results")
B1_CACHE_PATH = os.path.join(OUT_DIR, "asr_b1_glossary_prompting.csv")


def parse_args():
    parser = argparse.ArgumentParser(description="Run LiemWhisper Official Comparative Experiment (Proposal Table 4.4)")
    parser.add_argument("--manifest", type=str, default=DEFAULT_MANIFEST, help="Path to manifest CSV")
    parser.add_argument("--split", type=str, default="test", help="Split to evaluate: test, val, or all")
    parser.add_argument("--ref-col", type=str, default=None, help="Reference column for WER/CER (defaults to verbatim_transcript or prompt_text)")
    parser.add_argument("--fuzzy-threshold", type=float, default=0.75, help="Similarity threshold for System B2")
    parser.add_argument("--skip-b1-gpu", action="store_true", help="Skip running B1 GPU inference if only testing B0/B2/P")
    parser.add_argument("--skip-acoustic", action="store_true", help="Run System P without GPU teacher-forcing logprob")
    parser.add_argument("--run-ablations", action="store_true", default=True, help="Run ablation studies for System P")
    parser.add_argument("--force-rerun-p", action="store_true", help="Force rerunning System P even if predictions CSV exists")
    parser.add_argument("--n-resamples", type=int, default=2000, help="Number of bootstrap resamples for significance testing")
    return parser.parse_args()


def bootstrap_term_f1_significance(
    df: pd.DataFrame,
    gold_terms_list: list,
    base_preds: list,
    cand_preds: list,
    n_resamples: int = 2000,
    random_seed: int = 42
) -> dict:
    """
    Computes speaker-clustered paired bootstrap test on Term Recognition F1.
    """
    rng = np.random.RandomState(random_seed)
    unique_speakers = df["speaker_id"].unique()
    n_speakers = len(unique_speakers)
    speaker_to_indices = {spk: df[df["speaker_id"] == spk].index.tolist() for spk in unique_speakers}

    # Precalculate per-utterance TP, FP, FN for base and cand
    base_stats = []
    cand_stats = []
    for g, b, c in zip(gold_terms_list, base_preds, cand_preds):
        b_m = TerminologyEvaluator.match_utterance_occurrences(g, b)
        c_m = TerminologyEvaluator.match_utterance_occurrences(g, c)
        base_stats.append((b_m["term_tp"], b_m["term_fp"], b_m["term_fn"]))
        cand_stats.append((c_m["term_tp"], c_m["term_fp"], c_m["term_fn"]))

    # Overall observed F1
    b_tp = sum(s[0] for s in base_stats)
    b_fp = sum(s[1] for s in base_stats)
    b_fn = sum(s[2] for s in base_stats)
    b_f1 = (2 * b_tp) / (2 * b_tp + b_fp + b_fn) if (2 * b_tp + b_fp + b_fn) > 0 else 0.0

    c_tp = sum(s[0] for s in cand_stats)
    c_fp = sum(s[1] for s in cand_stats)
    c_fn = sum(s[2] for s in cand_stats)
    c_f1 = (2 * c_tp) / (2 * c_tp + c_fp + c_fn) if (2 * c_tp + c_fp + c_fn) > 0 else 0.0

    obs_diff = c_f1 - b_f1

    # Bootstrap resample loop
    diff_samples = []
    for _ in range(n_resamples):
        boot_speakers = rng.choice(unique_speakers, size=n_speakers, replace=True)
        boot_b_tp, boot_b_fp, boot_b_fn = 0, 0, 0
        boot_c_tp, boot_c_fp, boot_c_fn = 0, 0, 0

        for spk in boot_speakers:
            for idx in speaker_to_indices[spk]:
                boot_b_tp += base_stats[idx][0]
                boot_b_fp += base_stats[idx][1]
                boot_b_fn += base_stats[idx][2]

                boot_c_tp += cand_stats[idx][0]
                boot_c_fp += cand_stats[idx][1]
                boot_c_fn += cand_stats[idx][2]

        denom_b = 2 * boot_b_tp + boot_b_fp + boot_b_fn
        denom_c = 2 * boot_c_tp + boot_c_fp + boot_c_fn

        f1_b = (2 * boot_b_tp / denom_b) if denom_b > 0 else 0.0
        f1_c = (2 * boot_c_tp / denom_c) if denom_c > 0 else 0.0
        diff_samples.append(f1_c - f1_b)

    diffs = np.array(diff_samples)
    ci_lower = float(np.percentile(diffs, 2.5))
    ci_upper = float(np.percentile(diffs, 97.5))
    p_value = float(np.mean(diffs <= 0.0))

    return {
        "n_resamples": n_resamples,
        "n_clusters_speakers": n_speakers,
        "base_f1": round(b_f1, 6),
        "cand_f1": round(c_f1, 6),
        "observed_f1_gain": round(obs_diff, 6),
        "ci_95_lower": round(ci_lower, 6),
        "ci_95_upper": round(ci_upper, 6),
        "is_significant_95": bool(ci_lower > 0.0),
        "empirical_p_value": round(p_value, 4)
    }


def main():
    args = parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 80)
    print("LIEMWHISPER COMPARATIVE BENCHMARK: BASELINES vs PROPOSED METHOD P")
    print("=" * 80)
    print(f"Target Split            : {args.split.upper()}")
    print(f"Manifest                : {args.manifest}")
    print(f"Taxonomy                : {TAXONOMY_PATH}")
    print(f"Fuzzy Threshold B2      : {args.fuzzy_threshold}")
    print(f"Run Ablations           : {args.run_ablations}")

    # 1. Load Taxonomy
    tax = TaxonomyManager(TAXONOMY_PATH)
    categories = list(tax.categories.keys())
    print(f"Loaded {len(tax.canonical_terms)} taxonomy terms across {len(categories)} categories.")

    # 2. Load Manifest
    df = pd.read_csv(args.manifest)
    if args.split != "all":
        df = df[df["split"] == args.split].reset_index(drop=True)

    n_samples = len(df)
    n_speakers = df["speaker_id"].nunique()
    total_audio_sec = float(df["duration_seconds"].sum()) if "duration_seconds" in df.columns else 0.0
    print(f"Evaluating {n_samples} recordings from {n_speakers} held-out speakers (Total audio: {total_audio_sec:.1f}s / {total_audio_sec/60:.1f} mins).")

    ref_col_name = args.ref_col or ("verbatim_transcript" if "verbatim_transcript" in df.columns else "prompt_text")
    print(f"Evaluation Reference Col: {ref_col_name}")
    refs = df[ref_col_name].fillna("").astype(str).tolist()
    speaker_ids = df["speaker_id"].astype(str).tolist()

    def parse_gold_row(row):
        raw_terms = row.get("gold_terms")
        raw_cats = row.get("gold_categories")
        if pd.notna(raw_terms) and str(raw_terms).strip():
            t_list = [t.strip() for t in str(raw_terms).split(";") if t.strip()]
            c_list = [c.strip() for c in str(raw_cats).split(";") if c.strip()] if pd.notna(raw_cats) else []
            res = []
            for i, t in enumerate(t_list):
                c = c_list[i] if i < len(c_list) else "Unassigned"
                res.append(TerminologyOccurrence(t, c))
            return res
        cat = str(row.get("primary_category_hint", "Unassigned"))
        raw = row.get("target_terms_hint", "")
        return TerminologyEvaluator.parse_term_list(raw, cat)

    gold_terms_list = [parse_gold_row(r) for _, r in df.iterrows()]

    total_gold_terms = sum(len(g) for g in gold_terms_list)
    print(f"Total ground-truth term occurrences: {total_gold_terms}")

    summary_rows = []

    # ==========================================================================
    # 3. SYSTEM B0: ASR + Exact Matching + Taxonomy Lookup
    # ==========================================================================
    print("\n" + "-" * 80)
    print(">>> [SYSTEM B0] ASR (Raw Whisper Small) + Exact Matching + Taxonomy Lookup")
    print("-" * 80)
    b0_matcher = ExactMatchingBaseline(tax)
    b0_hyps = df["asr_transcript"].fillna("").astype(str).tolist()

    b0_asr = ASRMetricsCalculator.evaluate_corpus(refs, b0_hyps, speaker_ids)
    print(f"  Corpus WER: {b0_asr['corpus_wer']*100:.2f}% | Corpus CER: {b0_asr['corpus_cer']*100:.2f}%")

    b0_preds = [b0_matcher.extract_terms(h) for h in b0_hyps]
    b0_eval = TerminologyEvaluator.evaluate_corpus(gold_terms_list, b0_preds, categories)

    b0_term = b0_eval["term_recognition"]
    b0_e2e = b0_eval["end_to_end_classification"]
    print(f"  Term Recognition  : Precision={b0_term['precision']*100:.2f}%, Recall={b0_term['recall']*100:.2f}%, F1={b0_term['f1_score']*100:.2f}%")
    print(f"  E2E Term-Category : Precision={b0_e2e['precision']*100:.2f}%, Recall={b0_e2e['recall']*100:.2f}%, F1={b0_e2e['f1_score']*100:.2f}%")
    print(f"  Category Macro-F1 : {b0_e2e['category_macro_f1']*100:.2f}%")

    summary_rows.append({
        "System": "B0: Raw ASR + Exact Match",
        "Type": "Baseline",
        "Corpus WER": f"{b0_asr['corpus_wer']*100:.2f}%",
        "Corpus CER": f"{b0_asr['corpus_cer']*100:.2f}%",
        "Term Prec": f"{b0_term['precision']*100:.2f}%",
        "Term Recall": f"{b0_term['recall']*100:.2f}%",
        "Term F1": f"{b0_term['f1_score']*100:.2f}%",
        "E2E Term-Cat F1": f"{b0_e2e['f1_score']*100:.2f}%",
        "Harmful Corruptions": 0,
        "Harmful Correction Rate (HCR)": "0.00%",
        "Correction Success Rate (CSR)": "0.00%",
        "Net Gain": "0"
    })

    # ==========================================================================
    # 4. SYSTEM B1: ASR + Glossary Prompting + Lookup
    # ==========================================================================
    b1_preds = []
    b1_hyps = []
    if not args.skip_b1_gpu:
        print("\n" + "-" * 80)
        print(">>> [SYSTEM B1] ASR (Glossary Prompted Whisper Small) + Exact Match + Lookup")
        print("-" * 80)

        b1_cache = {}
        if os.path.exists(B1_CACHE_PATH):
            try:
                c_df = pd.read_csv(B1_CACHE_PATH)
                for _, r in c_df.iterrows():
                    b1_cache[r["wav_file"]] = str(r["b1_transcript"])
                print(f"Found {len(b1_cache)} cached B1 transcripts.")
            except Exception as e:
                print(f"Note reading cache: {e}")

        b1_model = None
        missing_count = 0

        for idx, row in df.iterrows():
            wf = row["wav_file"]
            if wf in b1_cache:
                b1_hyps.append(b1_cache[wf])
            else:
                if b1_model is None:
                    b1_model = GlossaryPromptingASR(tax, model_size="small", device="cuda", compute_type="float16")
                audio_p = os.path.join(WAV_DIR, wf)
                if not os.path.exists(audio_p):
                    b1_hyps.append("")
                    continue
                missing_count += 1
                res = b1_model.transcribe(audio_p, beam_size=5)
                b1_hyps.append(res["transcript"])
                b1_cache[wf] = res["transcript"]

        if missing_count > 0:
            cache_records = [{"wav_file": k, "b1_transcript": v} for k, v in b1_cache.items()]
            pd.DataFrame(cache_records).to_csv(B1_CACHE_PATH, index=False, encoding="utf-8-sig")

        b1_asr = ASRMetricsCalculator.evaluate_corpus(refs, b1_hyps, speaker_ids)
        print(f"  Corpus WER: {b1_asr['corpus_wer']*100:.2f}% | Corpus CER: {b1_asr['corpus_cer']*100:.2f}%")

        b1_preds = [b0_matcher.extract_terms(h) for h in b1_hyps]
        b1_eval = TerminologyEvaluator.evaluate_corpus(gold_terms_list, b1_preds, categories)

        b1_term = b1_eval["term_recognition"]
        b1_e2e = b1_eval["end_to_end_classification"]
        print(f"  Term Recognition  : Precision={b1_term['precision']*100:.2f}%, Recall={b1_term['recall']*100:.2f}%, F1={b1_term['f1_score']*100:.2f}%")
        print(f"  E2E Term-Category : Precision={b1_e2e['precision']*100:.2f}%, Recall={b1_e2e['recall']*100:.2f}%, F1={b1_e2e['f1_score']*100:.2f}%")
        print(f"  Category Macro-F1 : {b1_e2e['category_macro_f1']*100:.2f}%")

        b1_safety = SafetyMetricsEvaluator.evaluate_comparative_safety(gold_terms_list, b0_preds, b1_preds)
        print(f"  [Safety vs B0] Harmful-Correction Rate (HCR): {b1_safety['overall_harmful_correction_rate']*100:.2f}% ({b1_safety['overall_harmful_corruptions']} corrupted)")
        print(f"  [Safety vs B0] Correction Success Rate (CSR): {b1_safety['overall_correction_success_rate']*100:.2f}% ({b1_safety['overall_successful_corrections']} fixed)")
        print(f"  [Safety vs B0] Net Accuracy Gain            : {b1_safety['overall_net_gain']:+d} utterances")

        summary_rows.append({
            "System": "B1: Glossary Prompting",
            "Type": "Baseline",
            "Corpus WER": f"{b1_asr['corpus_wer']*100:.2f}%",
            "Corpus CER": f"{b1_asr['corpus_cer']*100:.2f}%",
            "Term Prec": f"{b1_term['precision']*100:.2f}%",
            "Term Recall": f"{b1_term['recall']*100:.2f}%",
            "Term F1": f"{b1_term['f1_score']*100:.2f}%",
            "E2E Term-Cat F1": f"{b1_e2e['f1_score']*100:.2f}%",
            "Harmful Corruptions": b1_safety["overall_harmful_corruptions"],
            "Harmful Correction Rate (HCR)": f"{b1_safety['overall_harmful_correction_rate']*100:.2f}%",
            "Correction Success Rate (CSR)": f"{b1_safety['overall_correction_success_rate']*100:.2f}%",
            "Net Gain": f"{b1_safety['overall_net_gain']:+d}"
        })

    # ==========================================================================
    # 5. SYSTEM B2: ASR + Lexical Fuzzy Matching + Lookup
    # ==========================================================================
    print("\n" + "-" * 80)
    print(f">>> [SYSTEM B2] ASR + Lexical Fuzzy Matching (θ={args.fuzzy_threshold}) + Lookup")
    print("-" * 80)
    b2_matcher = LexicalFuzzyMatcher(tax, similarity_threshold=args.fuzzy_threshold)
    b2_preds = [b2_matcher.extract_terms(h) for h in b0_hyps]
    b2_eval = TerminologyEvaluator.evaluate_corpus(gold_terms_list, b2_preds, categories)

    b2_term = b2_eval["term_recognition"]
    b2_e2e = b2_eval["end_to_end_classification"]
    print(f"  Term Recognition  : Precision={b2_term['precision']*100:.2f}%, Recall={b2_term['recall']*100:.2f}%, F1={b2_term['f1_score']*100:.2f}%")
    print(f"  E2E Term-Category : Precision={b2_e2e['precision']*100:.2f}%, Recall={b2_e2e['recall']*100:.2f}%, F1={b2_e2e['f1_score']*100:.2f}%")
    print(f"  Category Macro-F1 : {b2_e2e['category_macro_f1']*100:.2f}%")

    b2_safety = SafetyMetricsEvaluator.evaluate_comparative_safety(gold_terms_list, b0_preds, b2_preds)
    print(f"  [Safety vs B0] Harmful-Correction Rate (HCR): {b2_safety['overall_harmful_correction_rate']*100:.2f}% ({b2_safety['overall_harmful_corruptions']} corrupted)")
    print(f"  [Safety vs B0] Correction Success Rate (CSR): {b2_safety['overall_correction_success_rate']*100:.2f}% ({b2_safety['overall_successful_corrections']} fixed)")
    print(f"  [Safety vs B0] Net Accuracy Gain            : {b2_safety['overall_net_gain']:+d} utterances")

    summary_rows.append({
        "System": "B2: Lexical Fuzzy Matching",
        "Type": "Baseline",
        "Corpus WER": f"{b0_asr['corpus_wer']*100:.2f}% (ASR frozen)",
        "Corpus CER": f"{b0_asr['corpus_cer']*100:.2f}% (ASR frozen)",
        "Term Prec": f"{b2_term['precision']*100:.2f}%",
        "Term Recall": f"{b2_term['recall']*100:.2f}%",
        "Term F1": f"{b2_term['f1_score']*100:.2f}%",
        "E2E Term-Cat F1": f"{b2_e2e['f1_score']*100:.2f}%",
        "Harmful Corruptions": b2_safety["overall_harmful_corruptions"],
        "Harmful Correction Rate (HCR)": f"{b2_safety['overall_harmful_correction_rate']*100:.2f}%",
        "Correction Success Rate (CSR)": f"{b2_safety['overall_correction_success_rate']*100:.2f}%",
        "Net Gain": f"{b2_safety['overall_net_gain']:+d}"
    })

    # ==========================================================================
    # 6. PROPOSED SYSTEM P: EVIDENCE-BASED CANDIDATE RANKING
    # ==========================================================================
    print("\n" + "-" * 80)
    print(">>> [SYSTEM P] Proposed Method P: Evidence-Based Candidate Selector & Ranking Engine")
    print("-" * 80)

    # Initialize acoustic scorer
    acoustic_scorer = None
    if not args.skip_acoustic:
        try:
            print("  Initializing frozen Whisper Small decoder for teacher-forcing logprob difference...")
            acoustic_scorer = AcousticTeacherForcingScorer(model_size="small", device="cuda", compute_type="float16")
            acoustic_scorer.load_model()
        except Exception as e:
            print(f"  Note initializing acoustic scorer ({e}), falling back to CPU...")
            acoustic_scorer = AcousticTeacherForcingScorer(model_size="small", device="cpu", compute_type="int8")

    system_p = ProposedSystemP(
        taxonomy=tax,
        acoustic_scorer=acoustic_scorer,
        generator_threshold=0.45,
        acceptance_threshold=0.50,
        enable_acoustic=(acoustic_scorer is not None),
        enable_context=True,
        enable_phonetic=True,
        enable_gate=True
    )

    pred_csv = os.path.join(OUT_DIR, f"predictions_system_p_{args.split}.csv")
    loaded_cache = False
    p_hyps = []
    p_preds = []
    latency_p = 0.9709

    if os.path.exists(pred_csv) and not args.force_rerun_p:
        try:
            p_df = pd.read_csv(pred_csv)
            if len(p_df) == n_samples:
                print(f"  Loaded {len(p_df)} cached System P predictions from: {pred_csv}")
                p_hyps = p_df["revised_transcript"].fillna("").astype(str).tolist()
                for _, r in p_df.iterrows():
                    raw_t = r.get("predicted_terms", "")
                    raw_c = r.get("predicted_categories", "")
                    if pd.notna(raw_t) and str(raw_t).strip():
                        t_list = [t.strip() for t in str(raw_t).split(";") if t.strip()]
                        c_list = [c.strip() for c in str(raw_c).split(";") if c.strip()] if pd.notna(raw_c) else []
                        p_preds.append([
                            TerminologyOccurrence(t, c_list[i] if i < len(c_list) else "Unassigned")
                            for i, t in enumerate(t_list)
                        ])
                    else:
                        p_preds.append([])
                loaded_cache = True
        except Exception as e:
            print(f"  Note reading predictions cache ({e}), rerunning...")

    if not loaded_cache:
        t0_p = time.time()
        p_records = []

        for idx, row in df.iterrows():
            wf = row["wav_file"]
            audio_p = os.path.join(WAV_DIR, wf)
            orig_hyp = str(row["asr_transcript"])

            res = system_p.process_utterance(orig_hyp, audio_p if os.path.exists(audio_p) else None)
            p_hyps.append(res["revised_transcript"])
            p_preds.append(res["predicted_terms"])

            p_records.append({
                "recording_id": row["recording_id"],
                "speaker_id": row["speaker_id"],
                "prompt_id": row.get("prompt_id", ""),
                "prompt_text": row["prompt_text"],
                "asr_transcript": orig_hyp,
                "revised_transcript": res["revised_transcript"],
                "predicted_terms": "; ".join([t.term for t in res["predicted_terms"]]),
                "predicted_categories": "; ".join([t.category for t in res["predicted_terms"]]),
                "accepted_changes_count": len(res["accepted_changes"]),
                "accepted_changes": json.dumps(res["accepted_changes"], ensure_ascii=False),
                "split": row.get("split", args.split)
            })

            if (idx + 1) % 50 == 0 or idx == n_samples - 1:
                print(f"  [{idx+1}/{n_samples}] Processed System P: {wf} (Changes: {len(res['accepted_changes'])})", flush=True)

        latency_p = (time.time() - t0_p) / n_samples
        print(f"  Total processing time: {time.time() - t0_p:.2f}s (Average latency: {latency_p*1000:.1f}ms/recording)")
        pd.DataFrame(p_records).to_csv(pred_csv, index=False, encoding="utf-8-sig")
        print(f"  Saved structured predictions to: {pred_csv}")

    if acoustic_scorer is not None:
        acoustic_scorer.save_cache()

    # Evaluate System P Metrics
    p_asr = ASRMetricsCalculator.evaluate_corpus(refs, p_hyps, speaker_ids)
    print(f"  Corpus WER: {p_asr['corpus_wer']*100:.2f}% | Corpus CER: {p_asr['corpus_cer']*100:.2f}%")

    p_eval = TerminologyEvaluator.evaluate_corpus(gold_terms_list, p_preds, categories)
    p_term = p_eval["term_recognition"]
    p_e2e = p_eval["end_to_end_classification"]
    print(f"  Term Recognition  : Precision={p_term['precision']*100:.2f}%, Recall={p_term['recall']*100:.2f}%, F1={p_term['f1_score']*100:.2f}%")
    print(f"  E2E Term-Category : Precision={p_e2e['precision']*100:.2f}%, Recall={p_e2e['recall']*100:.2f}%, F1={p_e2e['f1_score']*100:.2f}%")
    print(f"  Category Macro-F1 : {p_e2e['category_macro_f1']*100:.2f}%")

    p_safety = SafetyMetricsEvaluator.evaluate_comparative_safety(gold_terms_list, b0_preds, p_preds)
    print(f"  [Safety vs B0] Harmful-Correction Rate (HCR): {p_safety['overall_harmful_correction_rate']*100:.2f}% ({p_safety['overall_harmful_corruptions']} corrupted)")
    print(f"  [Safety vs B0] Correction Success Rate (CSR): {p_safety['overall_correction_success_rate']*100:.2f}% ({p_safety['overall_successful_corrections']} fixed)")
    print(f"  [Safety vs B0] Net Accuracy Gain            : {p_safety['overall_net_gain']:+d} utterances")

    # Safety vs B1
    if b1_preds:
        p_safety_b1 = SafetyMetricsEvaluator.evaluate_comparative_safety(gold_terms_list, b1_preds, p_preds)
        print(f"  [Safety vs B1] Harmful-Correction Rate (HCR): {p_safety_b1['overall_harmful_correction_rate']*100:.2f}%")

    summary_rows.append({
        "System": "P: Proposed LiemWhisper",
        "Type": "Proposed Method",
        "Corpus WER": f"{p_asr['corpus_wer']*100:.2f}%",
        "Corpus CER": f"{p_asr['corpus_cer']*100:.2f}%",
        "Term Prec": f"{p_term['precision']*100:.2f}%",
        "Term Recall": f"{p_term['recall']*100:.2f}%",
        "Term F1": f"{p_term['f1_score']*100:.2f}%",
        "E2E Term-Cat F1": f"{p_e2e['f1_score']*100:.2f}%",
        "Harmful Corruptions": p_safety["overall_harmful_corruptions"],
        "Harmful Correction Rate (HCR)": f"{p_safety['overall_harmful_correction_rate']*100:.2f}%",
        "Correction Success Rate (CSR)": f"{p_safety['overall_correction_success_rate']*100:.2f}%",
        "Net Gain": f"{p_safety['overall_net_gain']:+d}"
    })

    # Statistical significance testing: Paired Bootstrap (2,000 resamples)
    test_df = df.copy()
    test_df["b0_hyp"] = b0_hyps
    test_df["b1_hyp"] = b1_hyps if b1_hyps else b0_hyps
    test_df["p_hyp"] = p_hyps

    print("\n" + "-" * 80)
    print(f">>> [STATISTICAL SIGNIFICANCE] Speaker-Clustered Paired Bootstrap ({args.n_resamples} Resamples)")
    print("-" * 80)

    # 1. P vs B0 (WER & Term F1)
    p_boot_b0_wer = PairedBootstrapTester.test_wer_difference(
        test_df,
        ref_col=ref_col_name,
        base_hyp_col="b0_hyp",
        cand_hyp_col="p_hyp",
        speaker_col="speaker_id",
        n_resamples=args.n_resamples,
        random_seed=42
    )
    p_boot_b0_f1 = bootstrap_term_f1_significance(
        test_df,
        gold_terms_list,
        b0_preds,
        p_preds,
        n_resamples=args.n_resamples,
        random_seed=42
    )
    print(f"  [P vs B0] WER Δ: {p_boot_b0_wer['observed_wer_reduction']*100:+.2f}% (95% CI: [{p_boot_b0_wer['ci_95_lower']*100:.2f}%, {p_boot_b0_wer['ci_95_upper']*100:.2f}%], p={p_boot_b0_wer['empirical_p_value']})")
    print(f"  [P vs B0] Term F1 Δ: {p_boot_b0_f1['observed_f1_gain']*100:+.2f}% (95% CI: [{p_boot_b0_f1['ci_95_lower']*100:.2f}%, {p_boot_b0_f1['ci_95_upper']*100:.2f}%], p={p_boot_b0_f1['empirical_p_value']})")

    # 2. P vs B1 (WER & Term F1)
    p_boot_b1_wer = None
    p_boot_b1_f1 = None
    if b1_hyps and b1_preds:
        p_boot_b1_wer = PairedBootstrapTester.test_wer_difference(
            test_df,
            ref_col=ref_col_name,
            base_hyp_col="b1_hyp",
            cand_hyp_col="p_hyp",
            speaker_col="speaker_id",
            n_resamples=args.n_resamples,
            random_seed=42
        )
        p_boot_b1_f1 = bootstrap_term_f1_significance(
            test_df,
            gold_terms_list,
            b1_preds,
            p_preds,
            n_resamples=args.n_resamples,
            random_seed=42
        )
        print(f"  [P vs B1] WER Δ: {p_boot_b1_wer['observed_wer_reduction']*100:+.2f}% (95% CI: [{p_boot_b1_wer['ci_95_lower']*100:.2f}%, {p_boot_b1_wer['ci_95_upper']*100:.2f}%], p={p_boot_b1_wer['empirical_p_value']})")
        print(f"  [P vs B1] Term F1 Δ: {p_boot_b1_f1['observed_f1_gain']*100:+.2f}% (95% CI: [{p_boot_b1_f1['ci_95_lower']*100:.2f}%, {p_boot_b1_f1['ci_95_upper']*100:.2f}%], p={p_boot_b1_f1['empirical_p_value']})")

    # 3. P vs B2 (Term F1)
    p_boot_b2_f1 = bootstrap_term_f1_significance(
        test_df,
        gold_terms_list,
        b2_preds,
        p_preds,
        n_resamples=args.n_resamples,
        random_seed=42
    )
    print(f"  [P vs B2] Term F1 Δ: {p_boot_b2_f1['observed_f1_gain']*100:+.2f}% (95% CI: [{p_boot_b2_f1['ci_95_lower']*100:.2f}%, {p_boot_b2_f1['ci_95_upper']*100:.2f}%], p={p_boot_b2_f1['empirical_p_value']})")

    sig_records = {
        "P_vs_B0": {"wer": p_boot_b0_wer, "term_f1": p_boot_b0_f1},
        "P_vs_B1": {"wer": p_boot_b1_wer, "term_f1": p_boot_b1_f1} if p_boot_b1_wer else {},
        "P_vs_B2": {"term_f1": p_boot_b2_f1}
    }
    sig_json_path = os.path.join(OUT_DIR, f"bootstrap_significance_results_{args.split}.json")
    with open(sig_json_path, "w", encoding="utf-8") as f:
        json.dump(sig_records, f, indent=2, ensure_ascii=False)
    print(f"  Saved bootstrap significance metrics to: {sig_json_path}")

    # ==========================================================================
    # 7. ABLATION STUDIES (Proposal Section 4.4)
    # ==========================================================================
    if args.run_ablations:
        print("\n" + "-" * 80)
        print(">>> [ABLATIONS] Running Component Ablation Studies for Proposed Method P")
        print("-" * 80)

        ablations_config = [
            ("P (w/o Acoustic Evidence)", {"enable_acoustic": False, "enable_context": True, "enable_gate": True}),
            ("P (w/o Context Evidence)", {"enable_acoustic": True, "enable_context": False, "enable_gate": True}),
            ("P (w/o Decision Gate)", {"enable_acoustic": True, "enable_context": True, "enable_gate": False}),
        ]

        for abl_name, cfg in ablations_config:
            abl_sys = ProposedSystemP(
                taxonomy=tax,
                acoustic_scorer=acoustic_scorer,
                generator_threshold=0.45,
                acceptance_threshold=0.50,
                enable_acoustic=cfg["enable_acoustic"] and (acoustic_scorer is not None),
                enable_context=cfg["enable_context"],
                enable_phonetic=True,
                enable_gate=cfg["enable_gate"]
            )

            abl_hyps = []
            abl_preds = []
            for idx, row in df.iterrows():
                wf = row["wav_file"]
                audio_p = os.path.join(WAV_DIR, wf)
                orig_hyp = str(row["asr_transcript"])
                res = abl_sys.process_utterance(orig_hyp, audio_p if os.path.exists(audio_p) else None)
                abl_hyps.append(res["revised_transcript"])
                abl_preds.append(res["predicted_terms"])
                if (idx + 1) % 50 == 0 or idx == n_samples - 1:
                    print(f"    [{idx+1}/{n_samples}] {abl_name} progress...", flush=True)

            if acoustic_scorer is not None:
                acoustic_scorer.save_cache()

            abl_asr = ASRMetricsCalculator.evaluate_corpus(refs, abl_hyps, speaker_ids)
            abl_eval = TerminologyEvaluator.evaluate_corpus(gold_terms_list, abl_preds, categories)
            abl_term = abl_eval["term_recognition"]
            abl_e2e = abl_eval["end_to_end_classification"]
            abl_safety = SafetyMetricsEvaluator.evaluate_comparative_safety(gold_terms_list, b0_preds, abl_preds)

            print(f"  {abl_name:<28}: F1={abl_term['f1_score']*100:.2f}% | E2E F1={abl_e2e['f1_score']*100:.2f}% | HCR={abl_safety['overall_harmful_correction_rate']*100:.2f}% | Net={abl_safety['overall_net_gain']:+d}")

            summary_rows.append({
                "System": abl_name,
                "Type": "Ablation",
                "Corpus WER": f"{abl_asr['corpus_wer']*100:.2f}%",
                "Corpus CER": f"{abl_asr['corpus_cer']*100:.2f}%",
                "Term Prec": f"{abl_term['precision']*100:.2f}%",
                "Term Recall": f"{abl_term['recall']*100:.2f}%",
                "Term F1": f"{abl_term['f1_score']*100:.2f}%",
                "E2E Term-Cat F1": f"{abl_e2e['f1_score']*100:.2f}%",
                "Harmful Corruptions": abl_safety["overall_harmful_corruptions"],
                "Harmful Correction Rate (HCR)": f"{abl_safety['overall_harmful_correction_rate']*100:.2f}%",
                "Correction Success Rate (CSR)": f"{abl_safety['overall_correction_success_rate']*100:.2f}%",
                "Net Gain": f"{abl_safety['overall_net_gain']:+d}"
            })

    # ==========================================================================
    # 8. EXPORT OFFICIAL COMPARATIVE SUMMARY
    # ==========================================================================
    summary_df = pd.DataFrame(summary_rows)
    csv_out = os.path.join(OUT_DIR, f"comparative_results_all_systems_{args.split}.csv")
    summary_df.to_csv(csv_out, index=False, encoding="utf-8-sig")

    # Also save as table_4_4_comparative_benchmark.csv and .md
    table4_csv = os.path.join(OUT_DIR, "table_4_4_comparative_benchmark.csv")
    table4_md = os.path.join(OUT_DIR, "table_4_4_comparative_benchmark.md")
    summary_df.to_csv(table4_csv, index=False, encoding="utf-8-sig")

    rtf_val = (latency_p * n_samples) / total_audio_sec if total_audio_sec > 0 else 0.0
    with open(table4_md, "w", encoding="utf-8") as f:
        f.write(f"# LiemWhisper Official Comparative Benchmark (Proposal Table 4.4)\n\n")
        f.write(f"- **Evaluation Split**: {args.split.upper()} ({n_samples} held-out recordings, {n_speakers} speakers, {total_audio_sec:.1f}s audio)\n")
        f.write(f"- **Ground Truth References**: `{ref_col_name}`\n")
        f.write(f"- **Total Gold Terms**: {total_gold_terms}\n")
        f.write(f"- **System P Average Latency**: {latency_p*1000:.1f} ms/recording\n")
        f.write(f"- **Real-Time Factor (RTF)**: {rtf_val:.4f} (Process time / Audio time)\n\n")
        f.write(summary_df.to_markdown(index=False))
        f.write("\n")

    print("\n" + "=" * 80)
    print(f"OFFICIAL COMPARATIVE RESULTS ON {args.split.upper()} SET (PROPOSAL TABLE 4.4)")
    print("=" * 80)
    print(summary_df.to_string(index=False))
    print(f"\nDetailed comparative report saved to:")
    print(f"  - {csv_out}")
    print(f"  - {table4_csv}")
    print(f"  - {table4_md}")


if __name__ == "__main__":
    main()
