"""
PhoWhisper Benchmark Runner on LiemWhisper Test Set (Proposal Section 4.4)
==========================================================================
Evaluates vinai/phowhisper-small (via CTranslate2) on the held-out TEST split
to establish the official Vietnamese Monolingual Baseline B0-PhoWhisper:
- Transcribes all 245 test files
- Computes Uncapped Corpus WER & CER
- Computes Term Precision, Recall, F1 and End-to-End Term-Category F1
- Compares against OpenAI Whisper Small B0 and LiemWhisper System P
- Saves predictions and updates the official benchmark table
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
    ExactMatchingBaseline
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
PHO_CACHE_PATH = os.path.join(OUT_DIR, "asr_phowhisper_small_test.csv")
COMPARATIVE_PATH = os.path.join(OUT_DIR, "comparative_results_all_systems_test.csv")


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    print("=" * 80)
    print("PHOWHISPER SMALL BENCHMARK ON LIEMWHISPER TEST SET (PROPOSAL TABLE 4.4)")
    print("=" * 80)

    # 1. Load Taxonomy
    tax = TaxonomyManager(TAXONOMY_PATH)
    categories = list(tax.categories.keys())
    exact_matcher = ExactMatchingBaseline(tax)
    print(f"Loaded {len(tax.canonical_terms)} taxonomy terms across {len(categories)} categories.")

    # 2. Load Manifest Test Set
    df = pd.read_csv(MANIFEST_PATH)
    df = df[df["split"] == "test"].reset_index(drop=True)
    n_samples = len(df)
    n_speakers = df["speaker_id"].nunique()
    print(f"Evaluating {n_samples} test recordings from {n_speakers} held-out speakers.")

    refs = df["prompt_text"].fillna("").astype(str).tolist()
    speaker_ids = df["speaker_id"].astype(str).tolist()

    gold_terms_list = []
    for _, row in df.iterrows():
        cat = str(row.get("primary_category_hint", "Unassigned"))
        raw = row.get("target_terms_hint", "")
        gold_terms_list.append(TerminologyEvaluator.parse_term_list(raw, cat))

    # Baseline B0 (Whisper Small) preds for comparison
    b0_hyps = df["asr_transcript"].fillna("").astype(str).tolist()
    b0_preds = [exact_matcher.extract_terms(h) for h in b0_hyps]

    # 3. Transcribe with PhoWhisper Small
    pho_cache = {}
    if os.path.exists(PHO_CACHE_PATH):
        try:
            c_df = pd.read_csv(PHO_CACHE_PATH)
            for _, r in c_df.iterrows():
                pho_cache[r["wav_file"]] = str(r["phowhisper_transcript"])
            print(f"Found {len(pho_cache)} cached PhoWhisper transcripts.")
        except Exception as e:
            print(f"Note reading PhoWhisper cache: {e}")

    pho_model = None
    pho_hyps = []
    missing_count = 0
    t0 = time.time()

    for idx, row in df.iterrows():
        wf = row["wav_file"]
        if wf in pho_cache:
            pho_hyps.append(pho_cache[wf])
        else:
            if pho_model is None:
                from faster_whisper import WhisperModel
                print("Loading diepho/PhoWhisper-small-ct2 on CUDA...")
                pho_model = WhisperModel("diepho/PhoWhisper-small-ct2", device="cuda", compute_type="float16")

            audio_p = os.path.join(WAV_DIR, wf)
            if not os.path.exists(audio_p):
                pho_hyps.append("")
                continue

            missing_count += 1
            segments, info = pho_model.transcribe(
                audio_p,
                language="vi",
                task="transcribe",
                beam_size=5,
                vad_filter=True,
                vad_parameters=dict(min_silence_duration_ms=500)
            )
            text = " ".join([s.text.strip() for s in segments])
            pho_hyps.append(text)
            pho_cache[wf] = text

            if missing_count % 25 == 0 or idx == n_samples - 1:
                print(f"  [{idx+1}/{n_samples}] Transcribed PhoWhisper: {wf} -> {text[:60]}...", flush=True)

    if missing_count > 0:
        cache_records = [{"wav_file": k, "phowhisper_transcript": v} for k, v in pho_cache.items()]
        pd.DataFrame(cache_records).to_csv(PHO_CACHE_PATH, index=False, encoding="utf-8-sig")
        print(f"Updated PhoWhisper cache at: {PHO_CACHE_PATH}")

    total_time = time.time() - t0
    print(f"Transcription complete in {total_time:.2f}s ({total_time*1000/n_samples:.1f}ms/file)")

    # 4. Evaluate PhoWhisper Metrics
    pho_asr = ASRMetricsCalculator.evaluate_corpus(refs, pho_hyps, speaker_ids)
    print("\n" + "-" * 75)
    print("PHOWHISPER SMALL OFFICIAL RESULTS:")
    print("-" * 75)
    print(f"  Corpus WER: {pho_asr['corpus_wer']*100:.2f}% | Corpus CER: {pho_asr['corpus_cer']*100:.2f}%")

    pho_preds = [exact_matcher.extract_terms(h) for h in pho_hyps]
    pho_eval = TerminologyEvaluator.evaluate_corpus(gold_terms_list, pho_preds, categories)

    pho_term = pho_eval["term_recognition"]
    pho_e2e = pho_eval["end_to_end_classification"]
    print(f"  Term Recognition  : Precision={pho_term['precision']*100:.2f}%, Recall={pho_term['recall']*100:.2f}%, F1={pho_term['f1_score']*100:.2f}%")
    print(f"  E2E Term-Category : Precision={pho_e2e['precision']*100:.2f}%, Recall={pho_e2e['recall']*100:.2f}%, F1={pho_e2e['f1_score']*100:.2f}%")
    print(f"  Category Macro-F1 : {pho_e2e['category_macro_f1']*100:.2f}%")

    pho_safety = SafetyMetricsEvaluator.evaluate_comparative_safety(gold_terms_list, b0_preds, pho_preds)
    print(f"  [Safety vs B0] Harmful-Correction Rate (HCR): {pho_safety['overall_harmful_correction_rate']*100:.2f}% ({pho_safety['overall_harmful_corruptions']} corrupted)")
    print(f"  [Safety vs B0] Correction Success Rate (CSR): {pho_safety['overall_correction_success_rate']*100:.2f}% ({pho_safety['overall_successful_corrections']} fixed)")
    print(f"  [Safety vs B0] Net Accuracy Gain            : {pho_safety['overall_net_gain']:+d} utterances")

    # 5. Insert PhoWhisper into Comparative Table
    new_row = {
        "System": "B0-Pho: Raw PhoWhisper Small",
        "Type": "Baseline",
        "Corpus WER": f"{pho_asr['corpus_wer']*100:.2f}%",
        "Corpus CER": f"{pho_asr['corpus_cer']*100:.2f}%",
        "Term Prec": f"{pho_term['precision']*100:.2f}%",
        "Term Recall": f"{pho_term['recall']*100:.2f}%",
        "Term F1": f"{pho_term['f1_score']*100:.2f}%",
        "E2E Term-Cat F1": f"{pho_e2e['f1_score']*100:.2f}%",
        "Harmful Corruptions": pho_safety["overall_harmful_corruptions"],
        "Harmful Correction Rate (HCR)": f"{pho_safety['overall_harmful_correction_rate']*100:.2f}%",
        "Correction Success Rate (CSR)": f"{pho_safety['overall_correction_success_rate']*100:.2f}%",
        "Net Gain": f"{pho_safety['overall_net_gain']:+d}"
    }

    if os.path.exists(COMPARATIVE_PATH):
        comp_df = pd.read_csv(COMPARATIVE_PATH)
        # Check if already present
        if "B0-Pho: Raw PhoWhisper Small" in comp_df["System"].values:
            comp_df = comp_df[comp_df["System"] != "B0-Pho: Raw PhoWhisper Small"]
        
        # Insert right after B0
        idx_b0 = 0
        for i, r in comp_df.iterrows():
            if "B0:" in r["System"]:
                idx_b0 = i
                break
        
        part1 = comp_df.iloc[:idx_b0 + 1]
        part2 = comp_df.iloc[idx_b0 + 1:]
        comp_df = pd.concat([part1, pd.DataFrame([new_row]), part2], ignore_index=True)
        comp_df.to_csv(COMPARATIVE_PATH, index=False, encoding="utf-8-sig")
        print("\n" + "=" * 80)
        print("UPDATED OFFICIAL COMPARATIVE TABLE (PROPOSAL TABLE 4.4):")
        print("=" * 80)
        print(comp_df.to_string(index=False))
        print(f"\nSaved updated comparative report to: {COMPARATIVE_PATH}")


if __name__ == "__main__":
    main()
