"""
LiemWhisper Annotation Adjudication & Inter-Annotator Agreement Engine
======================================================================
Implements Proposal Section 4.1 requirements:
- Ingests Batch A and Batch B human annotations
- Computes Inter-Annotator Agreement (IAA) on double-annotated overlap recordings:
  * Cohen's Kappa for categorical agreement (Taxonomy & Term presence)
  * Pairwise Word Agreement & Character Agreement (Transcriber WER/CER)
  * Term-span Jaccard agreement
- Exports Discrepancy Sheet (disagreements_for_adjudication.csv) for fast human review
- Merges agreed & adjudicated records into the official Gold Standard Manifest (clean_manifest_v1_gold.csv)
- Exports formal IAA & QC Report (iaa_qc_report.json & Markdown summary)
"""

import os
import sys
import re
import json
import time
from dataclasses import dataclass
from typing import List, Dict, Tuple, Any, Optional, Set
import numpy as np
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

try:
    from .evaluation import TextNormalizer, TerminologyOccurrence
    from .baselines import TaxonomyManager
except (ImportError, ValueError):
    from evaluation import TextNormalizer, TerminologyOccurrence
    from baselines import TaxonomyManager


# ==============================================================================
# 1. MATHEMATICAL AGREEMENT METRICS (COHEN'S KAPPA & LEVENSHTEIN)
# ==============================================================================

def compute_levenshtein_distance(seq1: List[Any], seq2: List[Any]) -> int:
    """Computes exact edit distance between two token/character sequences."""
    n, m = len(seq1), len(seq2)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if seq1[i - 1] == seq2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[n][m]


def compute_pairwise_agreement(text1: str, text2: str) -> Dict[str, float]:
    """
    Computes Word Agreement (1 - WER) and Character Agreement (1 - CER)
    between two human transcriber strings.
    """
    norm1 = TextNormalizer.normalize(text1)
    norm2 = TextNormalizer.normalize(text2)

    words1 = TextNormalizer.word_tokenize(norm1)
    words2 = TextNormalizer.word_tokenize(norm2)

    chars1 = list(norm1.replace(" ", ""))
    chars2 = list(norm2.replace(" ", ""))

    w_dist = compute_levenshtein_distance(words1, words2)
    c_dist = compute_levenshtein_distance(chars1, chars2)

    w_len = max(len(words1), len(words2))
    c_len = max(len(chars1), len(chars2))

    word_agreement = 1.0 - (w_dist / w_len) if w_len > 0 else 1.0
    char_agreement = 1.0 - (c_dist / c_len) if c_len > 0 else 1.0

    return {
        "word_distance": w_dist,
        "word_max_len": w_len,
        "word_agreement": max(0.0, word_agreement),
        "char_distance": c_dist,
        "char_max_len": c_len,
        "char_agreement": max(0.0, char_agreement)
    }


def compute_cohens_kappa(rater1: List[str], rater2: List[str]) -> Dict[str, Any]:
    """
    Computes Cohen's Kappa coefficient (kappa) for categorical decisions.
    Handles multi-class categories (ISTQB taxonomy groups + No-Term).
    Returns kappa score, observed agreement Po, expected agreement Pe, and interpretation.
    """
    if len(rater1) != len(rater2) or len(rater1) == 0:
        return {"kappa": 0.0, "po": 0.0, "pe": 0.0, "interpretation": "Invalid Input"}

    categories = sorted(list(set(rater1).union(set(rater2))))
    if len(categories) <= 1:
        return {"kappa": 1.0, "po": 1.0, "pe": 1.0, "interpretation": "Perfect Agreement"}

    cat_to_idx = {c: i for i, c in enumerate(categories)}
    n_cat = len(categories)
    cm = np.zeros((n_cat, n_cat), dtype=int)

    for r1, r2 in zip(rater1, rater2):
        cm[cat_to_idx[r1]][cat_to_idx[r2]] += 1

    n = len(rater1)
    po = np.trace(cm) / n
    row_sums = cm.sum(axis=1) / n
    col_sums = cm.sum(axis=0) / n
    pe = np.sum(row_sums * col_sums)

    if pe >= 1.0:
        kappa = 1.0
    else:
        kappa = (po - pe) / (1.0 - pe)

    kappa = max(-1.0, min(1.0, float(kappa)))

    # Landis & Koch (1977) interpretation
    if kappa > 0.80:
        interp = "Almost Perfect Agreement"
    elif kappa > 0.60:
        interp = "Substantial Agreement"
    elif kappa > 0.40:
        interp = "Moderate Agreement"
    elif kappa > 0.20:
        interp = "Fair Agreement"
    elif kappa > 0.00:
        interp = "Slight Agreement"
    else:
        interp = "Poor / Chance Agreement"

    return {
        "kappa": round(kappa, 4),
        "observed_agreement_po": round(float(po), 4),
        "expected_agreement_pe": round(float(pe), 4),
        "interpretation": interp,
        "sample_count": n,
        "category_count": n_cat,
        "categories": categories
    }


# ==============================================================================
# 2. ADJUDICATION PIPELINE & DISCREPANCY DETECTOR
# ==============================================================================

class AnnotationAdjudicationPipeline:
    """
    Complete workflow engine to audit, compare, adjudicate, and merge
    human annotator submissions into the official Gold Standard Manifest.
    """

    def __init__(self, taxonomy: TaxonomyManager):
        self.taxonomy = taxonomy

    def parse_annotator_terms(self, raw_terms: Any) -> List[str]:
        """Parses annotator_identified_terms from JSON string or list or semicolon string."""
        if not raw_terms or pd.isna(raw_terms):
            return []

        if isinstance(raw_terms, list):
            return [TextNormalizer.normalize(str(t)) for t in raw_terms if t]

        s = str(raw_terms).strip()
        if not s or s == "[]":
            return []

        # Try JSON
        if s.startswith("[") and s.endswith("]"):
            try:
                items = json.loads(s)
                res = []
                for item in items:
                    if isinstance(item, dict) and "term" in item:
                        res.append(TextNormalizer.normalize(item["term"]))
                    elif isinstance(item, str):
                        res.append(TextNormalizer.normalize(item))
                return res
            except Exception:
                pass

        # Semicolon separated fallback
        parts = [p.strip() for p in s.split(";") if p.strip()]
        return [TextNormalizer.normalize(p) for p in parts]

    def evaluate_inter_annotator_agreement(
        self,
        df_a: pd.DataFrame,
        df_b: pd.DataFrame
    ) -> Dict[str, Any]:
        """
        Computes full IAA metrics across the double-annotated subset:
        - Word Agreement
        - Character Agreement
        - Category Cohen's Kappa
        - Binary Term-Presence Kappa
        - Discrepancy counts
        """
        # Find intersection
        common_ids = sorted(list(
            set(df_a[df_a["is_double_annotation_candidate"] == True]["recording_id"]).intersection(
                set(df_b[df_b["is_double_annotation_candidate"] == True]["recording_id"])
            )
        ))

        if not common_ids:
            return {"error": "No common double-annotation recording_id found"}

        sub_a = df_a[df_a["recording_id"].isin(common_ids)].set_index("recording_id")
        sub_b = df_b[df_b["recording_id"].isin(common_ids)].set_index("recording_id")

        word_agreements = []
        char_agreements = []
        term_jaccards = []
        cat_rater_a = []
        cat_rater_b = []
        presence_rater_a = []
        presence_rater_b = []

        disagreements = []
        agreed_count = 0

        for rec_id in common_ids:
            row_a = sub_a.loc[rec_id]
            row_b = sub_b.loc[rec_id]

            t_a = str(row_a.get("verbatim_transcript", "")).strip()
            t_b = str(row_b.get("verbatim_transcript", "")).strip()

            pw = compute_pairwise_agreement(t_a, t_b)
            word_agreements.append(pw["word_agreement"])
            char_agreements.append(pw["char_agreement"])

            terms_a = self.parse_annotator_terms(row_a.get("annotator_identified_terms", "[]"))
            terms_b = self.parse_annotator_terms(row_b.get("annotator_identified_terms", "[]"))

            # Term Jaccard
            set_a = set(terms_a)
            set_b = set(terms_b)
            union = set_a | set_b
            inter = set_a & set_b
            jaccard = len(inter) / len(union) if union else 1.0
            term_jaccards.append(jaccard)

            # Categorical labels (primary category of first term, or No-Term)
            cat_a = self.taxonomy.get_category(terms_a[0]) if terms_a else "No_Term"
            cat_b = self.taxonomy.get_category(terms_b[0]) if terms_b else "No_Term"
            cat_rater_a.append(cat_a)
            cat_rater_b.append(cat_b)

            pres_a = "Has_Term" if len(terms_a) > 0 else "No_Term"
            pres_b = "Has_Term" if len(terms_b) > 0 else "No_Term"
            presence_rater_a.append(pres_a)
            presence_rater_b.append(pres_b)

            # Check if discrepancy exists
            # Disagreement defined as: term sets differ OR word agreement < 85%
            has_term_mismatch = (set_a != set_b)
            has_large_text_divergence = (pw["word_agreement"] < 0.85)

            if has_term_mismatch or has_large_text_divergence:
                disagreements.append({
                    "recording_id": rec_id,
                    "speaker_id": row_a.get("speaker_id", ""),
                    "wav_file": row_a.get("wav_file", ""),
                    "prompt_id": row_a.get("prompt_id", ""),
                    "prompt_text": row_a.get("prompt_text", ""),
                    "word_agreement_pct": round(pw["word_agreement"] * 100, 2),
                    "transcript_A": t_a,
                    "terms_A": "; ".join(terms_a),
                    "category_A": cat_a,
                    "transcript_B": t_b,
                    "terms_B": "; ".join(terms_b),
                    "category_B": cat_b,
                    "adjudicated_verbatim": "",
                    "adjudicated_terms": "",
                    "adjudicated_category": "",
                    "adjudication_status": "NEEDS_ADJUDICATION",
                    "adjudicator_notes": ""
                })
            else:
                agreed_count += 1

        kappa_cat = compute_cohens_kappa(cat_rater_a, cat_rater_b)
        kappa_presence = compute_cohens_kappa(presence_rater_a, presence_rater_b)

        return {
            "total_double_annotations": len(common_ids),
            "perfectly_agreed_count": agreed_count,
            "disagreement_count": len(disagreements),
            "mean_word_agreement": round(float(np.mean(word_agreements)) * 100, 2),
            "mean_char_agreement": round(float(np.mean(char_agreements)) * 100, 2),
            "mean_term_jaccard": round(float(np.mean(term_jaccards)) * 100, 2),
            "cohens_kappa_taxonomy": kappa_cat,
            "cohens_kappa_term_presence": kappa_presence,
            "disagreements": disagreements
        }

    def export_disagreements_sheet(
        self,
        disagreements: List[Dict[str, Any]],
        out_csv_path: str
    ):
        """Exports disagreeing samples to a review sheet for human adjudication."""
        os.makedirs(os.path.dirname(os.path.abspath(out_csv_path)), exist_ok=True)
        df_dis = pd.DataFrame(disagreements)
        df_dis.to_csv(out_csv_path, index=False, encoding="utf-8-sig")
        print(f"[Adjudication] Exported {len(disagreements)} disagreements for adjudication to: {out_csv_path}")

    def build_gold_manifest(
        self,
        df_a: pd.DataFrame,
        df_b: pd.DataFrame,
        adjudicated_df: Optional[pd.DataFrame] = None,
        master_manifest_path: Optional[str] = None
    ) -> pd.DataFrame:
        """
        Merges single-annotator partitions + agreed double-annotations + resolved adjudications
        into the definitive clean_manifest_v1_gold.csv.
        """
        # Build dictionary of adjudicated resolutions
        adj_map = {}
        if adjudicated_df is not None and not adjudicated_df.empty:
            for _, r in adjudicated_df.iterrows():
                rec_id = r["recording_id"]
                adj_map[rec_id] = {
                    "verbatim": str(r.get("adjudicated_verbatim", "")).strip(),
                    "terms": str(r.get("adjudicated_terms", "")).strip(),
                    "category": str(r.get("adjudicated_category", "")).strip()
                }

        # Index A and B
        dict_a = df_a.set_index("recording_id").to_dict(orient="index")
        dict_b = df_b.set_index("recording_id").to_dict(orient="index")
        all_ids = sorted(list(set(dict_a.keys()).union(set(dict_b.keys()))))

        master_df = None
        if master_manifest_path and os.path.exists(master_manifest_path):
            master_df = pd.read_csv(master_manifest_path).set_index("recording_id")

        gold_records = []

        for rec_id in all_ids:
            in_a = rec_id in dict_a
            in_b = rec_id in dict_b

            # Base metadata
            row_meta = dict_a[rec_id] if in_a else dict_b[rec_id]
            split = row_meta.get("split", "train")
            if master_df is not None and rec_id in master_df.index:
                split = master_df.loc[rec_id].get("split", split)

            # Resolution logic
            if rec_id in adj_map and adj_map[rec_id]["verbatim"]:
                # 1. Manually adjudicated
                final_verb = adj_map[rec_id]["verbatim"]
                final_terms = adj_map[rec_id]["terms"]
                status = "adjudicated"
            elif in_a and in_b:
                # 2. Double annotation: Check consensus
                row_a = dict_a[rec_id]
                row_b = dict_b[rec_id]
                t_a = str(row_a.get("verbatim_transcript", "")).strip()
                t_b = str(row_b.get("verbatim_transcript", "")).strip()
                terms_a = self.parse_annotator_terms(row_a.get("annotator_identified_terms", "[]"))
                terms_b = self.parse_annotator_terms(row_b.get("annotator_identified_terms", "[]"))

                if t_a == t_b or set(terms_a) == set(terms_b):
                    final_verb = t_a if t_a else t_b
                    final_terms = "; ".join(terms_a if terms_a else terms_b)
                    status = "verified_consensus"
                else:
                    # Prefer longer transcript as fallback if not adjudicated yet
                    final_verb = t_a if len(t_a) >= len(t_b) else t_b
                    final_terms = "; ".join(terms_a if len(terms_a) >= len(terms_b) else terms_b)
                    status = "double_annotation_pending_review"
            elif in_a:
                # 3. Single annotation A
                final_verb = str(dict_a[rec_id].get("verbatim_transcript", "")).strip()
                terms_a = self.parse_annotator_terms(dict_a[rec_id].get("annotator_identified_terms", "[]"))
                final_terms = "; ".join(terms_a)
                status = "single_annotated_A"
            else:
                # 4. Single annotation B
                final_verb = str(dict_b[rec_id].get("verbatim_transcript", "")).strip()
                terms_b = self.parse_annotator_terms(dict_b[rec_id].get("annotator_identified_terms", "[]"))
                final_terms = "; ".join(terms_b)
                status = "single_annotated_B"

            # Derive categories
            cat_list = []
            for t in [x.strip() for x in final_terms.split(";") if x.strip()]:
                cat_list.append(self.taxonomy.get_category(t))
            final_categories = "; ".join(cat_list)

            gold_records.append({
                "recording_id": rec_id,
                "speaker_id": row_meta.get("speaker_id", ""),
                "speaker_name": row_meta.get("speaker_name", ""),
                "wav_file": row_meta.get("wav_file", ""),
                "prompt_id": row_meta.get("prompt_id", ""),
                "prompt_text": row_meta.get("prompt_text", ""),
                "verbatim_transcript": final_verb,
                "gold_terms": final_terms,
                "gold_categories": final_categories,
                "split": split,
                "review_status": status,
                "quality_flag": row_meta.get("audio_quality_flag", "normal"),
                "duration_seconds": row_meta.get("duration_seconds", 0.0)
            })

        return pd.DataFrame(gold_records)
