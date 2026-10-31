"""
Unit Test Suite for LiemWhisper Proposed Method P (Candidate Ranking Engine)
=============================================================================
Validates:
1. Phonetic skeleton extraction and token alignment similarity
2. Contextual compatibility scoring against ISTQB CTFL definitions
3. Candidate generator multi-span extraction and pruning
4. Evidence ranker decision gate and thresholding
5. End-to-end ProposedSystemP processing, span substitution, and category lookup
"""

import os
import sys
import pytest

src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from liemwhisper.baselines import TaxonomyManager
from liemwhisper.candidate_ranking import (
    phonetic_skeleton,
    remove_vn_accents,
    sequence_similarity,
    token_alignment_similarity,
    ContextualCompatibilityScorer,
    CandidateGenerator,
    EvidenceRanker,
    ConsensusFrontEnd,
    ProposedSystemP
)

TAXONOMY_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "..",
    "Data",
    "glossary_taxonomy_v1.json"
))


def test_phonetic_skeleton_and_aliases():
    print("[1/5] Testing Phonetic Skeleton and Alignment...")
    # Check diacritic removal
    assert remove_vn_accents("kiểm thử phần mềm") == "kiem thu phan mem"
    assert remove_vn_accents("giá trị biên") == "gia tri bien"

    # Check skeleton equivalence
    skel1 = phonetic_skeleton("bớt")
    skel2 = phonetic_skeleton("bug")
    assert skel1[0] == skel2[0]  # Both map to 'b'

    # Check token alignment similarity on technical terms
    sim1 = token_alignment_similarity(["unit", "test"], ["unit", "testing"])
    assert sim1 > 0.80, f"Expected high similarity for 'unit test' vs 'unit testing', got {sim1}"

    # Check skeleton similarity on phonetic corruption 'bao đa ri' vs 'boundary'
    skel_vn = phonetic_skeleton("baodari")
    skel_en = phonetic_skeleton("boundary")
    sim2 = sequence_similarity(skel_vn, skel_en)
    assert sim2 >= 0.50, f"Expected similarity for 'baodari' skeleton vs 'boundary' >= 0.50, got {sim2}"

    print("  -> Passed Phonetic Skeleton and Alignment!")


def test_contextual_compatibility_scorer():
    print("[2/5] Testing Contextual Compatibility Scorer...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    scorer = ContextualCompatibilityScorer(tax)

    # Relevant context for Equivalence Partitioning
    ctx_ep = "chúng ta chia dữ liệu đầu vào thành các phân vùng hợp lệ và không hợp lệ"
    sim_ep = scorer.compute_context_compatibility(ctx_ep, "Equivalence Partitioning")
    assert sim_ep > 0.15, f"Expected positive context score for EP, got {sim_ep}"

    # Irrelevant context for Security Testing
    ctx_irrelevant = "nấu ăn cơm trưa ngoài đồng"
    sim_sec = scorer.compute_context_compatibility(ctx_irrelevant, "Security Testing")
    assert sim_sec == 0.0, f"Expected 0.0 for irrelevant context, got {sim_sec}"

    print("  -> Passed Contextual Compatibility Scorer!")


def test_candidate_generator():
    print("[3/5] Testing Candidate Generator...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    gen = CandidateGenerator(tax, min_retrieval_threshold=0.45)

    # Exact match span
    text = "Em thực hiện Unit Testing cho các module."
    cands = gen.generate_candidates(text)
    assert any(c["candidate_term"] == "Unit Testing" for c in cands)

    # Phonetic corruption span
    text_corrupt = "Em tạo một bớt report gửi cho dev."
    cands2 = gen.generate_candidates(text_corrupt)
    assert any(c["candidate_term"] == "Bug Report" for c in cands2)

    print("  -> Passed Candidate Generator!")


def test_evidence_ranker_decision_gate():
    print("[4/5] Testing Evidence Ranker Decision Gate...")
    ranker = EvidenceRanker(threshold=0.50)

    # Strong candidate with positive evidence
    score, prob = ranker.score_candidate(
        lexical_sim=0.85,
        phonetic_sim=0.90,
        acoustic_delta=0.5,
        context_sim=0.3,
        margin=0.25
    )
    assert prob >= 0.50
    assert ranker.should_accept(prob) is True

    # Weak candidate with negative acoustic delta and low lexical match
    score_weak, prob_weak = ranker.score_candidate(
        lexical_sim=0.20,
        phonetic_sim=0.30,
        acoustic_delta=-2.0,
        context_sim=0.0,
        margin=0.0
    )
    assert prob_weak < 0.50
    assert ranker.should_accept(prob_weak) is False

    print("  -> Passed Evidence Ranker Decision Gate!")


def test_proposed_system_p_end_to_end():
    print("[5/5] Testing ProposedSystemP End-to-End Pipeline...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    # Acoustic scorer set to None for offline testing (uses lexical + phonetic + context)
    system_p = ProposedSystemP(tax, acoustic_scorer=None, acceptance_threshold=0.50)

    # Test sentence with 2 corrupted technical terms
    test_transcript = "Sau khi hoàn thành xong em tiến hành unit test và xuất bớt report chi tiết."
    result = system_p.process_utterance(test_transcript)

    predicted = [t.term for t in result["predicted_terms"]]
    categories = [t.category for t in result["predicted_terms"]]

    assert "unit testing" in predicted, f"Expected 'unit testing', got {predicted}"
    assert "bug report" in predicted, f"Expected 'bug report', got {predicted}"
    assert "Testing Levels and Types" in categories
    assert "Testware" in categories

    # Revised transcript check
    assert "Unit Testing" in result["revised_transcript"]
    assert "Bug Report" in result["revised_transcript"]

    # Harmless sentence without technical terms
    normal_sentence = "hôm nay thời tiết rất đẹp và mọi người cùng đi dạo phố"
    res_normal = system_p.process_utterance(normal_sentence)
    assert len(res_normal["predicted_terms"]) == 0
    assert res_normal["revised_transcript"] == normal_sentence

    print("  -> Passed ProposedSystemP End-to-End Pipeline!")


def test_regional_phonetic_matrix():
    print("[6/8] Testing Regional Loanword Phonetic Matrix...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    gen = CandidateGenerator(tax, min_retrieval_threshold=0.45)

    # Southern loanword corruption: "bớt rì pọt" -> Bug Report
    text_south = "Hôm nay em nộp bớt rì pọt cho tech lead."
    cands_south = gen.generate_candidates(text_south)
    assert any(c["candidate_term"] == "Bug Report" for c in cands_south)

    # Phonetic alias: "stage transition testing" -> State Transition Testing
    text_stage = "Thực hiện stage transition testing trên giao diện."
    cands_stage = gen.generate_candidates(text_stage)
    assert any(c["candidate_term"] == "State Transition Testing" for c in cands_stage)

    # Phonetic alias: "borrowing value analysis" -> Boundary Value Analysis
    text_bva = "Áp dụng borrowing value analysis để xác định điểm biên."
    cands_bva = gen.generate_candidates(text_bva)
    assert any(c["candidate_term"] == "Boundary Value Analysis" for c in cands_bva)

    print("  -> Passed Regional Loanword Phonetic Matrix!")


def test_hierarchical_category_prior_boosting():
    print("[7/8] Testing Hierarchical Category Prior Boosting...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    scorer = ContextualCompatibilityScorer(tax)

    # Context with generic category design cues: "kỹ thuật thiết kế kiểm thử hộp đen input parameter"
    ctx_technique = "kỹ thuật thiết kế kiểm thử hộp đen phân vùng và kết hợp input parameter"

    # Category member: State Transition Testing (Testing Techniques)
    sim_tech = scorer.compute_context_compatibility(ctx_technique, "State Transition Testing")
    # Non-member: Security Testing (Testing Levels and Types)
    sim_sec = scorer.compute_context_compatibility(ctx_technique, "Security Testing")

    assert sim_tech > 0.15, f"Expected strong category compatibility for State Transition Testing, got {sim_tech}"
    assert sim_tech > sim_sec, f"Expected higher score for Testing Techniques member ({sim_tech}) vs non-member ({sim_sec})"

    print("  -> Passed Hierarchical Category Prior Boosting!")


def test_dual_engine_consensus_front_end():
    print("[8/8] Testing Dual-Engine ASR Consensus Front-End...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    consensus = ConsensusFrontEnd(tax)

    # Primary Whisper transcript has corrupted term "stage transition testing"
    primary_whisper = "Thực hiện kiểm thử kết hợp input parameter theo stage transition testing để tìm lỗi."
    # Secondary Nemotron transcript recognized "state transition testing"
    secondary_nemotron = "Được nghiện kiếm tử kết hợp input parameter theo state transition testing để tìm ra các lỗi."

    fused_text, hints = consensus.fuse_transcripts(primary_whisper, secondary_nemotron)
    assert len(hints) >= 1
    assert hints[0]["candidate_term"] == "State Transition Testing"
    assert hints[0]["method"] == "Dual_Engine_Consensus"

    # End-to-end processing with dual engine consensus
    system_p = ProposedSystemP(tax, acoustic_scorer=None, acceptance_threshold=0.50, enable_consensus=True)
    res = system_p.process_utterance(primary_whisper, secondary_transcript=secondary_nemotron)

    predicted_terms = [t.term for t in res["predicted_terms"]]
    assert "state transition testing" in predicted_terms
    assert "State Transition Testing" in res["revised_transcript"]

    print("  -> Passed Dual-Engine ASR Consensus Front-End!")
