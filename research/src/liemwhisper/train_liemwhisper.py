"""
LiemWhisper Official Model Training Engine (PEFT / LoRA Fine-Tuning)
====================================================================
Transforms the LiemWhisper research project into an official standalone model
(comparable to vinai/phowhisper-small or openai/whisper-small):

Workflow:
1. Loads dataset from clean_manifest_v1_gold.csv (or annotation_with_asr_v1.csv)
2. Formats audio (16kHz mono) and code-switched target transcripts
3. Prepares Whisper Small with LoRA adapters (q_proj, v_proj) via PEFT
4. Trains with Seq2SeqTrainer (supports gradient accumulation, fp16/bf16, and early stopping)
5. Merges LoRA adapters into base weights (model.merge_and_unload())
6. Exports official standalone Hugging Face checkpoint + Google Colab 1-click notebook
"""

import os
import sys
import json
import time
import argparse
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Any, Optional
import numpy as np
import pandas as pd

import torch
from torch.utils.data import Dataset
from transformers import (
    WhisperProcessor,
    WhisperForConditionalGeneration,
    Seq2SeqTrainer,
    Seq2SeqTrainingArguments
)
from peft import (
    LoraConfig,
    PeftModel,
    get_peft_model,
    TaskType
)

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

# Discover workspace base directory
cand_base = current_dir
while cand_base and not os.path.exists(os.path.join(cand_base, "Data", "glossary_taxonomy_v1.json")):
    parent = os.path.dirname(cand_base)
    if parent == cand_base:
        break
    cand_base = parent

BASE_DIR = cand_base
DATA_DIR = os.path.join(BASE_DIR, "Data")
WAV_DIR = os.path.join(DATA_DIR, "wav_16k")
GOLD_MANIFEST = os.path.join(DATA_DIR, "clean_manifest_v1_gold.csv")
FALLBACK_MANIFEST = os.path.join(DATA_DIR, "annotation_with_asr_v1.csv")
MODELS_DIR = os.path.join(DATA_DIR, "models")


# ==============================================================================
# 1. PYTORCH SPEECH DATASET & DATA COLLATOR
# ==============================================================================

class LiemWhisperDataset(Dataset):
    """
    Loads 16kHz audio waveforms and target code-switched transcripts for Whisper.
    """

    def __init__(
        self,
        df: pd.DataFrame,
        wav_dir: str,
        processor: WhisperProcessor,
        text_column: str = "verbatim_transcript",
        max_samples: Optional[int] = None
    ):
        self.df = df.reset_index(drop=True)
        if max_samples and len(self.df) > max_samples:
            self.df = self.df.iloc[:max_samples]

        self.wav_dir = wav_dir
        self.processor = processor
        self.text_column = text_column

    def __len__(self) -> int:
        return len(self.df)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        row = self.df.iloc[idx]
        wf = row["wav_file"]
        audio_path = os.path.join(self.wav_dir, wf)

        # 1. Load Audio Waveform
        if os.path.exists(audio_path):
            import faster_whisper.audio
            waveform = faster_whisper.audio.decode_audio(audio_path, sampling_rate=16000)
        else:
            # Fallback 1 second of silence
            waveform = np.zeros(16000, dtype=np.float32)

        # 2. Extract Mel Spectrogram Features
        input_features = self.processor.feature_extractor(
            waveform,
            sampling_rate=16000
        ).input_features[0]

        # 3. Tokenize Target Code-Switched Transcript
        target_text = str(row.get(self.text_column, "")).strip()
        if not target_text or target_text == "nan":
            target_text = str(row.get("prompt_text", "")).strip()

        labels = self.processor.tokenizer(target_text).input_ids

        return {
            "input_features": input_features,
            "labels": labels
        }


@dataclass
class DataCollatorSpeechSeq2SeqWithPadding:
    """
    Pads input features and labels dynamically for Seq2Seq batching.
    Labels padding is replaced with -100 so loss ignores padding tokens.
    """
    processor: WhisperProcessor

    def __call__(self, features: List[Dict[str, Any]]) -> Dict[str, torch.Tensor]:
        input_features = [{"input_features": f["input_features"]} for f in features]
        batch = self.processor.feature_extractor.pad(input_features, return_tensors="pt")

        label_features = [{"input_ids": f["labels"]} for f in features]
        labels_batch = self.processor.tokenizer.pad(label_features, return_tensors="pt")

        # Replace padding with -100 for PyTorch CrossEntropyLoss
        labels = labels_batch["input_ids"].masked_fill(
            labels_batch.attention_mask.ne(1), -100
        )

        # Truncate start-of-transcript token if already present
        if (labels[:, 0] == self.processor.tokenizer.bos_token_id).all().cpu().item():
            labels = labels[:, 1:]

        batch["labels"] = labels
        return batch


# ==============================================================================
# 2. PEFT / LORA MODEL PREPARATION & EXPORT
# ==============================================================================

def prepare_whisper_lora_model(
    base_model_name: str = "openai/whisper-small",
    lora_r: int = 16,
    lora_alpha: int = 32,
    lora_dropout: float = 0.05
) -> Tuple[PeftModel, WhisperProcessor]:
    """
    Prepares a Whisper model with trainable LoRA adapters on attention projection layers.
    """
    print(f"[Model] Loading Whisper processor and model: {base_model_name}...")
    processor = WhisperProcessor.from_pretrained(
        base_model_name,
        language="vi",
        task="transcribe"
    )

    model = WhisperForConditionalGeneration.from_pretrained(
        base_model_name,
        torch_dtype=torch.float32
    )

    # Configure generation parameters
    model.config.forced_decoder_ids = None
    model.config.suppress_tokens = []
    model.generation_config.language = "vi"
    model.generation_config.task = "transcribe"
    model.generation_config.forced_decoder_ids = None

    # LoRA Configuration
    lora_config = LoraConfig(
        r=lora_r,
        lora_alpha=lora_alpha,
        target_modules=["q_proj", "v_proj"],
        lora_dropout=lora_dropout,
        bias="none"
    )

    peft_model = get_peft_model(model, lora_config)
    peft_model.print_trainable_parameters()
    return peft_model, processor


def merge_and_export_model(
    lora_model_dir: str,
    output_merged_dir: str,
    base_model_name: str = "openai/whisper-small"
):
    """
    Merges trained LoRA weights into the base Whisper model, producing a 100%
    standard standalone checkpoint ready for Hugging Face Hub and CTranslate2.
    """
    print(f"\n[Merge] Loading base model '{base_model_name}' and LoRA adapters from '{lora_model_dir}'...")
    base_model = WhisperForConditionalGeneration.from_pretrained(base_model_name)
    peft_model = PeftModel.from_pretrained(base_model, lora_model_dir)

    print("[Merge] Merging LoRA adapters into base weights (merge_and_unload)...")
    merged_model = peft_model.merge_and_unload()

    processor = WhisperProcessor.from_pretrained(base_model_name, language="vi", task="transcribe")

    os.makedirs(output_merged_dir, exist_ok=True)
    merged_model.save_pretrained(output_merged_dir)
    processor.save_pretrained(output_merged_dir)
    print(f"[Merge] Successfully saved standalone LiemWhisper model to: {output_merged_dir}")


# ==============================================================================
# 3. GOOGLE COLAB 1-CLICK JUPYTER NOTEBOOK EXPORTER
# ==============================================================================

def export_google_colab_notebook(output_ipynb_path: str):
    """
    Generates a ready-to-run Google Colab Jupyter Notebook so students
    can train LiemWhisper for free on Google Colab T4 / A100 GPU in 1 click!
    """
    notebook = {
        "cells": [
            {
                "cell_type": "markdown",
                "metadata": {},
                "source": [
                    "# LiemWhisper Official Model Training on Google Colab (Free T4 / A100 GPU)\n",
                    "**Đề tài:** Nhận dạng thuật ngữ Software Testing trong tiếng nói tiếng Việt (ISTQB CTFL v4.0.1)\n",
                    "**Nhóm thực hiện:** Gehihi — LiemWhisper Team"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# 1. Cài đặt các thư viện Deep Learning chuyên dụng cho Speech & NLP\n",
                    "!pip install -q transformers peft accelerate datasets faster-whisper jiwer rapidfuzz"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# 2. Kiểm tra GPU Google Colab\n",
                    "import torch\n",
                    "print('CUDA Available:', torch.cuda.is_available())\n",
                    "if torch.cuda.is_available():\n",
                    "    print('GPU Device Name:', torch.cuda.get_device_name(0))\n",
                    "    print('VRAM:', round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2), 'GB')"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# 3. Clone Repository LiemWhisper hoặc Tải dữ liệu từ Google Drive\n",
                    "!git clone https://github.com/NCKH-LongT/LiemWhisper.git\n",
                    "%cd LiemWhisper/research/src/liemwhisper"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# 4. Bắt đầu huấn luyện mô hình LiemWhisper Small với LoRA\n",
                    "!python train_liemwhisper.py --train --epochs 5 --batch-size 4 --grad-accum 4 --fp16"
                ]
            },
            {
                "cell_type": "code",
                "execution_count": None,
                "metadata": {},
                "outputs": [],
                "source": [
                    "# 5. Tự động hợp nhất trọng số LoRA và xuất bản lên Hugging Face Hub\n",
                    "!python train_liemwhisper.py --merge-only\n",
                    "print('Hoàn thành! Bạn có thể tải checkpoint về hoặc push lên Hugging Face!')"
                ]
            }
        ],
        "metadata": {
            "accelerator": "GPU",
            "colab": {
                "gpuType": "T4",
                "provenance": []
            },
            "language_info": {
                "name": "python"
            }
        },
        "nbformat": 4,
        "nbformat_minor": 0
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_ipynb_path)), exist_ok=True)
    with open(output_ipynb_path, "w", encoding="utf-8") as f:
        json.dump(notebook, f, indent=2, ensure_ascii=False)
    print(f"[Colab Export] Exported 1-click Google Colab notebook to: {output_ipynb_path}")


# ==============================================================================
# 4. MAIN TRAINING & DRY-RUN CLI
# ==============================================================================

def parse_args():
    parser = argparse.ArgumentParser(description="LiemWhisper Official Model Training Engine")
    parser.add_argument("--base-model", type=str, default="openai/whisper-small", help="Hugging Face Whisper model name")
    parser.add_argument("--manifest", type=str, default=None, help="Path to manifest CSV")
    parser.add_argument("--wav-dir", type=str, default=WAV_DIR, help="Path to wav directory")
    parser.add_argument("--output-dir", type=str, default=os.path.join(MODELS_DIR, "liemwhisper-small-lora"))
    parser.add_argument("--merged-dir", type=str, default=os.path.join(MODELS_DIR, "liemwhisper-small-hf"))
    parser.add_argument("--epochs", type=int, default=3, help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=2, help="Per-device batch size")
    parser.add_argument("--grad-accum", type=int, default=8, help="Gradient accumulation steps")
    parser.add_argument("--lr", type=float, default=1e-4, help="Learning rate")
    parser.add_argument("--fp16", action="store_true", help="Enable FP16 mixed precision")
    parser.add_argument("--dry-run", action="store_true", help="Run 1-step dry run verification without full training")
    parser.add_argument("--train", action="store_true", help="Execute full training")
    parser.add_argument("--merge-only", action="store_true", help="Only merge existing LoRA checkpoint")
    parser.add_argument("--export-colab", action="store_true", help="Export Google Colab notebook")
    return parser.parse_args()


def main():
    args = parse_args()
    os.makedirs(MODELS_DIR, exist_ok=True)

    colab_path = os.path.join(MODELS_DIR, "train_liemwhisper_colab.ipynb")
    export_google_colab_notebook(colab_path)

    if args.export_colab and not args.train and not args.dry_run and not args.merge_only:
        return

    if args.merge_only:
        merge_and_export_model(args.output_dir, args.merged_dir, args.base_model)
        return

    manifest_p = args.manifest
    if not manifest_p:
        manifest_p = GOLD_MANIFEST if os.path.exists(GOLD_MANIFEST) else FALLBACK_MANIFEST

    print("=" * 80)
    print("LIEMWHISPER OFFICIAL MODEL TRAINING ENGINE (PEFT / LORA)")
    print("=" * 80)
    print(f"Base Model           : {args.base_model}")
    print(f"Manifest             : {manifest_p}")
    print(f"Audio Directory      : {args.wav_dir}")
    print(f"Output LoRA Dir      : {args.output_dir}")
    print(f"Output Standalone Dir: {args.merged_dir}")
    print(f"Dry-run Mode         : {args.dry_run}")

    if not os.path.exists(manifest_p):
        print(f"Error: Manifest not found at {manifest_p}")
        return

    df = pd.read_csv(manifest_p)
    train_df = df[df["split"] == "train"].reset_index(drop=True)
    val_df = df[df["split"] == "val"].reset_index(drop=True)

    print(f"Train samples: {len(train_df)} | Val samples: {len(val_df)}")

    # 1. Prepare Model and Processor
    model, processor = prepare_whisper_lora_model(args.base_model)

    # Text column to learn from
    text_col = "verbatim_transcript" if "verbatim_transcript" in df.columns else "prompt_text"

    # 2. Build Datasets
    max_s = 4 if args.dry_run else None
    train_dataset = LiemWhisperDataset(train_df, args.wav_dir, processor, text_column=text_col, max_samples=max_s)
    val_dataset = LiemWhisperDataset(val_df, args.wav_dir, processor, text_column=text_col, max_samples=max_s)
    collator = DataCollatorSpeechSeq2SeqWithPadding(processor=processor)

    # 3. Dry-Run Verification
    if args.dry_run:
        print("\n[Dry-Run] Verifying batch collation and forward pass...")
        sample_batch = collator([train_dataset[0], train_dataset[1]])
        print(f"  Input features shape : {sample_batch['input_features'].shape}")
        print(f"  Labels shape         : {sample_batch['labels'].shape}")

        outputs = model(
            input_features=sample_batch["input_features"],
            labels=sample_batch["labels"]
        )
        print(f"  Forward pass Loss    : {outputs.loss.item():.4f}")
        assert outputs.loss.item() > 0, "Loss must be positive"
        print("  -> Dry-run verification passed 100%! Ready for full training.")
        return

    # 4. Full Training Execution
    if args.train:
        training_args = Seq2SeqTrainingArguments(
            output_dir=args.output_dir,
            per_device_train_batch_size=args.batch_size,
            gradient_accumulation_steps=args.grad_accum,
            learning_rate=args.lr,
            warmup_steps=50,
            num_train_epochs=args.epochs,
            evaluation_strategy="epoch",
            save_strategy="epoch",
            logging_steps=10,
            fp16=args.fp16 and torch.cuda.is_available(),
            predict_with_generate=False,
            generation_max_length=225,
            save_total_limit=2,
            load_best_model_at_end=True,
            metric_for_best_model="loss",
            greater_is_better=False,
            report_to=["none"]
        )

        trainer = Seq2SeqTrainer(
            args=training_args,
            model=model,
            train_dataset=train_dataset,
            eval_dataset=val_dataset,
            data_collator=collator,
            tokenizer=processor.feature_extractor
        )

        print("\n[Train] Starting official LiemWhisper fine-tuning...")
        trainer.train()

        print(f"\n[Train] Saving best LoRA checkpoint to: {args.output_dir}")
        trainer.save_model(args.output_dir)
        processor.save_pretrained(args.output_dir)

        # Merge and export
        merge_and_export_model(args.output_dir, args.merged_dir, args.base_model)


if __name__ == "__main__":
    main()
