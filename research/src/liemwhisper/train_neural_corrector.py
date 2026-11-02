"""
LiemWhisper Open-Vocabulary Neural Error Corrector: Training Script
===================================================================
Fine-tunes a Sequence-to-Sequence Transformer (T5-Small) using LoRA
to map corrupted Vietnamese-English code-switched ASR text directly to clean text.

Features:
- Pure Deep Learning: Zero dictionary lookup, zero taxonomy constraints.
- Parameter-Efficient: LoRA trains only ~0.5% of model weights (<300K params).
- Memory-Safe: Runs stably on CPU / CUDA with pre-tokenized batching.
"""

import os
import sys
import json
import time
import math
from typing import List, Dict, Any

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import torch
from torch.utils.data import TensorDataset, DataLoader
from transformers import AutoTokenizer, T5ForConditionalGeneration
from peft import LoraConfig, get_peft_model, TaskType


def load_tokenized_dataset(jsonl_path: str, tokenizer, max_samples: int = 1200, max_len: int = 96):
    """Loads and pre-tokenizes samples in batch for zero overhead during training."""
    with open(jsonl_path, "r", encoding="utf-8") as f:
        samples = [json.loads(line) for line in f if line.strip()][:max_samples]

    src_texts = ["correct: " + s["input_text"] for s in samples]
    tgt_texts = [s["target_text"] for s in samples]

    src_enc = tokenizer(src_texts, max_length=max_len, padding="max_length", truncation=True, return_tensors="pt")
    tgt_enc = tokenizer(tgt_texts, max_length=max_len, padding="max_length", truncation=True, return_tensors="pt")

    labels = tgt_enc.input_ids
    labels[labels == tokenizer.pad_token_id] = -100

    return TensorDataset(src_enc.input_ids, src_enc.attention_mask, labels)


def train_neural_corrector(
    base_model_name: str = "google-t5/t5-small",
    data_dir: str = None,
    output_model_dir: str = None,
    total_steps: int = 150,
    batch_size: int = 8,
    lr: float = 2e-3,
    lora_r: int = 8,
    lora_alpha: int = 32
):
    print("=" * 80, flush=True)
    print("LIEMWHISPER: TRAINING OPEN-VOCABULARY NEURAL SEQ2SEQ ERROR CORRECTOR", flush=True)
    print("=" * 80, flush=True)

    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, "..", "..", "..", ".."))

    if data_dir is None:
        data_dir = os.path.join(project_root, "Data", "synthetic_neural_corpus")
    if output_model_dir is None:
        output_model_dir = os.path.join(project_root, "Data", "models", "neural_corrector_t5_lora")

    train_path = os.path.join(data_dir, "train.jsonl")
    val_path = os.path.join(data_dir, "val.jsonl")

    device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    print(f"[Device] Using device: {device}", flush=True)

    print(f"[Model] Loading base model: {base_model_name}...", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(base_model_name)
    base_model = T5ForConditionalGeneration.from_pretrained(base_model_name)

    print(f"[LoRA] Attaching LoRA adapter (r={lora_r}, alpha={lora_alpha})...", flush=True)
    peft_config = LoraConfig(
        task_type=TaskType.SEQ_2_SEQ_LM,
        inference_mode=False,
        r=lora_r,
        lora_alpha=lora_alpha,
        lora_dropout=0.1,
        target_modules=["q", "v"]
    )
    model = get_peft_model(base_model, peft_config)
    model.print_trainable_parameters()
    model.to(device)

    print("[Dataset] Pre-tokenizing train & val datasets...", flush=True)
    train_dataset = load_tokenized_dataset(train_path, tokenizer, max_samples=1000, max_len=96)
    val_dataset = load_tokenized_dataset(val_path, tokenizer, max_samples=150, max_len=96)

    train_loader = DataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    print(f"[Dataset] Train samples: {len(train_dataset)}, Val samples: {len(val_dataset)}", flush=True)

    optimizer = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=0.01)
    best_val_loss = float("inf")
    os.makedirs(output_model_dir, exist_ok=True)

    print(f"\n[Training] Commencing training for {total_steps} steps (batch_size={batch_size})...", flush=True)
    step = 0
    t_start = time.time()
    train_iter = iter(train_loader)

    while step < total_steps:
        step += 1
        model.train()

        try:
            batch = next(train_iter)
        except StopIteration:
            train_iter = iter(train_loader)
            batch = next(train_iter)

        b_in, b_mask, b_lab = [t.to(device) for t in batch]

        optimizer.zero_grad()
        loss = model(input_ids=b_in, attention_mask=b_mask, labels=b_lab).loss
        loss.backward()
        torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)
        optimizer.step()

        if step % 10 == 0 or step == total_steps:
            elapsed = time.time() - t_start
            print(f"  Step [{step:3d}/{total_steps}] | Train Loss: {loss.item():.4f} | Time: {elapsed:.1f}s", flush=True)

        if step % 30 == 0 or step == total_steps:
            # Validation pass
            model.eval()
            total_val_loss = 0.0
            with torch.no_grad():
                for v_batch in val_loader:
                    v_in, v_mask, v_lab = [t.to(device) for t in v_batch]
                    v_loss = model(input_ids=v_in, attention_mask=v_mask, labels=v_lab).loss
                    total_val_loss += v_loss.item()
            avg_val_loss = total_val_loss / len(val_loader)
            print(f"  --> Evaluation @ Step {step:3d} | Val Loss: {avg_val_loss:.4f}", flush=True)

            if avg_val_loss < best_val_loss:
                best_val_loss = avg_val_loss
                print(f"  [Checkpoint] Saving best adapter to {output_model_dir} (val_loss: {best_val_loss:.4f})...", flush=True)
                model.save_pretrained(output_model_dir)
                tokenizer.save_pretrained(output_model_dir)

    print("\n" + "=" * 80, flush=True)
    print(f"[SUCCESS] Neural Corrector training complete! Best Val Loss: {best_val_loss:.4f}", flush=True)
    print(f"LoRA Adapter saved at: {output_model_dir}", flush=True)
    print("=" * 80, flush=True)


if __name__ == "__main__":
    train_neural_corrector(
        base_model_name="google-t5/t5-small",
        total_steps=120,
        batch_size=8,
        lr=2e-3
    )
