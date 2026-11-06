import os
import sys
import json
import time
import numpy as np
import pandas as pd
import soundfile as sf
import torch
import torch.nn as nn
import torch.nn.functional as F
from torch.utils.data import Dataset, DataLoader
from transformers import WhisperModel, WhisperFeatureExtractor, AutoTokenizer, AutoModel

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure module path
current_dir = os.path.dirname(os.path.abspath(__file__))
capstone_dir = os.path.abspath(os.path.join(current_dir, ".."))
src_dir = os.path.join(capstone_dir, "Liem", "LiemWhisper", "research", "src", "liemwhisper")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from open_vocab_contrastive import AudioTextContrastiveModel, AudioProjectionHead, TextProjectionHead

class SpanAudioDataset(Dataset):
    """Loads pre-extracted or dynamic span acoustic features."""
    def __init__(self, manifest_df, audio_features, term_to_label):
        self.manifest = manifest_df
        self.features = torch.tensor(audio_features, dtype=torch.float32)
        self.labels = torch.tensor([term_to_label[t] for t in manifest_df['term_id']], dtype=torch.long)

    def __len__(self):
        return len(self.manifest)

    def __getitem__(self, idx):
        return self.features[idx], self.labels[idx]

def extract_all_span_features(manifest_df, wav_dir="Data/wav_16k"):
    """
    Extracts raw Whisper-Tiny encoder span pooled features (384D) for all 300 spans.
    Using formula: f_start = round(t_start * 50), f_end = round(t_end * 50).
    """
    print(f"\n[Feature Extraction] Extracting 384D raw span features for {len(manifest_df)} spans...")
    fe = WhisperFeatureExtractor.from_pretrained("openai/whisper-tiny")
    audio_model = WhisperModel.from_pretrained("openai/whisper-tiny")
    audio_model.eval()

    # Cache waveforms by audio_id
    audio_wavs = {}
    unique_audios = manifest_df['audio_id'].unique()
    df_gold = pd.read_csv("Data/gold_with_asr_v1.csv").set_index('recording_id')

    t0 = time.time()
    span_features = []

    for idx, row in manifest_df.iterrows():
        rec_id = row['audio_id']
        wav_file = df_gold.loc[rec_id, 'wav_file']
        wav_path = os.path.join(wav_dir, wav_file)

        if rec_id not in audio_wavs:
            wav, sr = sf.read(wav_path)
            inputs = fe(wav, sampling_rate=sr, return_tensors="pt")
            with torch.no_grad():
                enc_out = audio_model.encoder(inputs.input_features).last_hidden_state.squeeze(0) # [T, 384]
            audio_wavs[rec_id] = enc_out

        enc = audio_wavs[rec_id] # [T, 384]
        total_frames = enc.shape[0]

        # Convert timestamp to frame indices
        t_start = row['start_time']
        t_end = row['end_time']
        f_start = int(round(t_start * 50.0))
        f_end = int(round(t_end * 50.0))

        # Clamp frames
        f_start = max(0, min(total_frames - 1, f_start))
        f_end = max(f_start + 1, min(total_frames, f_end))

        # Mean pool over span
        span_feat = enc[f_start:f_end, :].mean(dim=0).numpy()
        span_features.append(span_feat)

        if (idx + 1) % 50 == 0 or (idx + 1) == len(manifest_df):
            print(f"  Extracted {idx + 1}/{len(manifest_df)} span features ({time.time() - t0:.1f}s)...")

    return np.array(span_features, dtype=np.float32)

def main():
    print("=" * 80)
    print("TRAINING PHASE E1b: DEDICATED SPAN AUDIO PROJECTION HEAD")
    print("=" * 80)
    torch.manual_seed(42)
    np.random.seed(42)

    # 1. Load 300 Spans Manifest
    manifest_path = "Data/training_spans_300.csv"
    if not os.path.exists(manifest_path):
        manifest_path = "C:/Users/ACER/.gemini/antigravity/brain/188b44ec-9425-4d1c-852d-6957627afff6/training_spans_300.csv"
    assert os.path.exists(manifest_path), f"Manifest not found: {manifest_path}"
    
    df_manifest = pd.read_csv(manifest_path)
    print(f"Loaded training manifest: {len(df_manifest)} spans across {df_manifest['term_id'].nunique()} terms.")

    # 2. Extract Raw 384D Span Features
    raw_span_features = extract_all_span_features(df_manifest)
    print(f"Raw Span Features Shape: {raw_span_features.shape} (Norm: {np.linalg.norm(raw_span_features, axis=1).mean():.2f} +/- {np.linalg.norm(raw_span_features, axis=1).std():.2f})")

    # 3. Text Prototype Construction (18 Canonical Train Terms)
    print("\n[Text Prototypes] Constructing frozen 18 canonical text prototypes...")
    train_terms = sorted(list(df_manifest['term_id'].unique()))
    term_to_label = {t: i for i, t in enumerate(train_terms)}

    tok = AutoTokenizer.from_pretrained("google-t5/t5-small")
    text_model = AutoModel.from_pretrained("google-t5/t5-small")
    text_model.eval()

    # Load Base Contrastive Checkpoint to get Text Projection Head
    base_ckpt_path = "Data/models/contrastive_open_vocab/best_contrastive_model.pt"
    base_ckpt = torch.load(base_ckpt_path, map_location="cpu")

    base_model = AudioTextContrastiveModel(audio_in_dim=384, text_in_dim=512, shared_dim=256)
    base_model.load_state_dict(base_ckpt)
    base_model.eval()

    # Freeze Text Branch 100%
    text_proj = base_model.text_proj
    for p in text_proj.parameters():
        p.requires_grad = False
    for p in text_model.parameters():
        p.requires_grad = False

    t_inputs = tok(train_terms, padding=True, truncation=True, return_tensors="pt")
    with torch.no_grad():
        raw_text_embs = text_model.encoder(**t_inputs).last_hidden_state.mean(dim=1) # [18, 512]
        proto_text_embs = text_proj(raw_text_embs) # [18, 256], L2-normalized
    
    print(f"Constructed {proto_text_embs.shape[0]} text prototypes in R^{proto_text_embs.shape[1]} (Norm: {torch.norm(proto_text_embs, dim=-1).mean():.4f})")

    # 4. Initialize Dedicated Span Audio Projection Head
    print("\n[E1b Model] Initializing Dedicated Span Audio Projection Head (384 -> 512 -> 256)...")
    span_audio_head = AudioProjectionHead(in_features=384, shared_dim=256)
    
    # Warm-start weights from global audio_proj for smooth adaptation
    span_audio_head.load_state_dict(base_model.audio_proj.state_dict())
    span_audio_head.train()

    # Learnable temperature
    log_temp = nn.Parameter(torch.tensor(np.log(1.0 / 0.07), dtype=torch.float32))

    optimizer = torch.optim.AdamW(
        list(span_audio_head.parameters()) + [log_temp],
        lr=5e-4,
        weight_decay=1e-4
    )
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=30, eta_min=1e-5)

    dataset = SpanAudioDataset(df_manifest, raw_span_features, term_to_label)
    dataloader = DataLoader(dataset, batch_size=32, shuffle=True, drop_last=False)

    # 5. Training Loop: Supervised Audio-to-Text Prototype Classification Loss
    print("\n--- Starting E1b Training (30 Epochs) ---")
    best_loss = float('inf')
    history = []

    for epoch in range(1, 31):
        span_audio_head.train()
        total_loss = 0.0
        pos_sims = []
        hard_margins = []

        for batch_feats, batch_labels in dataloader:
            optimizer.zero_grad()

            # Project audio spans to shared space (L2-normalized)
            z_audio = span_audio_head(batch_feats) # [B, 256]

            # Compute Cosine Logits with all 18 Text Prototypes: [B, 18]
            tau = torch.clamp(torch.exp(log_temp), min=0.01, max=1.0)
            logits = torch.matmul(z_audio, proto_text_embs.T) / tau # [B, 18]

            # Supervised Audio-to-Text Prototype Classification Loss (Cross-Entropy over 18 prototypes)
            loss = F.cross_entropy(logits, batch_labels)
            loss.backward()
            optimizer.step()

            total_loss += loss.item() * len(batch_labels)

            # Metrics tracking
            with torch.no_grad():
                cos_sims = torch.matmul(z_audio, proto_text_embs.T) # [B, 18]
                for b_i in range(len(batch_labels)):
                    pos_c = cos_sims[b_i, batch_labels[b_i]].item()
                    all_c = cos_sims[b_i].clone()
                    all_c[batch_labels[b_i]] = -999.0
                    hard_neg_c = all_c.max().item()
                    pos_sims.append(pos_c)
                    hard_margins.append(pos_c - hard_neg_c)

        scheduler.step()
        epoch_loss = total_loss / len(dataset)
        mean_pos = np.mean(pos_sims)
        mean_margin = np.mean(hard_margins)
        tau_val = float(torch.clamp(torch.exp(log_temp), min=0.01, max=1.0).item())

        history.append({
            'epoch': epoch,
            'loss': epoch_loss,
            'pos_sim': mean_pos,
            'hard_margin': mean_margin,
            'tau': tau_val
        })

        if epoch % 5 == 0 or epoch == 1:
            print(f"Epoch {epoch:2d}/30 | Loss: {epoch_loss:.4f} | Pos Sim: {mean_pos:+.4f} | Hard Margin: {mean_margin:+.4f} | Tau: {tau_val:.4f}")

        if epoch_loss < best_loss:
            best_loss = epoch_loss
            # Save checkpoint
            save_dict = {
                'epoch': epoch,
                'span_audio_head_state_dict': span_audio_head.state_dict(),
                'text_proj_state_dict': text_proj.state_dict(),
                'log_temp': log_temp.item(),
                'loss': epoch_loss,
                'train_terms': train_terms,
                'term_to_label': term_to_label
            }
            os.makedirs("Data/models", exist_ok=True)
            torch.save(save_dict, "Data/models/e1b_span_model.pt")

    print(f"\nTraining completed! Best Loss: {best_loss:.4f}")
    print("Checkpoint saved to: Data/models/e1b_span_model.pt")

    # Save training log
    with open("Data/models/e1b_training_history.json", "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2)

if __name__ == '__main__':
    main()
