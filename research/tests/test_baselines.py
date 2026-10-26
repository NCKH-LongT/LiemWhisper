"""
Unit Test Suite for LiemWhisper Baselines Engine
================================================
Validates System B0, B1, B2 components.
"""

import os
import sys
import pytest

# Add src to path
src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from liemwhisper.baselines import (
    TaxonomyManager,
    ExactMatchingBaseline,
    LexicalFuzzyMatcher
)

TAXONOMY_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__),
    "..", "..", "..", "..",
    "Data",
    "glossary_taxonomy_v1.json"
))


def test_taxonomy_manager():
    print("[1/3] Testing TaxonomyManager...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    assert len(tax.categories) == 5, f"Expected 5 categories, got {len(tax.categories)}"
    assert len(tax.canonical_terms) == 43, f"Expected 43 terms, got {len(tax.canonical_terms)}"

    # Check category lookup
    assert tax.get_category("Equivalence Partitioning") == "Testing Techniques"
    assert tax.get_category("Unit Testing") == "Testing Levels and Types"
    assert tax.get_category("Test Case") == "Testware"
    assert tax.get_category("Severity") == "Quality and Metrics"
    assert tax.get_category("Defect Life Cycle") == "Supporting Processes and Tools"

    # Check prompt generation
    prompt = tax.create_glossary_prompt()
    assert "Equivalence Partitioning" in prompt
    assert "Test Case" in prompt
    print("  -> Passed TaxonomyManager!")


def test_exact_matching_baseline_b0():
    print("[2/3] Testing ExactMatchingBaseline (B0)...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    b0 = ExactMatchingBaseline(tax)

    # Clean match
    text = "Em áp dụng Equivalence Partitioning để viết Test Case và Bug Report."
    terms = b0.extract_terms(text)
    term_names = [t.term for t in terms]
    assert "equivalence partitioning" in term_names
    assert "test case" in term_names
    assert "bug report" in term_names
    assert len(terms) == 3

    # Case-insensitive
    text_lower = "chúng ta dùng unit testing và system testing"
    terms2 = b0.extract_terms(text_lower)
    assert len(terms2) == 2
    assert {t.term for t in terms2} == {"unit testing", "system testing"}

    # No match
    text_none = "đây là câu nói bình thường không có thuật ngữ nào"
    assert len(b0.extract_terms(text_none)) == 0
    print("  -> Passed ExactMatchingBaseline (B0)!")


def test_lexical_fuzzy_matcher_b2():
    print("[3/3] Testing LexicalFuzzyMatcher (B2)...")
    tax = TaxonomyManager(TAXONOMY_PATH)
    b2 = LexicalFuzzyMatcher(tax, similarity_threshold=0.72)

    # Near misses commonly output by Whisper
    text = "Trong book report em sẽ ghi rõ từng bước và tạo test scale hoàn chỉnh."
    terms = b2.extract_terms(text)
    term_names = [t.term for t in terms]

    # "book report" (sim=0.8 with bug report) -> maps to bug report
    # "test scale" (sim=0.7 with test case) -> maps to test case
    assert "bug report" in term_names, f"Expected 'bug report' from 'book report', got {term_names}"
    assert "test case" in term_names, f"Expected 'test case' from 'test scale', got {term_names}"

    # Verify category
    for t in terms:
        if t.term == "bug report":
            assert t.category == "Testware"
        elif t.term == "test case":
            assert t.category == "Testware"

    print("  -> Passed LexicalFuzzyMatcher (B2)!")


if __name__ == "__main__":
    test_taxonomy_manager()
    test_exact_matching_baseline_b0()
    test_lexical_fuzzy_matcher_b2()
    print("All baseline unit tests passed successfully!")
