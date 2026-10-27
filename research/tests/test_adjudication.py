"""
Unit Test Suite for LiemWhisper Annotation Adjudication Pipeline
================================================================
Validates:
1. Pairwise Word Agreement and Character Agreement calculations
2. Cohen's Kappa categorical calculation & interpretation
3. Term parsing from multiple annotator formats
4. Discrepancy detector and IAA evaluation
5. Gold Standard Manifest merger logic
"""

import os
import sys
import pytest
import pandas as pd

src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from liemwhisper.baselines import TaxonomyManager
from liemwhisper.adjudicate_annotations import (
    compute_pairwise_agreement,
    compute_cohens_kappa,
    AnnotationAdjudicationPipeline
)

TAXONOMY_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "..",
    "Data",
    "glossary_taxonomy_v1.json"
))


def test_pairwise_agreement():
    print("[1/5] Testing Pairwise Word & Character Agreement...")
    text1 = "Em dùng Equivalence Partitioning để chia các phân vùng hợp lệ."
    text2 = "Em dùng Equivalence Partitioning để chia các phân vùng hợp lệ."
    pw_identical = compute_pairwise_agreement(text1, text2)
    assert pw_identical["word_agreement"] == 1.0
    assert pw_identical["char_agreement"] == 1.0

    # 1 word different out of 10 words
    text3 = "Em dùng Equivalence Partitioning để chia các phân vùng không hợp lệ."
    pw_diff = compute_pairwise_agreement(text1, text3)
    assert 0.80 <= pw_diff["word_agreement"] < 1.0
    print("  -> Passed Pairwise Agreement!")


def test_cohens_kappa_calculation():
    print("[2/5] Testing Cohen's Kappa Calculation...")
    # Perfect agreement
    r1 = ["Testing Techniques", "Testware", "Quality and Metrics", "No_Term"]
    r2 = ["Testing Techniques", "Testware", "Quality and Metrics", "No_Term"]
    res_perfect = compute_cohens_kappa(r1, r2)
    assert res_perfect["kappa"] == 1.0
    assert res_perfect["interpretation"] == "Almost Perfect Agreement"

    # Known disagreement
    rater_a = ["CatA", "CatA", "CatB", "CatB"]
    rater_b = ["CatA", "CatB", "CatA", "CatB"]
    res_half = compute_cohens_kappa(rater_a, rater_b)
    assert res_half["kappa"] == 0.0  # Exactly chance agreement
    assert res_half["interpretation"] == "Slight Agreement" or res_half["interpretation"] == "Poor / Chance Agreement"
    print("  -> Passed Cohen's Kappa!")


def test_term_parsing():
    print("[3/5] Testing Annotator Term Parsing...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    pipeline = AnnotationAdjudicationPipeline(tax)

    # JSON formatted
    json_str = '[{"term": "Bug Report", "category": "Testware"}, {"term": "Test Case", "category": "Testware"}]'
    terms_json = pipeline.parse_annotator_terms(json_str)
    assert terms_json == ["bug report", "test case"]

    # Semicolon formatted
    semi_str = "Equivalence Partitioning; Boundary Value Analysis"
    terms_semi = pipeline.parse_annotator_terms(semi_str)
    assert terms_semi == ["equivalence partitioning", "boundary value analysis"]

    # Empty / None
    assert pipeline.parse_annotator_terms("[]") == []
    assert pipeline.parse_annotator_terms("") == []
    print("  -> Passed Term Parsing!")


def test_iaa_evaluation():
    print("[4/5] Testing IAA Evaluation on Mock Double Annotations...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    pipeline = AnnotationAdjudicationPipeline(tax)

    df_a = pd.DataFrame([
        {
            "recording_id": "REC_001",
            "is_double_annotation_candidate": True,
            "verbatim_transcript": "Em viết test case hoàn chỉnh.",
            "annotator_identified_terms": '[{"term": "Test Case"}]'
        },
        {
            "recording_id": "REC_002",
            "is_double_annotation_candidate": True,
            "verbatim_transcript": "Em báo cáo bớt report.",
            "annotator_identified_terms": '[{"term": "Bug Report"}]'
        }
    ])

    df_b = pd.DataFrame([
        {
            "recording_id": "REC_001",
            "is_double_annotation_candidate": True,
            "verbatim_transcript": "Em viết test case hoàn chỉnh.",
            "annotator_identified_terms": '[{"term": "Test Case"}]'
        },
        {
            "recording_id": "REC_002",
            "is_double_annotation_candidate": True,
            "verbatim_transcript": "Em báo cáo bớt report.",
            "annotator_identified_terms": '[]'  # Disagreement!
        }
    ])

    iaa = pipeline.evaluate_inter_annotator_agreement(df_a, df_b)
    assert iaa["total_double_annotations"] == 2
    assert iaa["perfectly_agreed_count"] == 1
    assert iaa["disagreement_count"] == 1
    assert iaa["disagreements"][0]["recording_id"] == "REC_002"
    print("  -> Passed IAA Evaluation!")


def test_gold_manifest_builder():
    print("[5/5] Testing Gold Manifest Builder...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    pipeline = AnnotationAdjudicationPipeline(tax)

    df_a = pd.DataFrame([
        {
            "recording_id": "REC_001",
            "speaker_id": "SPK_01",
            "wav_file": "001.wav",
            "prompt_text": "Prompt 1",
            "verbatim_transcript": "Em dùng Unit Testing.",
            "annotator_identified_terms": '[{"term": "Unit Testing"}]',
            "is_double_annotation_candidate": False
        }
    ])

    df_b = pd.DataFrame([
        {
            "recording_id": "REC_002",
            "speaker_id": "SPK_02",
            "wav_file": "002.wav",
            "prompt_text": "Prompt 2",
            "verbatim_transcript": "Em chạy Load Testing.",
            "annotator_identified_terms": '[{"term": "Load Testing"}]',
            "is_double_annotation_candidate": False
        }
    ])

    gold_df = pipeline.build_gold_manifest(df_a, df_b)
    assert len(gold_df) == 2
    assert set(gold_df["recording_id"]) == {"REC_001", "REC_002"}
    assert "Testing Levels and Types" in gold_df.iloc[0]["gold_categories"]
    print("  -> Passed Gold Manifest Builder!")
