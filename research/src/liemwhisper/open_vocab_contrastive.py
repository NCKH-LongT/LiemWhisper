"""
LiemWhisper Open-Vocabulary Terminology Recognition: Audio-Text Contrastive Learning
====================================================================================
Implements zero-shot / unseen technical term retrieval via joint Audio-Text representation:
1. Audio Encoder (Whisper acoustic features) + Text Encoder (Multilingual Sentence-BERT).
2. Symmetric InfoNCE Contrastive Loss to project both modalities into a shared d=256 embedding space.
3. Disjoint Train/Test term partitioning (Zero Leakage: T_train ∩ T_test = ∅).
4. FAISS Cosine Similarity retrieval for evaluating Unseen Term Recognition.

Research Question:
    Can LiemWhisper improve the recognition of specialized terms NOT present in training
    data compared to vanilla Whisper / PhoWhisper baselines?
"""

import os
import sys
import json
import time
from typing import List, Dict, Any, Tuple, Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import torch
import torch.nn as nn
import torch.nn.functional as F
import numpy as np
import pandas as pd
import faiss

# Import InfoNCE loss from alignment module
current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from alignment import symmetric_info_nce


# Canonical list of 6 Unseen Test Terms (Disjoint from 18 Train Terms)
UNSEEN_TEST_TERMS = [
    "Load Testing",
    "Stress Testing",
    "Code Coverage",
    "Statement Coverage",
    "Bug Report",
    "Equivalence Partitioning"
]


def partition_dataset_by_terms(
    df: pd.DataFrame,
    unseen_terms: List[str] = UNSEEN_TEST_TERMS
) -> Tuple[pd.DataFrame, pd.DataFrame, List[str], List[str]]:
    """
    Partitions dataset into Train and Unseen-Test sets by disjoint terms.
    Ensures that NO audio in the Train set contains ANY of the Unseen Test Terms.
    """
    unseen_set = set(t.lower() for t in unseen_terms)
    train_rows = []
    test_rows = []

    for idx, r in df.iterrows():
        raw_gt = str(r.get("gold_terms", ""))
        terms = [t.strip().lower() for t in raw_gt.split(";") if t.strip()]

        # If any term is in the unseen set, this utterance is strictly for test
        is_unseen = any(t in unseen_set for t in terms)
        if is_unseen:
            test_rows.append(r)
        else:
            train_rows.append(r)

    train_df = pd.DataFrame(train_rows).reset_index(drop=True)
    test_df = pd.DataFrame(test_rows).reset_index(drop=True)

    # Collect actual unique terms in each split
    train_terms = sorted(list(set(
        t.strip().title()
        for raw in train_df["gold_terms"].dropna()
        for t in str(raw).split(";") if t.strip()
    )))
    test_terms = sorted(list(set(
        t.strip().title()
        for raw in test_df["gold_terms"].dropna()
        for t in str(raw).split(";") if t.strip() and t.strip().lower() in unseen_set
    )))

    # Verify zero leakage
    leakage = set(t.lower() for t in train_terms).intersection(set(t.lower() for t in test_terms))
    assert len(leakage) == 0, f"Critical Data Leakage detected: {leakage}"

    return train_df, test_df, train_terms, test_terms


class AudioProjectionHead(nn.Module):
    """Projects Whisper acoustic features to shared embedding space."""
    def __init__(self, in_features: int = 768, shared_dim: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_features, 512),
            nn.LayerNorm(512),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(512, shared_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.net(x)
        return F.normalize(out, p=2, dim=-1)


class TextProjectionHead(nn.Module):
    """Projects Multilingual Text Encoder embeddings to shared embedding space."""
    def __init__(self, in_features: int = 384, shared_dim: int = 256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(in_features, 512),
            nn.LayerNorm(512),
            nn.GELU(),
            nn.Dropout(0.1),
            nn.Linear(512, shared_dim)
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        out = self.net(x)
        return F.normalize(out, p=2, dim=-1)


class AudioTextContrastiveModel(nn.Module):
    """
    Joint Audio-Text Dual-Encoder Model.
    Learns shared space where audio of a term is close to the text of the term.
    """
    def __init__(self, audio_in_dim: int = 768, text_in_dim: int = 384, shared_dim: int = 256):
        super().__init__()
        self.audio_proj = AudioProjectionHead(audio_in_dim, shared_dim)
        self.text_proj = TextProjectionHead(text_in_dim, shared_dim)
        self.temperature = nn.Parameter(torch.ones([]) * np.log(1 / 0.07))

    def forward(self, audio_feat: torch.Tensor, text_feat: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        z_audio = self.audio_proj(audio_feat)
        z_text = self.text_proj(text_feat)
        return z_audio, z_text

    def compute_loss(self, z_audio: torch.Tensor, z_text: torch.Tensor) -> torch.Tensor:
        temp = torch.clamp(self.temperature.exp(), min=0.01, max=100.0)
        return symmetric_info_nce(z_audio, z_text, temperature=float(temp.item()))


class FaissTermRetriever:
    """
    FAISS-based Cosine Similarity Index for fast retrieval over candidate terms.
    Used during inference to retrieve the closest term given an audio embedding.
    """
    def __init__(self, candidate_terms: List[str], text_embeddings: np.ndarray):
        self.candidate_terms = candidate_terms
        dim = text_embeddings.shape[1]

        # Inner Product with normalized vectors == Cosine Similarity
        self.index = faiss.IndexFlatIP(dim)
        norm_embeddings = text_embeddings / np.linalg.norm(text_embeddings, axis=1, keepdims=True)
        self.index.add(norm_embeddings.astype(np.float32))

    def retrieve(self, query_audio_emb: np.ndarray, k: int = 5) -> List[Dict[str, Any]]:
        """
        Retrieves Top-K candidate terms for a given query audio embedding.
        """
        if query_audio_emb.ndim == 1:
            query_audio_emb = query_audio_emb.reshape(1, -1)
        norm_q = query_audio_emb / np.linalg.norm(query_audio_emb, axis=1, keepdims=True)
        scores, indices = self.index.search(norm_q.astype(np.float32), k)

        results = []
        for rank in range(k):
            idx = indices[0][rank]
            if 0 <= idx < len(self.candidate_terms):
                results.append({
                    "rank": rank + 1,
                    "term": self.candidate_terms[idx],
                    "similarity": float(scores[0][rank])
                })
        return results
