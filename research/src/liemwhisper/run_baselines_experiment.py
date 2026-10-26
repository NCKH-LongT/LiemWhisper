"""
LiemWhisper Baselines Experiment Runner
=======================================
Executes the comparative experiment specified in Proposal Section 4.4:
- System B0: ASR + exact matching + taxonomy lookup
- System B1: ASR + glossary prompt + lookup
- System B2: ASR + fuzzy matching + lookup

Generates official comparative metrics, safety analysis (Harmful-Correction Rate),
and statistical significance testing on the held-out Test split.
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

# Ensure imports work
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

# Find workspace root directory containing 'Data/glossary_taxonomy_v1.json'
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
MANIFEST_PATH = os.path.join(DATA_DIR, "annotation_with_asr_v1.csv")
OUT_DIR = os.path.join(DATA_DIR, "benchmark_results")
B1_CACHE_PATH = os.path.join(OUT_DIR, "asr_b1_glossary_prompting.csv")


def parse_args():
    parser = argparse.ArgumentParser(description="Run LiemWhisper Baselines Comparative Experiment")
    parser.add_argument("--split", type=str, default="test", help="Split to evaluate: test, val, or all")
    parser.add_argument("--fuzzy-threshold", type=float, default=0.75, help="Similarity threshold for System B2")
    parser.add_argument("--skip-b1-gpu", action="store_true", help="Skip running B1 GPU inference if only testing B0/B2")
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 75)
    print("LIEMWHISPER COMPARATIVE BASELINES EXPERIMENT (B0 vs B1 vs B2)")
    print("=" * 75)
    print(f"Target Split       : {args.split.upper()}")
    print(f"Manifest           : {MANIFEST_PATH}")
    print(f"Taxonomy           : {TAXONOMY_PATH}")
    print(f"Fuzzy Threshold B2 : {args.fuzzy_threshold}")

    # 1. Load Taxonomy
    tax = TaxonomyManager(TAXONOMY_PATH)
    categories = list(tax.categories.keys())
    print(f"Loaded {len(tax.canonical_terms)} taxonomy terms across {len(categories)} categories.")

    # 2. Load Manifest
    df = pd.read_csv(MANIFEST_PATH)
    if args.split != "all":
        df = df[df["split"] == args.split].reset_index(drop=True)

    n_samples = len(df)
    n_speakers = df["speaker_id"].nunique()
    print(f"Evaluating {n_samples} recordings from {n_speakers} held-out speakers.")

    # Parse ground truth terms and references
    refs = df["prompt_text"].fillna("").astype(str).tolist()
    speaker_ids = df["speaker_id"].astype(str).tolist()

    gold_terms_list = []
    for _, row in df.iterrows():
        cat = str(row.get("primary_category_hint", "Unassigned"))
        raw = row.get("target_terms_hint", "")
        gold_terms_list.append(TerminologyEvaluator.parse_term_list(raw, cat))

    total_gold_terms = sum(len(g) for g in gold_terms_list)
    print(f"Total ground-truth term occurrences: {total_gold_terms}")

    # ==========================================================================
    # 3. SYSTEM B0: ASR + Exact Matching + Taxonomy Lookup
    # ==========================================================================
    print("\n" + "-" * 75)
    print(">>> [SYSTEM B0] ASR (Raw Whisper Small) + Exact Matching + Taxonomy Lookup")
    print("-" * 75)
    b0_matcher = ExactMatchingBaseline(tax)
    b0_hyps = df["asr_transcript"].fillna("").astype(str).tolist()

    # ASR WER/CER
    b0_asr = ASRMetricsCalculator.evaluate_corpus(refs, b0_hyps, speaker_ids)
    print(f"  Corpus WER: {b0_asr['corpus_wer']*100:.2f}% | Corpus CER: {b0_asr['corpus_cer']*100:.2f}%")

    # Term Extraction
    b0_preds = [b0_matcher.extract_terms(h) for h in b0_hyps]
    b0_eval = TerminologyEvaluator.evaluate_corpus(gold_terms_list, b0_preds, categories)

    b0_term = b0_eval["term_recognition"]
    b0_e2e = b0_eval["end_to_end_classification"]
    print(f"  Term Recognition  : Precision={b0_term['precision']*100:.2f}%, Recall={b0_term['recall']*100:.2f}%, F1={b0_term['f1_score']*100:.2f}%")
    print(f"  E2E Term-Category : Precision={b0_e2e['precision']*100:.2f}%, Recall={b0_e2e['recall']*100:.2f}%, F1={b0_e2e['f1_score']*100:.2f}%")
    print(f"  Category Macro-F1 : {b0_e2e['category_macro_f1']*100:.2f}%")

    # ==========================================================================
    # 4. SYSTEM B2: ASR + Lexical Fuzzy Matching + Taxonomy Lookup
    # ==========================================================================
    print("\n" + "-" * 75)
    print(f">>> [SYSTEM B2] ASR + Lexical Fuzzy Matching (θ={args.fuzzy_threshold}) + Taxonomy Lookup")
    print("-" * 75)
    b2_matcher = LexicalFuzzyMatcher(tax, similarity_threshold=args.fuzzy_threshold)

    # B2 operates on the baseline ASR transcript (pure lexical post-correction)
    b2_preds = [b2_matcher.extract_terms(h) for h in b0_hyps]
    b2_eval = TerminologyEvaluator.evaluate_corpus(gold_terms_list, b2_preds, categories)

    b2_term = b2_eval["term_recognition"]
    b2_e2e = b2_eval["end_to_end_classification"]
    print(f"  Term Recognition  : Precision={b2_term['precision']*100:.2f}%, Recall={b2_term['recall']*100:.2f}%, F1={b2_term['f1_score']*100:.2f}%")
    print(f"  E2E Term-Category : Precision={b2_e2e['precision']*100:.2f}%, Recall={b2_e2e['recall']*100:.2f}%, F1={b2_e2e['f1_score']*100:.2f}%")
    print(f"  Category Macro-F1 : {b2_e2e['category_macro_f1']*100:.2f}%")

    # Safety Metrics B2 vs B0
    b2_safety = SafetyMetricsEvaluator.evaluate_comparative_safety(gold_terms_list, b0_preds, b2_preds)
    print(f"  [Safety vs B0] Harmful-Correction Rate (HCR): {b2_safety['overall_harmful_correction_rate']*100:.2f}% ({b2_safety['overall_harmful_corruptions']} corrupted)")
    print(f"  [Safety vs B0] Correction Success Rate (CSR): {b2_safety['overall_correction_success_rate']*100:.2f}% ({b2_safety['overall_successful_corrections']} fixed)")
    print(f"  [Safety vs B0] Net Accuracy Gain            : {b2_safety['overall_net_gain']:+d} utterances")

    # ==========================================================================
    # 5. SYSTEM B1: ASR + Glossary Prompting + Lookup
    # ==========================================================================
    b1_results = {}
    if not args.skip_b1_gpu:
        print("\n" + "-" * 75)
        print(">>> [SYSTEM B1] ASR (Glossary Prompted Whisper Small) + Exact Match + Lookup")
        print("-" * 75)

        # Check existing B1 cache
        b1_cache = {}
        if os.path.exists(B1_CACHE_PATH):
            try:
                c_df = pd.read_csv(B1_CACHE_PATH)
                for _, r in c_df.iterrows():
                    b1_cache[r["wav_file"]] = str(r["b1_transcript"])
                print(f"Found {len(b1_cache)} cached B1 transcripts in {B1_CACHE_PATH}.")
            except Exception as e:
                print(f"Note reading cache: {e}")

        # Run inference for missing files
        b1_hyps = []
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
                    print(f"Warning: Audio file not found: {wf}")
                    b1_hyps.append("")
                    continue

                missing_count += 1
                res = b1_model.transcribe(audio_p, beam_size=5)
                b1_hyps.append(res["transcript"])
                b1_cache[wf] = res["transcript"]

                if missing_count % 20 == 0 or idx == n_samples - 1:
                    print(f"  [{idx+1}/{n_samples}] Transcribed B1 with prompt: {wf} ({res['inference_seconds']}s) -> {res['transcript'][:50]}...", flush=True)

        # Save updated cache
        cache_records = [{"wav_file": k, "b1_transcript": v} for k, v in b1_cache.items()]
        pd.DataFrame(cache_records).to_csv(B1_CACHE_PATH, index=False, encoding="utf-8-sig")

        # Evaluate B1 ASR WER/CER
        b1_asr = ASRMetricsCalculator.evaluate_corpus(refs, b1_hyps, speaker_ids)
        print(f"  Corpus WER: {b1_asr['corpus_wer']*100:.2f}% | Corpus CER: {b1_asr['corpus_cer']*100:.2f}%")

        # Extract terms using exact match on B1
        b1_preds = [b0_matcher.extract_terms(h) for h in b1_hyps]
        b1_eval = TerminologyEvaluator.evaluate_corpus(gold_terms_list, b1_preds, categories)

        b1_term = b1_eval["term_recognition"]
        b1_e2e = b1_eval["end_to_end_classification"]
        print(f"  Term Recognition  : Precision={b1_term['precision']*100:.2f}%, Recall={b1_term['recall']*100:.2f}%, F1={b1_term['f1_score']*100:.2f}%")
        print(f"  E2E Term-Category : Precision={b1_e2e['precision']*100:.2f}%, Recall={b1_e2e['recall']*100:.2f}%, F1={b1_e2e['f1_score']*100:.2f}%")
        print(f"  Category Macro-F1 : {b1_e2e['category_macro_f1']*100:.2f}%")

        # Safety Metrics B1 vs B0
        b1_safety = SafetyMetricsEvaluator.evaluate_comparative_safety(gold_terms_list, b0_preds, b1_preds)
        print(f"  [Safety vs B0] Harmful-Correction Rate (HCR): {b1_safety['overall_harmful_correction_rate']*100:.2f}% ({b1_safety['overall_harmful_corruptions']} corrupted)")
        print(f"  [Safety vs B0] Correction Success Rate (CSR): {b1_safety['overall_correction_success_rate']*100:.2f}% ({b1_safety['overall_successful_corrections']} fixed)")
        print(f"  [Safety vs B0] Net Accuracy Gain            : {b1_safety['overall_net_gain']:+d} utterances")

        # Statistical significance test: Paired Bootstrap on WER
        b1_df = df.copy()
        b1_df["b0_hyp"] = b0_hyps
        b1_df["b1_hyp"] = b1_hyps
        b1_boot = PairedBootstrapTester.test_wer_difference(
            b1_df,
            ref_col="prompt_text",
            base_hyp_col="b0_hyp",
            cand_hyp_col="b1_hyp",
            speaker_col="speaker_id",
            n_resamples=2000,
            random_seed=42
        )
        print(f"  [Bootstrap 2000 resamples] WER Δ: {b1_boot['observed_wer_reduction']*100:+.2f}% (95% CI: [{b1_boot['ci_95_lower']*100:.2f}%, {b1_boot['ci_95_upper']*100:.2f}%], p={b1_boot['empirical_p_value']})")

    # ==========================================================================
    # 6. EXPORT OFFICIAL COMPARATIVE SUMMARY
    # ==========================================================================
    rows = [
        {
            "System": "B0: Raw ASR + Exact Match",
            "Description": "Whisper Small + Exact Substring Lookup",
            "Corpus WER": f"{b0_asr['corpus_wer']*100:.2f}%",
            "Corpus CER": f"{b0_asr['corpus_cer']*100:.2f}%",
            "Term Prec": f"{b0_term['precision']*100:.2f}%",
            "Term Recall": f"{b0_term['recall']*100:.2f}%",
            "Term F1": f"{b0_term['f1_score']*100:.2f}%",
            "E2E Term-Cat F1": f"{b0_e2e['f1_score']*100:.2f}%",
            "Harmful Corruptions": 0,
            "Harmful Correction Rate (HCR)": "0.00%",
            "Correction Success Rate (CSR)": "0.00%",
            "Net Gain": 0
        },
        {
            "System": "B2: Lexical Fuzzy Matching",
            "Description": f"ASR + Levenshtein Similarity (θ={args.fuzzy_threshold})",
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
        }
    ]

    if not args.skip_b1_gpu:
        rows.insert(1, {
            "System": "B1: Glossary Prompting",
            "Description": "Whisper Small + initial_prompt biasing",
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

    summary_df = pd.DataFrame(rows)
    csv_out = os.path.join(OUT_DIR, f"baselines_comparison_{args.split}.csv")
    summary_df.to_csv(csv_out, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 75)
    print(f"OFFICIAL COMPARATIVE RESULTS ON {args.split.upper()} SET (PROPOSAL TABLE 4.4)")
    print("=" * 75)
    print(summary_df.to_string(index=False))
    print(f"\nDetailed comparative report saved to: {csv_out}")


if __name__ == "__main__":
    main()
