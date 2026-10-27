"""
LiemWhisper Annotation Adjudication CLI Runner
==============================================
Runs the automated verification, IAA evaluation, discrepancy extraction,
and Gold Standard Manifest generation:

Usage:
    python research/src/liemwhisper/run_adjudication.py
    python research/src/liemwhisper/run_adjudication.py --adjudicated-file Data/annotator_assignments/disagreements_resolved.csv
"""

import os
import sys
import json
import time
import argparse
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from baselines import TaxonomyManager
from adjudicate_annotations import AnnotationAdjudicationPipeline

# Discover workspace base directory
cand_base = current_dir
while cand_base and not os.path.exists(os.path.join(cand_base, "Data", "glossary_taxonomy_v1.json")):
    parent = os.path.dirname(cand_base)
    if parent == cand_base:
        break
    cand_base = parent

BASE_DIR = cand_base
DATA_DIR = os.path.join(BASE_DIR, "Data")
TAXONOMY_PATH = os.path.join(DATA_DIR, "glossary_taxonomy_v1.json")
ASSIGN_DIR = os.path.join(DATA_DIR, "annotator_assignments")
FILE_A = os.path.join(ASSIGN_DIR, "annotation_batch_annotator_A.csv")
FILE_B = os.path.join(ASSIGN_DIR, "annotation_batch_annotator_B.csv")
DISAGREEMENTS_OUT = os.path.join(ASSIGN_DIR, "disagreements_for_adjudication.csv")
REPORT_JSON = os.path.join(ASSIGN_DIR, "iaa_qc_report.json")
REPORT_MD = os.path.join(ASSIGN_DIR, "iaa_qc_report.md")
GOLD_MANIFEST_OUT = os.path.join(DATA_DIR, "clean_manifest_v1_gold.csv")
MASTER_MANIFEST = os.path.join(DATA_DIR, "clean_manifest_v1.csv")


def parse_args():
    parser = argparse.ArgumentParser(description="LiemWhisper Annotation Adjudication & IAA Runner")
    parser.add_argument("--file-a", type=str, default=FILE_A, help="Path to Annotator A CSV submission")
    parser.add_argument("--file-b", type=str, default=FILE_B, help="Path to Annotator B CSV submission")
    parser.add_argument("--adjudicated-file", type=str, default=None, help="Path to human-resolved disagreements CSV")
    return parser.parse_args()


def main():
    args = parse_args()
    print("=" * 80)
    print("LIEMWHISPER ANNOTATION ADJUDICATION & INTER-ANNOTATOR AGREEMENT (IAA)")
    print("=" * 80)
    print(f"Taxonomy Path        : {TAXONOMY_PATH}")
    print(f"Annotator A File     : {args.file_a}")
    print(f"Annotator B File     : {args.file_b}")

    if not os.path.exists(args.file_a) or not os.path.exists(args.file_b):
        print(f"Error: Annotator files not found at {args.file_a} or {args.file_b}")
        return

    tax = TaxonomyManager(TAXONOMY_PATH)
    pipeline = AnnotationAdjudicationPipeline(tax)

    df_a = pd.read_csv(args.file_a)
    df_b = pd.read_csv(args.file_b)

    print(f"Loaded {len(df_a)} records from Annotator A, {len(df_b)} records from Annotator B.")

    # 1. Run IAA on double annotations
    print("\nEvaluating Inter-Annotator Agreement on double-annotated subset...")
    iaa = pipeline.evaluate_inter_annotator_agreement(df_a, df_b)

    if "error" in iaa:
        print(f"IAA Error: {iaa['error']}")
        return

    print("\n" + "-" * 75)
    print("INTER-ANNOTATOR AGREEMENT SUMMARY:")
    print("-" * 75)
    print(f"  Double-annotated samples evaluated : {iaa['total_double_annotations']}")
    print(f"  Perfect Consensus samples          : {iaa['perfectly_agreed_count']} ({iaa['perfectly_agreed_count']*100/iaa['total_double_annotations']:.1f}%)")
    print(f"  Discrepant samples (Need Review)   : {iaa['disagreement_count']} ({iaa['disagreement_count']*100/iaa['total_double_annotations']:.1f}%)")
    print(f"  Mean Word Agreement (Pairwise)     : {iaa['mean_word_agreement']}%")
    print(f"  Mean Char Agreement (Pairwise)     : {iaa['mean_char_agreement']}%")
    print(f"  Mean Term Jaccard Overlap          : {iaa['mean_term_jaccard']}%")

    k_tax = iaa["cohens_kappa_taxonomy"]
    k_pres = iaa["cohens_kappa_term_presence"]
    print(f"  Cohen's Kappa (Taxonomy Groups)    : κ = {k_tax['kappa']:.4f} ({k_tax['interpretation']})")
    print(f"  Cohen's Kappa (Term Presence)      : κ = {k_pres['kappa']:.4f} ({k_pres['interpretation']})")

    # 2. Export Discrepancy Sheet
    if iaa["disagreements"]:
        pipeline.export_disagreements_sheet(iaa["disagreements"], DISAGREEMENTS_OUT)

    # 3. Export JSON Report
    report_data = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "total_double_annotations": iaa["total_double_annotations"],
        "perfectly_agreed_count": iaa["perfectly_agreed_count"],
        "disagreement_count": iaa["disagreement_count"],
        "mean_word_agreement_pct": iaa["mean_word_agreement"],
        "mean_char_agreement_pct": iaa["mean_char_agreement"],
        "mean_term_jaccard_pct": iaa["mean_term_jaccard"],
        "cohens_kappa_taxonomy": k_tax,
        "cohens_kappa_term_presence": k_pres
    }
    with open(REPORT_JSON, "w", encoding="utf-8") as f:
        json.dump(report_data, f, indent=2, ensure_ascii=False)
    print(f"\nSaved IAA QC Report to: {REPORT_JSON}")

    # 4. Generate Gold Standard Manifest
    adj_df = None
    if args.adjudicated_file and os.path.exists(args.adjudicated_file):
        try:
            adj_df = pd.read_csv(args.adjudicated_file)
            print(f"Loaded {len(adj_df)} resolved adjudications from {args.adjudicated_file}")
        except Exception as e:
            print(f"Note reading adjudicated file: {e}")
    elif os.path.exists(DISAGREEMENTS_OUT) and os.path.getsize(DISAGREEMENTS_OUT) > 50:
        try:
            check_dis = pd.read_csv(DISAGREEMENTS_OUT)
            if "adjudicated_verbatim" in check_dis.columns and check_dis["adjudicated_verbatim"].dropna().count() > 0:
                adj_df = check_dis
                print(f"Found resolved adjudications in {DISAGREEMENTS_OUT}")
        except Exception:
            pass

    gold_df = pipeline.build_gold_manifest(
        df_a, df_b,
        adjudicated_df=adj_df,
        master_manifest_path=MASTER_MANIFEST
    )

    gold_df.to_csv(GOLD_MANIFEST_OUT, index=False, encoding="utf-8-sig")
    print(f"Exported Master Gold Manifest ({len(gold_df)} rows) to: {GOLD_MANIFEST_OUT}")

    print("\nStatus Breakdown in Gold Manifest:")
    print(gold_df["review_status"].value_counts().to_string())
    print("=" * 80)


if __name__ == "__main__":
    main()
