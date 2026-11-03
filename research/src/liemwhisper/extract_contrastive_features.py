"""
LiemWhisper Open-Vocabulary: Offline Feature Extractor
=====================================================
Extracts:
1. Audio acoustic representations via Whisper-tiny encoder (d=384).
2. Canonical text representations via T5-small encoder (d=512).
3. Partitions samples into Train (18 terms) and Unseen Test (6 terms) with zero leakage.
"""

import os
import sys
import json
import time
import numpy as np
import pandas as pd
import soundfile as sf
import torch

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from transformers import WhisperModel, WhisperFeatureExtractor, AutoTokenizer, AutoModel

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from open_vocab_contrastive import UNSEEN_TEST_TERMS, partition_dataset_by_terms


def extract_features(
    csv_path: str = "Data/gold_with_asr_v1.csv",
    wav_dir: str = "Data/wav_16k",
    output_dir: str = "Data/features_contrastive",
    samples_per_prompt: int = 35
):
    print("=" * 80)
    print("EXTRACTING CONTRASTIVE EMBEDDINGS (AUDIO & TEXT)")
    print("=" * 80)
    os.makedirs(output_dir, exist_ok=True)

    # 1. Load and Partition Dataset
    print(f"[Dataset] Loading {csv_path}...")
    df = pd.read_csv(csv_path)

    # Sample balanced subset across prompts for high speed & speaker diversity
    balanced_rows = []
    for pid, group in df.groupby("prompt_id"):
        balanced_rows.append(group.head(samples_per_prompt))
    df_balanced = pd.concat(balanced_rows, ignore_index=True)
    print(f"[Dataset] Sampled {len(df_balanced)} balanced audio files across 15 prompts.")

    train_df, test_df, train_terms, test_terms = partition_dataset_by_terms(df_balanced, UNSEEN_TEST_TERMS)
    print(f"[Partition] Train: {len(train_df)} audios (18 terms: {train_terms[:4]}...)")
    print(f"[Partition] Unseen Test: {len(test_df)} audios (6 terms: {test_terms})")

    # 2. Extract Text Embeddings for All 24 Canonical Terms
    print("\n[Text Encoder] Loading T5-small text encoder...")
    tok = AutoTokenizer.from_pretrained("google-t5/t5-small")
    text_model = AutoModel.from_pretrained("google-t5/t5-small")
    text_model.eval()

    all_terms = sorted(list(set(train_terms + test_terms)))
    print(f"[Text Encoder] Encoding {len(all_terms)} canonical terms...")
    t_inputs = tok(all_terms, padding=True, truncation=True, return_tensors="pt")
    with torch.no_grad():
        term_text_embs = text_model.encoder(**t_inputs).last_hidden_state.mean(dim=1).numpy()
    print(f"[Text Encoder] Output shape: {term_text_embs.shape}")

    term_to_idx = {t: i for i, t in enumerate(all_terms)}
    with open(os.path.join(output_dir, "terms_meta.json"), "w", encoding="utf-8") as f:
        json.dump({
            "all_terms": all_terms,
            "train_terms": train_terms,
            "test_terms": test_terms,
            "term_to_idx": term_to_idx
        }, f, indent=2, ensure_ascii=False)

    np.save(os.path.join(output_dir, "term_text_embs.npy"), term_text_embs)

    # 3. Extract Audio Embeddings via Whisper Encoder
    print("\n[Audio Encoder] Loading Whisper-tiny acoustic encoder...")
    fe = WhisperFeatureExtractor.from_pretrained("openai/whisper-tiny")
    audio_model = WhisperModel.from_pretrained("openai/whisper-tiny")
    audio_model.eval()

    def process_split(split_df: pd.DataFrame, split_name: str):
        print(f"\n[Audio Encoder] Processing {split_name} ({len(split_df)} files)...")
        audio_embs = []
        target_indices = []
        valid_filenames = []
        t0 = time.time()

        for idx, row in split_df.iterrows():
            wav_path = os.path.join(wav_dir, row["wav_file"])
            if not os.path.exists(wav_path):
                continue
            try:
                wav, sr = sf.read(wav_path)
                inputs = fe(wav, sampling_rate=sr, return_tensors="pt")
                with torch.no_grad():
                    # Whisper encoder last hidden state [1, T, 384]
                    enc_out = audio_model.encoder(inputs.input_features).last_hidden_state
                    pooled = enc_out.mean(dim=1).squeeze(0).numpy()
                audio_embs.append(pooled)
                valid_filenames.append(row["wav_file"])

                # Primary target term
                gt = str(row.get("gold_terms", "")).split(";")[0].strip().title()
                t_idx = term_to_idx.get(gt, 0)
                target_indices.append(t_idx)

                if len(audio_embs) % 50 == 0:
                    print(f"  Processed {len(audio_embs)}/{len(split_df)} files ({time.time()-t0:.1f}s)...")
            except Exception as e:
                print(f"  Error on {wav_path}: {e}")

        embs_arr = np.array(audio_embs, dtype=np.float32)
        targets_arr = np.array(target_indices, dtype=np.int64)

        np.save(os.path.join(output_dir, f"{split_name}_audio_embs.npy"), embs_arr)
        np.save(os.path.join(output_dir, f"{split_name}_targets.npy"), targets_arr)
        with open(os.path.join(output_dir, f"{split_name}_files.json"), "w", encoding="utf-8") as f:
            json.dump(valid_filenames, f, indent=2)

        print(f"[Audio Encoder] Saved {split_name} features: shape {embs_arr.shape}")

    process_split(train_df, "train")
    process_split(test_df, "test")

    print("\n" + "=" * 80)
    print(f"[SUCCESS] All features successfully extracted and saved to: {output_dir}")
    print("=" * 80)


if __name__ == "__main__":
    extract_features()
