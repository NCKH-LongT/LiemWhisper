"""
LiemWhisper Open-Vocabulary: Contrastive Matcher Training
========================================================
Trains the Audio-Text Contrastive Projection Heads using Symmetric InfoNCE Loss
on the 18 Train Terms (100% disjoint from the 6 Unseen Test Terms).
"""

import os
import sys
import json
import time
import numpy as np
import torch
from torch.utils.data import TensorDataset, DataLoader

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from open_vocab_contrastive import AudioTextContrastiveModel


def train_contrastive_matcher(
    features_dir: str = "Data/features_contrastive",
    output_model_dir: str = "Data/models/contrastive_open_vocab",
    epochs: int = 25,
    batch_size: int = 32,
    lr: float = 1e-3
):
    print("=" * 80)
    print("TRAINING AUDIO-TEXT CONTRASTIVE MATCHER (INFONCE)")
    print("=" * 80)
    os.makedirs(output_model_dir, exist_ok=True)

    # 1. Load Pre-extracted Features
    print(f"[Data] Loading features from {features_dir}...")
    train_audio = np.load(os.path.join(features_dir, "train_audio_embs.npy")) # [N, 384]
    train_targets = np.load(os.path.join(features_dir, "train_targets.npy"))   # [N]
    term_text_embs = np.load(os.path.join(features_dir, "term_text_embs.npy"))# [24, 512]

    with open(os.path.join(features_dir, "terms_meta.json"), "r", encoding="utf-8") as f:
        meta = json.load(f)

    print(f"[Data] Train Audio: {train_audio.shape}, Text Embeddings: {term_text_embs.shape}")
    print(f"[Data] Train Terms ({len(meta['train_terms'])}): {meta['train_terms'][:5]}...")
    print(f"[Data] Strictly Unseen Terms ({len(meta['test_terms'])}): {meta['test_terms']}")

    # Form paired training tensors
    train_text = term_text_embs[train_targets] # [N, 512]

    t_audio = torch.tensor(train_audio, dtype=torch.float32)
    t_text = torch.tensor(train_text, dtype=torch.float32)

    dataset = TensorDataset(t_audio, t_text)
    loader = DataLoader(dataset, batch_size=batch_size, shuffle=True, drop_last=True)

    # 2. Initialize Model
    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[Model] Initializing AudioTextContrastiveModel on {device}...")
    model = AudioTextContrastiveModel(audio_in_dim=384, text_in_dim=512, shared_dim=256)
    model.to(device)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=epochs)

    # 3. Training Loop
    print(f"\n[Training] Starting {epochs} epochs (batch_size={batch_size})...")
    t0 = time.time()
    best_loss = float("inf")

    for epoch in range(1, epochs + 1):
        model.train()
        total_loss = 0.0
        num_batches = 0

        for b_audio, b_text in loader:
            b_audio = b_audio.to(device)
            b_text = b_text.to(device)

            optimizer.zero_grad()
            z_audio, z_text = model(b_audio, b_text)
            loss = model.compute_loss(z_audio, z_text)
            loss.backward()
            optimizer.step()

            total_loss += loss.item()
            num_batches += 1

        scheduler.step()
        avg_loss = total_loss / max(num_batches, 1)

        if epoch % 5 == 0 or epoch == 1 or epoch == epochs:
            elapsed = time.time() - t0
            temp_val = torch.clamp(model.temperature.exp(), min=0.01, max=100.0).item()
            print(f"  Epoch [{epoch:2d}/{epochs:2d}] | InfoNCE Loss: {avg_loss:.4f} | Temp: {temp_val:.3f} | Time: {elapsed:.1f}s")

        if avg_loss < best_loss:
            best_loss = avg_loss
            torch.save(model.state_dict(), os.path.join(output_model_dir, "best_contrastive_model.pt"))

    # Save final model & metadata
    torch.save(model.state_dict(), os.path.join(output_model_dir, "final_contrastive_model.pt"))
    with open(os.path.join(output_model_dir, "model_config.json"), "w", encoding="utf-8") as f:
        json.dump({
            "audio_in_dim": 384,
            "text_in_dim": 512,
            "shared_dim": 256,
            "best_loss": round(best_loss, 4),
            "epochs": epochs
        }, f, indent=2)

    print("\n" + "=" * 80)
    print(f"[SUCCESS] Contrastive training complete! Best Loss: {best_loss:.4f}")
    print(f"Model saved at: {output_model_dir}")
    print("=" * 80)


if __name__ == "__main__":
    train_contrastive_matcher()
