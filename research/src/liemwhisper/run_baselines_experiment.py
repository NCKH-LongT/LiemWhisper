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
MANIFEST_PATH = os.path.join(DATA_DIR, "annotation_with_asr_v1.csv")
OUT_DIR = os.path.join(DATA_DIR, "benchmark_results")
B1_CACHE_PATH = os.path.join(OUT_DIR, "asr_b1_glossary_prompting.csv")


def parse_args():
    parser = argparse.ArgumentParser(description="Run LiemWhisper Official Comparative Experiment (Proposal Table 4.4)")
    parser.add_argument("--split", type=str, default="test", help="Split to evaluate: test, val, or all")
    parser.add_argument("--fuzzy-threshold", type=float, default=0.75, help="Similarity threshold for System B2")
    parser.add_argument("--skip-b1-gpu", action="store_true", help="Skip running B1 GPU inference if only testing B0/B2/P")
    parser.add_argument("--skip-acoustic", action="store_true", help="Run System P without GPU teacher-forcing logprob")
    parser.add_argument("--run-ablations", action="store_true", default=True, help="Run ablation studies for System P")
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(OUT_DIR, exist_ok=True)

    print("=" * 80)
    print("LIEMWHISPER COMPARATIVE BENCHMARK: BASELINES vs PROPOSED METHOD P")
    print("=" * 80)
    print(f"Target Split            : {args.split.upper()}")
    print(f"Manifest                : {MANIFEST_PATH}")
    print(f"Taxonomy                : {TAXONOMY_PATH}")
    print(f"Fuzzy Threshold B2      : {args.fuzzy_threshold}")
    print(f"Run Ablations           : {args.run_ablations}")

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

    refs = df["prompt_text"].fillna("").astype(str).tolist()
    speaker_ids = df["speaker_id"].astype(str).tolist()

    gold_terms_list = []
    for _, row in df.iterrows():
        cat = str(row.get("primary_category_hint", "Unassigned"))
        raw = row.get("target_terms_hint", "")
        gold_terms_list.append(TerminologyEvaluator.parse_term_list(raw, cat))

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

    t0_p = time.time()
    p_hyps = []
    p_preds = []
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

    # Save detailed System P predictions (Appendix A format)
    pred_csv = os.path.join(OUT_DIR, f"predictions_system_p_{args.split}.csv")
    pd.DataFrame(p_records).to_csv(pred_csv, index=False, encoding="utf-8-sig")
    print(f"  Saved structured predictions to: {pred_csv}")

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

    # Statistical significance test: Paired Bootstrap on WER comparing P vs B0
    test_df = df.copy()
    test_df["b0_hyp"] = b0_hyps
    test_df["p_hyp"] = p_hyps
    p_boot_b0 = PairedBootstrapTester.test_wer_difference(
        test_df,
        ref_col="prompt_text",
        base_hyp_col="b0_hyp",
        cand_hyp_col="p_hyp",
        speaker_col="speaker_id",
        n_resamples=2000,
        random_seed=42
    )
    print(f"  [Bootstrap 2000 resamples: P vs B0] WER Δ: {p_boot_b0['observed_wer_reduction']*100:+.2f}% (95% CI: [{p_boot_b0['ci_95_lower']*100:.2f}%, {p_boot_b0['ci_95_upper']*100:.2f}%], p={p_boot_b0['empirical_p_value']})")

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

    print("\n" + "=" * 80)
    print(f"OFFICIAL COMPARATIVE RESULTS ON {args.split.upper()} SET (PROPOSAL TABLE 4.4)")
    print("=" * 80)
    print(summary_df.to_string(index=False))
    print(f"\nDetailed comparative report saved to: {csv_out}")


if __name__ == "__main__":
    main()
