"""Small reusable shared-space contrastive loss component.

This module does not implement a complete encoder or experiment.
"""
from __future__ import annotations

import torch
from torch import Tensor
from torch.nn import functional as F


def symmetric_info_nce(audio_embeddings: Tensor, text_embeddings: Tensor, temperature: float = 0.07) -> Tensor:
    """Symmetric CLIP-style InfoNCE for UNIQUE positive terms per batch.

    Repeated identical target terms require multi-positive handling not provided here.
    Both inputs have shape [batch, embedding_dimension].
    """
    if audio_embeddings.ndim != 2 or audio_embeddings.shape != text_embeddings.shape:
        raise ValueError("Both embedding batches must have identical [B, D] shape")
    if audio_embeddings.shape[0] < 2:
        raise ValueError("Batch must contain at least two distinct pairs")
    if temperature <= 0:
        raise ValueError("temperature must be positive")
    audio = F.normalize(audio_embeddings, p=2, dim=-1)
    text = F.normalize(text_embeddings, p=2, dim=-1)
    logits = (audio @ text.T) / temperature
    targets = torch.arange(logits.shape[0], device=logits.device)
    return 0.5 * (F.cross_entropy(logits, targets) + F.cross_entropy(logits.T, targets))


def retrieval_topk(audio_embeddings: Tensor, text_embeddings: Tensor, k: int = 5) -> Tensor:
    """Return zero-based Top-K lexical candidate indices using cosine similarity."""
    if audio_embeddings.ndim != 2 or text_embeddings.ndim != 2 or audio_embeddings.shape[1] != text_embeddings.shape[1]:
        raise ValueError("Expected [N,D] audio and [M,D] text embeddings with shared D")
    if not 1 <= k <= text_embeddings.shape[0]:
        raise ValueError("k must be within candidate count")
    scores = F.normalize(audio_embeddings, dim=-1) @ F.normalize(text_embeddings, dim=-1).T
    return scores.topk(k, dim=1).indices
