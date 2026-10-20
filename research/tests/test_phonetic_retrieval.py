"""Unit tests for LiemWhisper Phonetic Retrieval Engine."""
import sys
from pathlib import Path

# Add research/src to path
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import pytest
from liemwhisper.phonetic_retrieval import (
    phonetic_skeleton,
    remove_vn_accents,
    sequence_similarity,
    token_alignment_similarity,
    LiemWhisperPhoneticRetrieval,
)


def test_remove_vn_accents():
    assert remove_vn_accents("kiểm thử phần mềm") == "kiem thu phan mem"
    assert remove_vn_accents("Đo lường") == "do luong"


def test_phonetic_skeleton():
    assert phonetic_skeleton("Boundary") != ""
    assert phonetic_skeleton("Bao Dari") != ""
    # Similar consonant skeleton for phonetically close sounds
    skel_term = phonetic_skeleton("Bug")
    skel_mis = phonetic_skeleton("Bớt")
    assert skel_term[0] == skel_mis[0]  # Both start with B


def test_sequence_similarity():
    assert sequence_similarity("abc", "abc") == 1.0
    assert sequence_similarity("", "abc") == 0.0
    assert 0.0 < sequence_similarity("bntr", "bndr") < 1.0


def test_phonetic_retrieval_candidate_generation(tmp_path):
    # Create minimal mock taxonomy
    import json

    tax_file = tmp_path / "mock_taxonomy.json"
    tax_data = {
        "categories": {
            "Testing Techniques": {
                "terms": ["Boundary Value Analysis", "Equivalence Partitioning", "Decision Table Testing"]
            },
            "Quality and Metrics": {
                "terms": ["Code Coverage", "Statement Coverage"]
            }
        }
    }
    tax_file.write_text(json.dumps(tax_data, ensure_ascii=False), encoding="utf-8")

    engine = LiemWhisperPhoneticRetrieval(str(tax_file))

    # Test 1: Phonetic alias fast-path
    res1 = engine.retrieve_candidates("Chỉ số code code gray đo lường tỷ lệ ma lệnh")
    assert len(res1) > 0
    top_cand = res1[0]
    assert top_cand["term"] == "Code Coverage"
    assert top_cand["category"] == "Quality and Metrics"
    assert top_cand["score"] >= 0.90

    # Test 2: Boundary Value Analysis alias
    res2 = engine.retrieve_candidates("Bao Dari, Valor, Analyzic tập trung kiểm thử tại các giá trị biên")
    assert len(res2) > 0
    assert res2[0]["term"] == "Boundary Value Analysis"
    assert res2[0]["category"] == "Testing Techniques"

    # Test 3: Empty input handling
    assert engine.retrieve_candidates("") == []
    assert engine.retrieve_candidates("   ") == []
