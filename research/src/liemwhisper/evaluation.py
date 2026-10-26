"""
LiemWhisper Evaluation Toolkit (Harness)
========================================
Implements the exact evaluation methodology defined in the LiemWhisper
Research Proposal (Section 4.4 - Experimental Design and Evaluation):

1. Text Normalization:
   - Unicode NFC standard normalization.
   - Case-folding (lower-case).
   - Standardized punctuation stripping while preserving Vietnamese diacritics and English alphanumerics.
   - Whitespace consolidation.

2. ASR Metrics (Corpus-level and Utterance-level):
   - Corpus WER (Total Edit Distance / Total Reference Words, strictly uncapped).
   - Corpus CER (Total Character Edit Distance / Total Reference Characters, uncapped).
   - Utterance-level micro and macro averages with distributions.

3. Terminology Extraction & Classification Metrics:
   - 1-to-1 greedy occurrence matching (prevents duplicate credit).
   - Term Precision, Recall, F1.
   - Primary End-to-End Term-Category F1 (requires BOTH canonical term AND category match).
   - Category-level Macro F1, Micro F1, per-class support and confusion matrix.

4. Safety & Efficiency Metrics:
   - Harmful-Correction Rate (HCR): originally correct spans made incorrect.
   - Correction Success Rate (CSR): originally incorrect spans successfully fixed.
   - Net Accuracy Delta: True fixes minus harmful corruptions.
   - Hallucination Rate in no-term recordings.
   - Graceful handling of empty references and zero-evaluated samples.

5. Statistical Rigor:
   - Speaker-clustered Paired Bootstrap Hypothesis Testing (2,000 resamples).
   - 95% Confidence Intervals (CI) and empirical p-values.
"""

import os
import sys
import re
import json
import unicodedata
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Any, Optional, Union
import numpy as np
import pandas as pd

try:
    from rapidfuzz.distance import Levenshtein as rf_lev
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False

try:
    import jiwer
    HAS_JIWER = True
except ImportError:
    HAS_JIWER = False


# ==============================================================================
# 1. TEXT NORMALIZATION
# ==============================================================================

class TextNormalizer:
    """
    Standardized Text Normalizer for Vietnamese-English Code-Switching ASR.
    Applies Unicode NFC normalization, lower-casing, punctuation stripping,
    and whitespace collapsing.
    """

    # Characters to explicitly remove or treat as whitespace
    PUNCTUATION_PATTERN = re.compile(
        r'[\.,\?!:;\-\—\–_\(\)\[\]\{\}"\'`“”‘’«»…/\\]'
    )

    @classmethod
    def normalize(
        cls,
        text: Optional[str],
        to_lower: bool = True,
        remove_punctuation: bool = True,
        collapse_whitespace: bool = True
    ) -> str:
        """
        Normalizes a string for fair ASR and terminology comparison.
        """
        if text is None or pd.isna(text):
            return ""

        s = str(text)

        # 1. Unicode NFC normalization (ensures precomposed Vietnamese vowels)
        s = unicodedata.normalize("NFC", s)

        # 2. Lowercase
        if to_lower:
            s = s.lower()

        # 3. Punctuation removal
        if remove_punctuation:
            s = cls.PUNCTUATION_PATTERN.sub(" ", s)

        # 4. Collapse consecutive whitespace
        if collapse_whitespace:
            s = " ".join(s.split())

        return s

    @classmethod
    def word_tokenize(cls, text: Optional[str]) -> List[str]:
        """Tokenize normalized text into words."""
        norm_s = cls.normalize(text)
        return norm_s.split() if norm_s else []

    @classmethod
    def char_tokenize(cls, text: Optional[str]) -> List[str]:
        """Tokenize normalized text into characters (excluding spaces)."""
        norm_s = cls.normalize(text)
        return [c for c in norm_s if not c.isspace()]


# ==============================================================================
# 2. LEVENSHTEIN ALIGNMENT & CORPUS-LEVEL WER / CER
# ==============================================================================

def compute_levenshtein_alignment(
    ref_tokens: List[str],
    hyp_tokens: List[str]
) -> Tuple[int, int, int]:
    """
    Computes exact (Substitutions, Deletions, Insertions) using Wagner-Fischer
    dynamic programming with backtrace.
    """
    n, m = len(ref_tokens), len(hyp_tokens)

    # Edge cases
    if n == 0:
        return 0, 0, m  # 0 S, 0 D, m I
    if m == 0:
        return 0, n, 0  # 0 S, n D, 0 I

    # Fast path if strings/tokens are identical
    if ref_tokens == hyp_tokens:
        return 0, 0, 0

    # DP Matrix: dp[i][j] = (cost, S, D, I)
    dp = [[(0, 0, 0, 0)] * (m + 1) for _ in range(n + 1)]

    for i in range(1, n + 1):
        dp[i][0] = (i, 0, i, 0)
    for j in range(1, m + 1):
        dp[0][j] = (j, 0, 0, j)

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref_tokens[i - 1] == hyp_tokens[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                cost_sub, s, d, ins = dp[i - 1][j - 1]
                cost_del, s_d, d_d, ins_d = dp[i - 1][j]
                cost_ins, s_i, d_i, ins_i = dp[i][j - 1]

                cand_sub = (cost_sub + 1, s + 1, d, ins)
                cand_del = (cost_del + 1, s_d, d_d + 1, ins_d)
                cand_ins = (cost_ins + 1, s_i, d_i, ins_i + 1)

                dp[i][j] = min(cand_sub, cand_del, cand_ins, key=lambda x: x[0])

    _, s, d, ins = dp[n][m]
    return s, d, ins


class ASRMetricsCalculator:
    """
    Calculates Corpus-level and Utterance-level WER and CER according to Proposal Section 4.4:
    "Corpus WER and CER will be total edit counts divided by total reference words or characters,
     using a published normalization policy. They will not be capped at 100%."
    """

    @classmethod
    def evaluate_pair(
        cls,
        ref_text: str,
        hyp_text: str
    ) -> Dict[str, Any]:
        """
        Calculates edit counts for a single utterance pair.
        """
        ref_words = TextNormalizer.word_tokenize(ref_text)
        hyp_words = TextNormalizer.word_tokenize(hyp_text)

        s_w, d_w, i_w = compute_levenshtein_alignment(ref_words, hyp_words)
        n_ref_w = len(ref_words)
        edits_w = s_w + d_w + i_w
        wer = (edits_w / n_ref_w) if n_ref_w > 0 else (1.0 if len(hyp_words) > 0 else 0.0)

        ref_chars = TextNormalizer.char_tokenize(ref_text)
        hyp_chars = TextNormalizer.char_tokenize(hyp_text)
        s_c, d_c, i_c = compute_levenshtein_alignment(ref_chars, hyp_chars)
        n_ref_c = len(ref_chars)
        edits_c = s_c + d_c + i_c
        cer = (edits_c / n_ref_c) if n_ref_c > 0 else (1.0 if len(hyp_chars) > 0 else 0.0)

        return {
            "n_ref_words": n_ref_w,
            "n_hyp_words": len(hyp_words),
            "word_substitutions": s_w,
            "word_deletions": d_w,
            "word_insertions": i_w,
            "word_edits": edits_w,
            "utterance_wer": wer,
            "n_ref_chars": n_ref_c,
            "n_hyp_chars": len(hyp_chars),
            "char_substitutions": s_c,
            "char_deletions": d_c,
            "char_insertions": i_c,
            "char_edits": edits_c,
            "utterance_cer": cer,
        }

    @classmethod
    def evaluate_corpus(
        cls,
        references: List[str],
        hypotheses: List[str],
        speaker_ids: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Computes uncapped corpus-level micro WER and CER, macro averages,
        and per-speaker aggregations.
        """
        assert len(references) == len(hypotheses), "References and Hypotheses must have equal length."
        total_samples = len(references)

        if total_samples == 0:
            return {
                "total_utterances": 0,
                "corpus_wer": 0.0,
                "corpus_cer": 0.0,
                "macro_wer": 0.0,
                "macro_cer": 0.0
            }

        total_ref_words = 0
        total_word_sub = 0
        total_word_del = 0
        total_word_ins = 0

        total_ref_chars = 0
        total_char_sub = 0
        total_char_del = 0
        total_char_ins = 0

        utterance_wers = []
        utterance_cers = []
        sample_records = []

        for idx, (ref, hyp) in enumerate(zip(references, hypotheses)):
            res = cls.evaluate_pair(ref, hyp)
            total_ref_words += res["n_ref_words"]
            total_word_sub += res["word_substitutions"]
            total_word_del += res["word_deletions"]
            total_word_ins += res["word_insertions"]

            total_ref_chars += res["n_ref_chars"]
            total_char_sub += res["char_substitutions"]
            total_char_del += res["char_deletions"]
            total_char_ins += res["char_insertions"]

            utterance_wers.append(res["utterance_wer"])
            utterance_cers.append(res["utterance_cer"])

            rec = dict(res)
            rec["index"] = idx
            if speaker_ids is not None and idx < len(speaker_ids):
                rec["speaker_id"] = speaker_ids[idx]
            sample_records.append(rec)

        total_word_edits = total_word_sub + total_word_del + total_word_ins
        total_char_edits = total_char_sub + total_char_del + total_char_ins

        corpus_wer = (total_word_edits / total_ref_words) if total_ref_words > 0 else 0.0
        corpus_cer = (total_char_edits / total_ref_chars) if total_ref_chars > 0 else 0.0

        return {
            "total_utterances": total_samples,
            "total_ref_words": total_ref_words,
            "total_word_substitutions": total_word_sub,
            "total_word_deletions": total_word_del,
            "total_word_insertions": total_word_ins,
            "total_word_edits": total_word_edits,
            "corpus_wer": round(corpus_wer, 6),
            "macro_wer": round(float(np.mean(utterance_wers)), 6),
            "total_ref_chars": total_ref_chars,
            "total_char_substitutions": total_char_sub,
            "total_char_deletions": total_char_del,
            "total_char_insertions": total_char_ins,
            "total_char_edits": total_char_edits,
            "corpus_cer": round(corpus_cer, 6),
            "macro_cer": round(float(np.mean(utterance_cers)), 6),
            "sample_records": sample_records
        }


# ==============================================================================
# 3. TERMINOLOGY EXTRACTION & END-TO-END CLASSIFICATION METRICS
# ==============================================================================

class TerminologyOccurrence:
    """Represents a single canonical term occurrence with its taxonomy category."""
    def __init__(self, term: str, category: str = "Unassigned"):
        self.term = TextNormalizer.normalize(term)
        self.category = category.strip()

    def __repr__(self):
        return f"Term({self.term} -> {self.category})"

    def matches_term(self, other: "TerminologyOccurrence") -> bool:
        return self.term == other.term

    def matches_end_to_end(self, other: "TerminologyOccurrence") -> bool:
        return (self.term == other.term) and (self.category.lower() == other.category.lower())


class TerminologyEvaluator:
    """
    Evaluates Occurrence-Level Term Precision, Recall, F1 and End-to-End F1.
    Proposal Section 4.4:
    "One-to-one matching within each recording will prevent duplicate predictions receiving
     extra credit; spurious predictions and missed terms will count as errors. Primary end-to-end
     F1 will count a prediction as correct only when both term and category match a reference occurrence."
    """

    @classmethod
    def parse_term_list(cls, terms_raw: Any, default_cat: str = "Unassigned") -> List[TerminologyOccurrence]:
        """Parses various formats (list of dicts, JSON string, list of strings, semicolon-delimited)."""
        if terms_raw is None or pd.isna(terms_raw):
            return []

        if isinstance(terms_raw, str):
            s = terms_raw.strip()
            if not s or s == "[]":
                return []
            if s.startswith("[") and s.endswith("]"):
                try:
                    parsed = json.loads(s)
                    return cls.parse_term_list(parsed, default_cat)
                except Exception:
                    pass
            # Semicolon or comma delimited string
            parts = [p.strip() for p in re.split(r"[;,]", s) if p.strip()]
            return [TerminologyOccurrence(p, default_cat) for p in parts]

        if isinstance(terms_raw, list):
            occurrences = []
            for item in terms_raw:
                if isinstance(item, dict):
                    t = item.get("term") or item.get("canonical_term") or ""
                    c = item.get("category") or item.get("primary_category") or default_cat
                    if t:
                        occurrences.append(TerminologyOccurrence(t, c))
                elif isinstance(item, str) and item.strip():
                    occurrences.append(TerminologyOccurrence(item, default_cat))
            return occurrences

        return []

    @classmethod
    def match_utterance_occurrences(
        cls,
        gold_terms: List[TerminologyOccurrence],
        pred_terms: List[TerminologyOccurrence]
    ) -> Dict[str, Any]:
        """
        Executes strict 1-to-1 greedy matching within an utterance.
        Computes TP, FP, FN for:
        1. Term Recognition (Term Only)
        2. End-to-End Recognition + Category Classification (Term + Category)
        """
        # Term-only matching
        unmatched_gold = list(gold_terms)
        unmatched_pred = list(pred_terms)

        term_tp = 0
        matched_gold_indices = set()
        matched_pred_indices = set()

        for p_idx, p in enumerate(pred_terms):
            for g_idx, g in enumerate(gold_terms):
                if g_idx not in matched_gold_indices and p.matches_term(g):
                    term_tp += 1
                    matched_gold_indices.add(g_idx)
                    matched_pred_indices.add(p_idx)
                    break

        term_fp = len(pred_terms) - term_tp
        term_fn = len(gold_terms) - term_tp

        # End-to-End (Term + Category) matching
        e2e_tp = 0
        matched_e2e_gold = set()
        matched_e2e_pred = set()

        # Detailed matches for category analysis
        category_matches = []

        for p_idx, p in enumerate(pred_terms):
            for g_idx, g in enumerate(gold_terms):
                if g_idx not in matched_e2e_gold and p.matches_end_to_end(g):
                    e2e_tp += 1
                    matched_e2e_gold.add(g_idx)
                    matched_e2e_pred.add(p_idx)
                    category_matches.append({
                        "term": p.term,
                        "gold_category": g.category,
                        "pred_category": p.category,
                        "status": "CORRECT"
                    })
                    break

        # Record category confusions on term-matched but category-mismatched
        for p_idx in matched_pred_indices:
            if p_idx not in matched_e2e_pred:
                # Find corresponding gold term that matched lexically
                p = pred_terms[p_idx]
                for g_idx in matched_gold_indices:
                    g = gold_terms[g_idx]
                    if p.matches_term(g):
                        category_matches.append({
                            "term": p.term,
                            "gold_category": g.category,
                            "pred_category": p.category,
                            "status": "CATEGORY_MISMATCH"
                        })
                        break

        e2e_fp = len(pred_terms) - e2e_tp
        e2e_fn = len(gold_terms) - e2e_tp

        return {
            "gold_count": len(gold_terms),
            "pred_count": len(pred_terms),
            "term_tp": term_tp,
            "term_fp": term_fp,
            "term_fn": term_fn,
            "e2e_tp": e2e_tp,
            "e2e_fp": e2e_fp,
            "e2e_fn": e2e_fn,
            "category_matches": category_matches
        }

    @classmethod
    def evaluate_corpus(
        cls,
        gold_occurrences_list: List[List[TerminologyOccurrence]],
        pred_occurrences_list: List[List[TerminologyOccurrence]],
        taxonomy_categories: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Computes Corpus-level Term F1, End-to-End Term-Category F1,
        Category-level Macro F1, and per-class support.
        """
        assert len(gold_occurrences_list) == len(pred_occurrences_list)
        total_samples = len(gold_occurrences_list)

        total_gold_terms = 0
        total_pred_terms = 0

        total_term_tp = 0
        total_term_fp = 0
        total_term_fn = 0

        total_e2e_tp = 0
        total_e2e_fp = 0
        total_e2e_fn = 0

        per_category_stats = defaultdict(lambda: {"tp": 0, "fp": 0, "fn": 0, "support": 0})
        all_category_matches = []

        for gold, pred in zip(gold_occurrences_list, pred_occurrences_list):
            res = cls.match_utterance_occurrences(gold, pred)
            total_gold_terms += res["gold_count"]
            total_pred_terms += res["pred_count"]

            total_term_tp += res["term_tp"]
            total_term_fp += res["term_fp"]
            total_term_fn += res["term_fn"]

            total_e2e_tp += res["e2e_tp"]
            total_e2e_fp += res["e2e_fp"]
            total_e2e_fn += res["e2e_fn"]

            all_category_matches.extend(res["category_matches"])

            # Accumulate per-category statistics
            for g in gold:
                per_category_stats[g.category]["support"] += 1

            for match in res["category_matches"]:
                if match["status"] == "CORRECT":
                    per_category_stats[match["gold_category"]]["tp"] += 1
                elif match["status"] == "CATEGORY_MISMATCH":
                    per_category_stats[match["pred_category"]]["fp"] += 1
                    per_category_stats[match["gold_category"]]["fn"] += 1

        # Calculate Precision, Recall, F1
        def calc_prf(tp: int, fp: int, fn: int) -> Tuple[float, float, float]:
            prec = (tp / (tp + fp)) if (tp + fp) > 0 else 0.0
            rec = (tp / (tp + fn)) if (tp + fn) > 0 else 0.0
            f1 = (2 * prec * rec / (prec + rec)) if (prec + rec) > 0 else 0.0
            return round(prec, 6), round(rec, 6), round(f1, 6)

        term_p, term_r, term_f1 = calc_prf(total_term_tp, total_term_fp, total_term_fn)
        e2e_p, e2e_r, e2e_f1 = calc_prf(total_e2e_tp, total_e2e_fp, total_e2e_fn)

        # Per-category report
        cat_report = {}
        macro_f1_list = []
        target_cats = taxonomy_categories or sorted(list(per_category_stats.keys()))

        for cat in target_cats:
            st = per_category_stats[cat]
            cp, cr, cf1 = calc_prf(st["tp"], st["fp"], st["fn"])
            cat_report[cat] = {
                "support": st["support"],
                "precision": cp,
                "recall": cr,
                "f1_score": cf1
            }
            if st["support"] > 0:
                macro_f1_list.append(cf1)

        category_macro_f1 = round(float(np.mean(macro_f1_list)), 6) if macro_f1_list else 0.0

        return {
            "total_samples": total_samples,
            "total_gold_terms": total_gold_terms,
            "total_pred_terms": total_pred_terms,
            "term_recognition": {
                "tp": total_term_tp,
                "fp": total_term_fp,
                "fn": total_term_fn,
                "precision": term_p,
                "recall": term_r,
                "f1_score": term_f1
            },
            "end_to_end_classification": {
                "tp": total_e2e_tp,
                "fp": total_e2e_fp,
                "fn": total_e2e_fn,
                "precision": e2e_p,
                "recall": e2e_r,
                "f1_score": e2e_f1,
                "category_macro_f1": category_macro_f1,
                "per_category": cat_report
            }
        }


# ==============================================================================
# 4. SAFETY & EFFICIENCY METRICS (Harmful-Correction Rate)
# ==============================================================================

class SafetyMetricsEvaluator:
    """
    Evaluates safety against over-biasing and harmful corrections.
    Proposal Section 4.4:
    "Harmful-correction rate will be the number of originally correct evaluated spans made
     incorrect divided by the number of originally correct evaluated spans. Correction success
     will be measured over originally incorrect spans. Term hallucinations in no-term recordings..."
    """

    @classmethod
    def evaluate_comparative_safety(
        cls,
        gold_terms_list: List[List[TerminologyOccurrence]],
        baseline_preds: List[List[TerminologyOccurrence]],
        candidate_preds: List[List[TerminologyOccurrence]]
    ) -> Dict[str, Any]:
        """
        Compares candidate system against baseline system to compute:
        - Harmful-Correction Rate (HCR)
        - Correction Success Rate (CSR)
        - Net Gain (Fixed - Broken)
        - Hallucinations in No-Term recordings
        """
        assert len(gold_terms_list) == len(baseline_preds) == len(candidate_preds)
        n = len(gold_terms_list)

        # Overall cohort counters
        originally_correct_count = 0
        originally_incorrect_count = 0
        harmful_corruptions = 0
        successful_corrections = 0
        unchanged_correct = 0
        unchanged_incorrect = 0

        # Term-bearing specific counters (span-level)
        tb_correct_count = 0
        tb_incorrect_count = 0
        tb_harmful_corruptions = 0
        tb_successful_corrections = 0

        no_term_utterances = 0
        baseline_hallucinations = 0
        candidate_hallucinations = 0

        sample_safety_log = []

        for idx in range(n):
            gold = gold_terms_list[idx]
            base = baseline_preds[idx]
            cand = candidate_preds[idx]

            base_eval = TerminologyEvaluator.match_utterance_occurrences(gold, base)
            cand_eval = TerminologyEvaluator.match_utterance_occurrences(gold, cand)

            # Utterance is considered "correct" if all gold terms are recognized with zero FP
            base_correct = (base_eval["term_fn"] == 0 and base_eval["term_fp"] == 0)
            cand_correct = (cand_eval["term_fn"] == 0 and cand_eval["term_fp"] == 0)

            is_term_bearing = len(gold) > 0

            if not is_term_bearing:
                no_term_utterances += 1
                if len(base) > 0:
                    baseline_hallucinations += len(base)
                if len(cand) > 0:
                    candidate_hallucinations += len(cand)

            if base_correct:
                originally_correct_count += 1
                if is_term_bearing:
                    tb_correct_count += 1

                if not cand_correct:
                    harmful_corruptions += 1
                    if is_term_bearing:
                        tb_harmful_corruptions += 1
                    status = "HARMFUL_CORRUPTION"
                else:
                    unchanged_correct += 1
                    status = "PRESERVED_CORRECT"
            else:
                originally_incorrect_count += 1
                if is_term_bearing:
                    tb_incorrect_count += 1

                if cand_correct:
                    successful_corrections += 1
                    if is_term_bearing:
                        tb_successful_corrections += 1
                    status = "SUCCESSFUL_CORRECTION"
                else:
                    unchanged_incorrect += 1
                    status = "PERSISTENT_ERROR"

            sample_safety_log.append({
                "sample_idx": idx,
                "is_term_bearing": is_term_bearing,
                "gold_terms": [t.term for t in gold],
                "base_terms": [t.term for t in base],
                "cand_terms": [t.term for t in cand],
                "base_correct": base_correct,
                "cand_correct": cand_correct,
                "safety_status": status
            })

        overall_hcr = (harmful_corruptions / originally_correct_count) if originally_correct_count > 0 else 0.0
        overall_csr = (successful_corrections / originally_incorrect_count) if originally_incorrect_count > 0 else 0.0

        tb_hcr = (tb_harmful_corruptions / tb_correct_count) if tb_correct_count > 0 else 0.0
        tb_csr = (tb_successful_corrections / tb_incorrect_count) if tb_incorrect_count > 0 else 0.0

        net_gain = successful_corrections - harmful_corruptions
        tb_net_gain = tb_successful_corrections - tb_harmful_corruptions

        hallucination_rate = (candidate_hallucinations / no_term_utterances) if no_term_utterances > 0 else 0.0

        return {
            "total_evaluated_utterances": n,
            "overall_originally_correct": originally_correct_count,
            "overall_originally_incorrect": originally_incorrect_count,
            "overall_harmful_corruptions": harmful_corruptions,
            "overall_successful_corrections": successful_corrections,
            "overall_harmful_correction_rate": round(overall_hcr, 6),
            "overall_correction_success_rate": round(overall_csr, 6),
            "overall_net_gain": net_gain,
            "term_bearing_samples": n - no_term_utterances,
            "term_bearing_originally_correct": tb_correct_count,
            "term_bearing_originally_incorrect": tb_incorrect_count,
            "term_bearing_harmful_corruptions": tb_harmful_corruptions,
            "term_bearing_successful_corrections": tb_successful_corrections,
            "term_bearing_harmful_correction_rate": round(tb_hcr, 6),
            "term_bearing_correction_success_rate": round(tb_csr, 6),
            "term_bearing_net_gain": tb_net_gain,
            "no_term_utterance_count": no_term_utterances,
            "baseline_hallucination_count": baseline_hallucinations,
            "candidate_hallucination_count": candidate_hallucinations,
            "no_term_hallucination_rate": round(hallucination_rate, 6),
            "sample_safety_log": sample_safety_log
        }


# ==============================================================================
# 5. PAIRED BOOTSTRAP HYPOTHESIS TESTING (Speaker-Clustered)
# ==============================================================================

class PairedBootstrapTester:
    """
    Computes Paired Bootstrap Confidence Intervals and empirical p-values
    using speaker-clustered resampling (Proposal Section 4.4:
    "Paired bootstrap intervals will resample speakers, preserving their recordings,
     with 2,000 resamples planned.")
    """

    @classmethod
    def test_wer_difference(
        cls,
        df: pd.DataFrame,
        ref_col: str,
        base_hyp_col: str,
        cand_hyp_col: str,
        speaker_col: str = "speaker_id",
        n_resamples: int = 2000,
        random_seed: int = 42
    ) -> Dict[str, Any]:
        """
        Resamples speakers with replacement, evaluating the Delta WER (Base - Candidate).
        Delta > 0 indicates Candidate improved over Baseline.
        """
        rng = np.random.RandomState(random_seed)
        unique_speakers = df[speaker_col].unique()
        n_speakers = len(unique_speakers)

        if n_speakers < 2:
            return {"error": "Need at least 2 distinct speakers for clustered bootstrap."}

        # Pre-group indices by speaker for high performance
        speaker_to_indices = {s: df.index[df[speaker_col] == s].tolist() for s in unique_speakers}

        # Pre-compute edit stats for base and cand per row
        ref_texts = df[ref_col].tolist()
        base_hyps = df[base_hyp_col].tolist()
        cand_hyps = df[cand_hyp_col].tolist()

        row_stats = []
        for r, b, c in zip(ref_texts, base_hyps, cand_hyps):
            b_eval = ASRMetricsCalculator.evaluate_pair(r, b)
            c_eval = ASRMetricsCalculator.evaluate_pair(r, c)
            row_stats.append((
                b_eval["n_ref_words"],
                b_eval["word_edits"],
                c_eval["word_edits"]
            ))

        # Overall observed WER
        total_ref_w = sum(s[0] for s in row_stats)
        obs_base_wer = sum(s[1] for s in row_stats) / total_ref_w if total_ref_w > 0 else 0.0
        obs_cand_wer = sum(s[2] for s in row_stats) / total_ref_w if total_ref_w > 0 else 0.0
        obs_diff = obs_base_wer - obs_cand_wer  # Positive = Candidate is better

        # Bootstrap loop
        diff_samples = []
        for _ in range(n_resamples):
            boot_speakers = rng.choice(unique_speakers, size=n_speakers, replace=True)
            boot_ref = 0
            boot_base_ed = 0
            boot_cand_ed = 0

            for spk in boot_speakers:
                for idx in speaker_to_indices[spk]:
                    ref_w, b_ed, c_ed = row_stats[idx]
                    boot_ref += ref_w
                    boot_base_ed += b_ed
                    boot_cand_ed += c_ed

            if boot_ref > 0:
                b_wer = boot_base_ed / boot_ref
                c_wer = boot_cand_ed / boot_ref
                diff_samples.append(b_wer - c_wer)

        diffs = np.array(diff_samples)
        ci_lower = float(np.percentile(diffs, 2.5))
        ci_upper = float(np.percentile(diffs, 97.5))

        # Empirical p-value (proportion of resamples where cand is worse than or equal to baseline)
        p_value = float(np.mean(diffs <= 0.0))

        return {
            "n_resamples": n_resamples,
            "n_clusters_speakers": n_speakers,
            "baseline_wer": round(obs_base_wer, 6),
            "candidate_wer": round(obs_cand_wer, 6),
            "observed_wer_reduction": round(obs_diff, 6),
            "ci_95_lower": round(ci_lower, 6),
            "ci_95_upper": round(ci_upper, 6),
            "is_significant_95": bool(ci_lower > 0.0),
            "empirical_p_value": round(p_value, 4)
        }


# ==============================================================================
# 6. UNIFIED BENCHMARK HARNESS RUNNER
# ==============================================================================

class LiemWhisperBenchmarkHarness:
    """
    Unified CLI and program interface to run full evaluation suites.
    """

    def __init__(self, taxonomy_path: str):
        self.taxonomy_path = taxonomy_path
        self.taxonomy = self._load_taxonomy()
        self.categories = list(self.taxonomy.get("categories", {}).keys())

    def _load_taxonomy(self) -> Dict[str, Any]:
        if os.path.exists(self.taxonomy_path):
            with open(self.taxonomy_path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"categories": {}}

    def evaluate_manifest(
        self,
        manifest_df: pd.DataFrame,
        ref_text_col: str = "verbatim_transcript",
        hyp_text_col: str = "asr_transcript",
        gold_terms_col: str = "target_terms_hint",
        pred_terms_col: str = "b0_exact_matches",
        split_filter: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Runs complete benchmark evaluation over a manifest subset.
        """
        eval_df = manifest_df.copy()
        if split_filter:
            eval_df = eval_df[eval_df["split"] == split_filter].copy()

        eval_df = eval_df.reset_index(drop=True)
        total_eval = len(eval_df)

        if total_eval == 0:
            return {"error": f"No samples found for split: {split_filter}"}

        refs = eval_df[ref_text_col].fillna("").astype(str).tolist()
        hyps = eval_df[hyp_text_col].fillna("").astype(str).tolist()
        spk_ids = eval_df["speaker_id"].astype(str).tolist() if "speaker_id" in eval_df.columns else None

        # 1. ASR Metrics
        asr_res = ASRMetricsCalculator.evaluate_corpus(refs, hyps, spk_ids)

        # 2. Terminology occurrences
        gold_occurrences = []
        pred_occurrences = []

        for _, row in eval_df.iterrows():
            cat = str(row.get("primary_category_hint", "Unassigned"))
            g_raw = row.get(gold_terms_col, "")
            p_raw = row.get(pred_terms_col, "")

            gold_occurrences.append(TerminologyEvaluator.parse_term_list(g_raw, cat))
            pred_occurrences.append(TerminologyEvaluator.parse_term_list(p_raw, cat))

        term_res = TerminologyEvaluator.evaluate_corpus(
            gold_occurrences,
            pred_occurrences,
            taxonomy_categories=self.categories
        )

        return {
            "evaluation_split": split_filter or "all",
            "sample_count": total_eval,
            "asr_metrics": {
                "corpus_wer": asr_res["corpus_wer"],
                "corpus_cer": asr_res["corpus_cer"],
                "macro_wer": asr_res["macro_wer"],
                "macro_cer": asr_res["macro_cer"],
                "total_ref_words": asr_res["total_ref_words"],
                "total_word_edits": asr_res["total_word_edits"]
            },
            "terminology_metrics": term_res
        }
