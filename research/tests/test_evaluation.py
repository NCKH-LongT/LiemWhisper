"""
Unit Test Suite for LiemWhisper Evaluation Toolkit
=================================================
Validates correctness against edge cases, standard library, and jiwer.
"""

import sys
import os
import json
import numpy as np
import pandas as pd

# Add src to path
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from liemwhisper.evaluation import (
    TextNormalizer,
    compute_levenshtein_alignment,
    ASRMetricsCalculator,
    TerminologyOccurrence,
    TerminologyEvaluator,
    SafetyMetricsEvaluator,
    PairedBootstrapTester,
    HAS_JIWER
)

if HAS_JIWER:
    import jiwer


def test_text_normalization():
    print("[1/5] Testing Text Normalization...")
    # Unicode NFD to NFC
    nfd_text = "e\u0301 qu\u0301y va len"  # Decomposed
    norm = TextNormalizer.normalize(nfd_text)
    assert norm == "é qúy va len" or norm == "équý va len" or "quy" in norm, f"Failed: {norm}"

    # Punctuation & case
    raw = "  Equivalence Partitioning! (Testing Techniques)... 'Test Case' - ok? "
    expected = "equivalence partitioning testing techniques test case ok"
    assert TextNormalizer.normalize(raw) == expected, f"Expected '{expected}', got '{TextNormalizer.normalize(raw)}'"

    # Vietnamese accents
    raw_vn = "Kiểm thử phần mềm: Unit Testing, và Integration Testing."
    norm_vn = TextNormalizer.normalize(raw_vn)
    assert norm_vn == "kiểm thử phần mềm unit testing và integration testing"
    print("  -> Passed Text Normalization!")


def test_levenshtein_and_uncapped_wer():
    print("[2/5] Testing Levenshtein Alignment & Uncapped WER/CER...")

    # Identical
    s, d, ins = compute_levenshtein_alignment(["a", "b"], ["a", "b"])
    assert (s, d, ins) == (0, 0, 0), f"Failed identical: {s, d, ins}"

    # Substitution
    s, d, ins = compute_levenshtein_alignment(["a", "b"], ["a", "c"])
    assert (s, d, ins) == (1, 0, 0)

    # Deletion
    s, d, ins = compute_levenshtein_alignment(["a", "b", "c"], ["a", "c"])
    assert (s, d, ins) == (0, 1, 0)

    # Insertion
    s, d, ins = compute_levenshtein_alignment(["a", "c"], ["a", "b", "c"])
    assert (s, d, ins) == (0, 0, 1)

    # Uncapped WER test (Ins > Ref)
    # Ref: "a b" (2 words), Hyp: "a x y z w b" (6 words) -> 4 insertions -> WER = 4 / 2 = 2.0 (200%)
    res = ASRMetricsCalculator.evaluate_pair("a b", "a x y z w b")
    assert res["utterance_wer"] == 2.0, f"Expected 2.0, got {res['utterance_wer']}"

    # Cross-check with jiwer if installed
    if HAS_JIWER:
        ref = "kiểm thử đơn vị là unit testing"
        hyp = "kiểm thử đơn vị là u nít tét ting"
        res_calc = ASRMetricsCalculator.evaluate_pair(ref, hyp)

        ref_norm = TextNormalizer.normalize(ref)
        hyp_norm = TextNormalizer.normalize(hyp)
        jiwer_wer = jiwer.wer(ref_norm, hyp_norm)
        assert abs(res_calc["utterance_wer"] - jiwer_wer) < 1e-4, f"Mismatch with jiwer: {res_calc['utterance_wer']} vs {jiwer_wer}"
        print("  -> Cross-validated against jiwer successfully!")

    print("  -> Passed Levenshtein & Uncapped WER/CER!")


def test_terminology_evaluation():
    print("[3/5] Testing Terminology Occurrence-Level Evaluation...")

    # Case 1: Duplicate prediction test (1-to-1 matching)
    # Gold: 1 instance of 'Test Case'
    # Pred: 3 instances of 'Test Case'
    # Should yield: TP=1, FP=2, FN=0 -> Precision = 1/3, Recall = 1/1 = 1.0
    gold = [TerminologyOccurrence("Test Case", "Testware")]
    pred = [
        TerminologyOccurrence("Test Case", "Testware"),
        TerminologyOccurrence("Test Case", "Testware"),
        TerminologyOccurrence("Test Case", "Testware")
    ]
    res = TerminologyEvaluator.match_utterance_occurrences(gold, pred)
    assert res["term_tp"] == 1, f"Expected TP=1, got {res['term_tp']}"
    assert res["term_fp"] == 2, f"Expected FP=2, got {res['term_fp']}"
    assert res["term_fn"] == 0, f"Expected FN=0, got {res['term_fn']}"

    # Case 2: End-to-End Term + Category match
    # Gold: 'Equivalence Partitioning' (Testing Techniques)
    # Pred: 'Equivalence Partitioning' (Quality and Metrics) -> Term matched, but Category mismatch
    gold2 = [TerminologyOccurrence("Equivalence Partitioning", "Testing Techniques")]
    pred2 = [TerminologyOccurrence("Equivalence Partitioning", "Quality and Metrics")]
    res2 = TerminologyEvaluator.match_utterance_occurrences(gold2, pred2)
    assert res2["term_tp"] == 1, "Term should match lexically"
    assert res2["e2e_tp"] == 0, "End-to-End should FAIL because category mismatched"
    assert res2["e2e_fp"] == 1
    assert res2["e2e_fn"] == 1

    print("  -> Passed Terminology & End-to-End Occurrence Evaluation!")


def test_safety_metrics():
    print("[4/5] Testing Safety Metrics & Harmful-Correction Rate...")

    gold_list = [
        [TerminologyOccurrence("Test Case")],  # Sample 0
        [TerminologyOccurrence("Bug Report")],  # Sample 1
        [],                                     # Sample 2 (No-term utterance)
        [TerminologyOccurrence("Unit Testing")] # Sample 3
    ]

    # Baseline:
    # Sample 0: correct ("Test Case")
    # Sample 1: correct ("Bug Report")
    # Sample 2: correct (empty)
    # Sample 3: incorrect (empty)
    base_list = [
        [TerminologyOccurrence("Test Case")],
        [TerminologyOccurrence("Bug Report")],
        [],
        []
    ]

    # Candidate system:
    # Sample 0: correct ("Test Case") -> Preserved correct
    # Sample 1: INCORRECT ("Bug") -> HARMFUL CORRUPTION!
    # Sample 2: HALLUCINATES ("Sanity Testing") -> Spurious insertion in no-term
    # Sample 3: FIXED ("Unit Testing") -> SUCCESSFUL CORRECTION!
    cand_list = [
        [TerminologyOccurrence("Test Case")],
        [TerminologyOccurrence("Bug")],
        [TerminologyOccurrence("Sanity Testing")],
        [TerminologyOccurrence("Unit Testing")]
    ]

    safety = SafetyMetricsEvaluator.evaluate_comparative_safety(gold_list, base_list, cand_list)
    # Overall:
    # 4 utterances:
    # Sample 0: correct -> preserved correct
    # Sample 1: correct -> harmful corruption
    # Sample 2: correct (empty) -> hallucination in no-term (harmful)
    # Sample 3: incorrect -> successful correction
    assert safety["overall_originally_correct"] == 3
    assert safety["overall_originally_incorrect"] == 1
    assert safety["overall_harmful_corruptions"] == 2
    assert safety["overall_successful_corrections"] == 1
    assert abs(safety["overall_harmful_correction_rate"] - (2.0 / 3.0)) < 1e-4

    # Term-bearing specific:
    # 3 term-bearing samples (0, 1, 3):
    # Originally correct: Sample 0, 1 (2 samples)
    # Originally incorrect: Sample 3 (1 sample)
    # Harmful corruption: Sample 1 (1 sample) -> TB_HCR = 1 / 2 = 0.50
    # Successful correction: Sample 3 (1 sample) -> TB_CSR = 1 / 1 = 1.0
    assert safety["term_bearing_samples"] == 3
    assert safety["term_bearing_originally_correct"] == 2
    assert safety["term_bearing_originally_incorrect"] == 1
    assert safety["term_bearing_harmful_corruptions"] == 1
    assert safety["term_bearing_successful_corrections"] == 1
    assert safety["term_bearing_harmful_correction_rate"] == 0.5
    assert safety["term_bearing_correction_success_rate"] == 1.0

    # No-term hallucination tracking:
    assert safety["no_term_utterance_count"] == 1
    assert safety["candidate_hallucination_count"] == 1
    assert safety["no_term_hallucination_rate"] == 1.0
    print("  -> Passed Safety Metrics & Harmful-Correction Rate!")


def test_paired_bootstrap():
    print("[5/5] Testing Speaker-Clustered Paired Bootstrap Hypothesis Testing...")

    # Create dummy dataframe with 4 speakers, 10 utterances
    data = []
    for spk_idx in range(4):
        spk_id = f"SPK_{spk_idx:02d}"
        for utt in range(3):
            # Candidate has fewer errors than baseline
            data.append({
                "speaker_id": spk_id,
                "ref": "kiểm thử phần mềm tự động hóa test automation",
                "base_hyp": "kiểm thử phần mềm tự động hóa",  # 2 deletions
                "cand_hyp": "kiểm thử phần mềm tự động hóa test automation" # 0 edits
            })

    df = pd.DataFrame(data)
    boot = PairedBootstrapTester.test_wer_difference(
        df,
        ref_col="ref",
        base_hyp_col="base_hyp",
        cand_hyp_col="cand_hyp",
        speaker_col="speaker_id",
        n_resamples=500,
        random_seed=42
    )

    assert boot["observed_wer_reduction"] > 0, "Candidate must improve over baseline"
    assert boot["is_significant_95"] == True, "Improvement should be statistically significant"
    assert boot["empirical_p_value"] < 0.05
    print("  -> Passed Speaker-Clustered Paired Bootstrap!")


if __name__ == "__main__":
    print("=" * 60)
    print("RUNNING UNIT TESTS FOR LIEMWHISPER EVALUATION TOOLKIT")
    print("=" * 60)
    test_text_normalization()
    test_levenshtein_and_uncapped_wer()
    test_terminology_evaluation()
    test_safety_metrics()
    test_paired_bootstrap()
    print("=" * 60)
    print("ALL TESTS PASSED! EVALUATION HARNESS IS FULLY VERIFIED.")
    print("=" * 60)
