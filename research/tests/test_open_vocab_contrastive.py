"""
Unit Test Suite for Open-Vocabulary Audio-Text Contrastive Learning & FAISS Retrieval
=====================================================================================
Validates:
1. Zero-leakage disjoint term split (Train terms ∩ Unseen Test terms = ∅).
2. Dual-Encoder projection heads & Symmetric InfoNCE loss computation.
3. FAISS index construction, cosine search, and retrieval consistency.
"""

import os
import sys
import pytest
import torch
import numpy as np
import pandas as pd

src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from liemwhisper.open_vocab_contrastive import (
    UNSEEN_TEST_TERMS,
    partition_dataset_by_terms,
    AudioTextContrastiveModel,
    FaissTermRetriever
)


def test_disjoint_term_partitioning():
    """Validates that partitioning produces disjoint sets with zero term leakage."""
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "Data", "gold_with_asr_v1.csv"))
    if not os.path.exists(csv_path):
        pytest.skip("Dataset file not available")

    df = pd.read_csv(csv_path)
    train_df, test_df, train_terms, test_terms = partition_dataset_by_terms(df, UNSEEN_TEST_TERMS)

    assert len(train_df) > 0
    assert len(test_df) > 0
    assert len(test_terms) > 0
    assert len(train_terms) > 0

    # Ensure intersection is completely empty
    train_set = set(t.lower() for t in train_terms)
    test_set = set(t.lower() for t in test_terms)
    intersection = train_set.intersection(test_set)
    assert len(intersection) == 0, f"Found leaked terms: {intersection}"


def test_contrastive_model_forward_and_loss():
    """Validates projection heads and InfoNCE loss gradient flow."""
    model = AudioTextContrastiveModel(audio_in_dim=64, text_in_dim=32, shared_dim=16)

    audio_feat = torch.randn(4, 64)
    text_feat = torch.randn(4, 32)

    z_audio, z_text = model(audio_feat, text_feat)
    assert z_audio.shape == (4, 16)
    assert z_text.shape == (4, 16)

    # Check L2 normalization
    norms_a = torch.norm(z_audio, p=2, dim=-1)
    norms_t = torch.norm(z_text, p=2, dim=-1)
    assert torch.allclose(norms_a, torch.ones_like(norms_a), atol=1e-5)
    assert torch.allclose(norms_t, torch.ones_like(norms_t), atol=1e-5)

    loss = model.compute_loss(z_audio, z_text)
    assert torch.isfinite(loss)
    assert loss.item() > 0.0

    loss.backward()
    assert model.audio_proj.net[0].weight.grad is not None


def test_faiss_retriever_exact_match():
    """Validates FAISS cosine similarity retrieval on candidate terms."""
    terms = ["Load Testing", "Stress Testing", "Code Coverage", "Bug Report"]
    dim = 16

    # Generate distinct normalized embeddings
    np.random.seed(42)
    embs = np.random.randn(len(terms), dim).astype(np.float32)
    embs = embs / np.linalg.norm(embs, axis=1, keepdims=True)

    retriever = FaissTermRetriever(terms, embs)

    # Query with the exact embedding of "Stress Testing" (idx=1)
    query = embs[1]
    res = retriever.retrieve(query, k=2)

    assert len(res) == 2
    assert res[0]["rank"] == 1
    assert res[0]["term"] == "Stress Testing"
    assert pytest.approx(res[0]["similarity"], abs=1e-4) == 1.0
