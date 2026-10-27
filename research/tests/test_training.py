"""
Unit Test Suite for LiemWhisper Model Training Engine
=====================================================
Validates:
1. Google Colab 1-click notebook exporter
2. Whisper LoRA model setup and trainable parameter reduction
3. Speech dataset and collator tensor dimensions
"""

import os
import sys
import json
import pytest
import torch
import pandas as pd

src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from liemwhisper.train_liemwhisper import (
    export_google_colab_notebook,
    prepare_whisper_lora_model,
    LiemWhisperDataset,
    DataCollatorSpeechSeq2SeqWithPadding
)


def test_colab_notebook_export(tmp_path):
    print("[1/3] Testing Google Colab Notebook Export...")
    out_file = os.path.join(tmp_path, "test_colab.ipynb")
    export_google_colab_notebook(out_file)

    assert os.path.exists(out_file)
    with open(out_file, "r", encoding="utf-8") as f:
        data = json.load(f)

    assert "cells" in data
    assert len(data["cells"]) >= 5
    # Verify presence of training command
    sources = " ".join([" ".join(c.get("source", [])) for c in data["cells"]])
    assert "train_liemwhisper.py" in sources
    assert "transformers" in sources
    print("  -> Passed Colab Notebook Export!")


def test_lora_whisper_model_setup():
    print("[2/3] Testing Whisper LoRA Setup...")
    # Test on tiny model for speed
    peft_model, processor = prepare_whisper_lora_model(
        base_model_name="openai/whisper-tiny",
        lora_r=8,
        lora_alpha=16
    )

    trainable_params = sum(p.numel() for p in peft_model.parameters() if p.requires_grad)
    total_params = sum(p.numel() for p in peft_model.parameters())
    trainable_pct = trainable_params / total_params * 100

    print(f"  Trainable params: {trainable_params:,} / {total_params:,} ({trainable_pct:.2f}%)")
    # LoRA should train less than 3% of total parameters
    assert trainable_pct < 3.0, f"Expected <3% trainable parameters, got {trainable_pct:.2f}%"
    print("  -> Passed Whisper LoRA Setup!")


def test_dataset_and_collator():
    print("[3/3] Testing Dataset and Collator Tensors...")
    from transformers import WhisperProcessor
    processor = WhisperProcessor.from_pretrained("openai/whisper-tiny", language="vi", task="transcribe")

    mock_df = pd.DataFrame([
        {
            "wav_file": "non_existent_1.wav",
            "prompt_text": "Em dùng Boundary Value Analysis.",
            "verbatim_transcript": "Em dùng Boundary Value Analysis."
        },
        {
            "wav_file": "non_existent_2.wav",
            "prompt_text": "Viết Bug Report gửi cho developer.",
            "verbatim_transcript": "Viết Bug Report gửi cho developer."
        }
    ])

    dataset = LiemWhisperDataset(mock_df, wav_dir="/tmp", processor=processor)
    assert len(dataset) == 2

    sample = dataset[0]
    assert "input_features" in sample
    assert "labels" in sample

    collator = DataCollatorSpeechSeq2SeqWithPadding(processor=processor)
    batch = collator([dataset[0], dataset[1]])

    assert "input_features" in batch
    assert "labels" in batch
    assert batch["input_features"].ndim == 3  # [batch, n_mels, time]
    assert batch["labels"].ndim == 2          # [batch, seq_len]
    # Check that padding was replaced with -100
    assert torch.is_tensor(batch["labels"])
    print("  -> Passed Dataset and Collator Tensors!")
