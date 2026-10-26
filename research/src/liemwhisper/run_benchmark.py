"""
LiemWhisper Benchmark Evaluation Runner
=======================================
Runs formal evaluation across dataset splits (Train / Val / Test)
implementing the metrics required by Proposal Section 4.4.

Outputs:
1. benchmark_summary.json
2. benchmark_summary_table.csv
3. category_breakdown.csv
4. per_speaker_distribution.csv
"""

import os
import sys
import argparse
import json
import numpy as np
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Add scripts directory to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from evaluation_toolkit import (
    TextNormalizer,
    ASRMetricsCalculator,
    TerminologyOccurrence,
    TerminologyEvaluator,
    SafetyMetricsEvaluator,
    PairedBootstrapTester
)

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, "Data")
DEFAULT_INPUT = os.path.join(DATA_DIR, "annotation_with_asr_v1.csv")
DEFAULT_TAXONOMY = os.path.join(DATA_DIR, "glossary_taxonomy_v1.json")
DEFAULT_OUT_DIR = os.path.join(DATA_DIR, "benchmark_results")


def parse_args():
    parser = argparse.ArgumentParser(description="Run LiemWhisper Benchmark Evaluation")
    parser.add_argument("--input", type=str, default=DEFAULT_INPUT, help="Path to input manifest/annotations")
    parser.add_argument("--taxonomy", type=str, default=DEFAULT_TAXONOMY, help="Path to taxonomy JSON")
    parser.add_argument("--out-dir", type=str, default=DEFAULT_OUT_DIR, help="Output directory for reports")
    parser.add_argument("--ref-col", type=str, default="prompt_text", help="Reference text column")
    parser.add_argument("--hyp-col", type=str, default="asr_transcript", help="Hypothesis text column")
    parser.add_argument("--gold-terms-col", type=str, default="target_terms_hint", help="Gold terms column")
    parser.add_argument("--pred-terms-col", type=str, default="b0_exact_matches", help="Predicted terms column")
    parser.add_argument("--category-col", type=str, default="primary_category_hint", help="Category column")
    return parser.parse_args()


def evaluate_split(
    df: pd.DataFrame,
    split_name: str,
    categories: list,
    args
) -> dict:
    sub_df = df[df["split"] == split_name].reset_index(drop=True)
    n = len(sub_df)
    if n == 0:
        return {}

    refs = sub_df[args.ref_col].fillna("").astype(str).tolist()
    hyps = sub_df[args.hyp_col].fillna("").astype(str).tolist()
    spk_ids = sub_df["speaker_id"].astype(str).tolist()

    # 1. ASR Metrics
    asr_res = ASRMetricsCalculator.evaluate_corpus(refs, hyps, spk_ids)

    # 2. Terminology Occurrences
    gold_occurrences = []
    pred_occurrences = []

    for _, row in sub_df.iterrows():
        cat = str(row.get(args.category_col, "Unassigned"))
        g_raw = row.get(args.gold_terms_col, "")
        p_raw = row.get(args.pred_terms_col, "")

        gold_occurrences.append(TerminologyEvaluator.parse_term_list(g_raw, cat))
        pred_occurrences.append(TerminologyEvaluator.parse_term_list(p_raw, cat))

    term_res = TerminologyEvaluator.evaluate_corpus(
        gold_occurrences,
        pred_occurrences,
        taxonomy_categories=categories
    )

    # 3. Per-speaker breakdown
    spk_stats = {}
    sample_records = asr_res["sample_records"]
    for rec in sample_records:
        spk = rec["speaker_id"]
        if spk not in spk_stats:
            spk_stats[spk] = {"ref_words": 0, "word_edits": 0, "count": 0}
        spk_stats[spk]["ref_words"] += rec["n_ref_words"]
        spk_stats[spk]["word_edits"] += rec["word_edits"]
        spk_stats[spk]["count"] += 1

    spk_wers = [
        (s["word_edits"] / s["ref_words"]) if s["ref_words"] > 0 else 0.0
        for s in spk_stats.values()
    ]

    return {
        "split": split_name,
        "utterance_count": n,
        "speaker_count": sub_df["speaker_id"].nunique(),
        "total_ref_words": asr_res["total_ref_words"],
        "corpus_wer": asr_res["corpus_wer"],
        "corpus_cer": asr_res["corpus_cer"],
        "macro_wer": asr_res["macro_wer"],
        "macro_cer": asr_res["macro_cer"],
        "speaker_wer_mean": round(float(np.mean(spk_wers)), 6),
        "speaker_wer_std": round(float(np.std(spk_wers)), 6),
        "speaker_wer_min": round(float(np.min(spk_wers)), 6),
        "speaker_wer_max": round(float(np.max(spk_wers)), 6),
        "term_precision": term_res["term_recognition"]["precision"],
        "term_recall": term_res["term_recognition"]["recall"],
        "term_f1": term_res["term_recognition"]["f1_score"],
        "e2e_term_cat_precision": term_res["end_to_end_classification"]["precision"],
        "e2e_term_cat_recall": term_res["end_to_end_classification"]["recall"],
        "e2e_term_cat_f1": term_res["end_to_end_classification"]["f1_score"],
        "category_macro_f1": term_res["end_to_end_classification"]["category_macro_f1"],
        "per_category": term_res["end_to_end_classification"]["per_category"]
    }


def main():
    args = parse_args()
    print("=" * 70)
    print("LIEMWHISPER BENCHMARK EVALUATION HARNESS")
    print("=" * 70)
    print(f"Input file : {args.input}")
    print(f"Taxonomy   : {args.taxonomy}")
    print(f"Output dir : {args.out_dir}")

    os.makedirs(args.out_dir, exist_ok=True)

    # Load taxonomy
    with open(args.taxonomy, "r", encoding="utf-8") as f:
        tax = json.load(f)
    categories = list(tax.get("categories", {}).keys())

    # Load dataset
    df = pd.read_csv(args.input)
    print(f"Loaded {len(df)} total recordings across splits: {list(df['split'].unique())}")

    # Evaluate each split
    splits_to_eval = ["test", "val", "train"]
    split_results = {}
    summary_rows = []

    for sp in splits_to_eval:
        print(f"\n--- Evaluating Split: {sp.upper()} ---")
        res = evaluate_split(df, sp, categories, args)
        split_results[sp] = res
        summary_rows.append({
            "Split": sp.upper(),
            "Speakers": res["speaker_count"],
            "Utterances": res["utterance_count"],
            "Corpus WER": f"{res['corpus_wer'] * 100:.2f}%",
            "Corpus CER": f"{res['corpus_cer'] * 100:.2f}%",
            "Term Prec": f"{res['term_precision'] * 100:.2f}%",
            "Term Recall": f"{res['term_recall'] * 100:.2f}%",
            "Term F1": f"{res['term_f1'] * 100:.2f}%",
            "E2E Term-Cat F1": f"{res['e2e_term_cat_f1'] * 100:.2f}%",
            "Cat Macro F1": f"{res['category_macro_f1'] * 100:.2f}%"
        })
        print(f"  Utterances: {res['utterance_count']} | Speakers: {res['speaker_count']}")
        print(f"  Corpus WER: {res['corpus_wer']*100:.2f}% | Corpus CER: {res['corpus_cer']*100:.2f}%")
        print(f"  Term Recognition  : Precision={res['term_precision']*100:.2f}%, Recall={res['term_recall']*100:.2f}%, F1={res['term_f1']*100:.2f}%")
        print(f"  E2E Term-Category : Precision={res['e2e_term_cat_precision']*100:.2f}%, Recall={res['e2e_term_cat_recall']*100:.2f}%, F1={res['e2e_term_cat_f1']*100:.2f}%")
        print(f"  Category Macro-F1 : {res['category_macro_f1']*100:.2f}%")

    # Export Summary Table
    summary_df = pd.DataFrame(summary_rows)
    summary_csv = os.path.join(args.out_dir, "baseline_b0_summary.csv")
    summary_df.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    # Export Category Breakdown for Test Set
    test_cat_rows = []
    test_res = split_results.get("test", {})
    if "per_category" in test_res:
        for cat, metrics in test_res["per_category"].items():
            test_cat_rows.append({
                "Category": cat,
                "Support": metrics["support"],
                "Precision": f"{metrics['precision'] * 100:.2f}%",
                "Recall": f"{metrics['recall'] * 100:.2f}%",
                "F1 Score": f"{metrics['f1_score'] * 100:.2f}%"
            })
    cat_df = pd.DataFrame(test_cat_rows)
    cat_csv = os.path.join(args.out_dir, "baseline_b0_category_breakdown_test.csv")
    cat_df.to_csv(cat_csv, index=False, encoding="utf-8-sig")

    # Export Full JSON Report
    json_path = os.path.join(args.out_dir, "baseline_b0_metrics.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(split_results, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 70)
    print("BASELINE B0 SUMMARY TABLE (Mục 4.4 Proposal)")
    print("=" * 70)
    print(summary_df.to_string(index=False))

    print("\n" + "=" * 70)
    print("TEST SET PER-CATEGORY BREAKDOWN")
    print("=" * 70)
    print(cat_df.to_string(index=False))

    print(f"\nAll artifacts successfully saved to: {args.out_dir}")


if __name__ == "__main__":
    main()
