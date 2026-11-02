"""
LiemWhisper Pure Machine Learning: Open-Vocabulary Neural Error Corrector
========================================================================
Performs phonetic and grammatical error correction on code-switched Vietnamese-English
speech recognition output using a fine-tuned Sequence-to-Sequence Transformer (T5 + LoRA).

Design:
- 100% Neural / End-to-End: Does NOT require any dictionary, glossary, or pre-registered taxonomy.
- Parameter-Efficient: Employs LoRA adapter on top of T5-Small.
- Generalizes to out-of-vocabulary terms through context & character/subword phonetic patterns.
"""

import os
import sys
import time
from typing import List, Dict, Any, Optional

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import torch
from transformers import AutoTokenizer, T5ForConditionalGeneration
from peft import PeftModel


class NeuralErrorCorrector:
    """
    Open-Vocabulary Neural Error Corrector for Vietnamese-English code-switched text.
    Uses Sequence-to-Sequence translation:
        Input: "correct: khi chiếm thử api..."
        Output: "Khi kiểm thử API..."
    """
    def __init__(
        self,
        model_dir: Optional[str] = None,
        base_model_name: str = "google-t5/t5-small",
        device: Optional[str] = None
    ):
        if device is None:
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(device)

        # Resolve model directory
        if model_dir is None:
            current_dir = os.path.dirname(os.path.abspath(__file__))
            candidates = [
                os.path.abspath(os.path.join(current_dir, "..", "..", "..", "..", "Data", "models", "neural_corrector_t5_lora")),
                os.path.abspath(os.path.join(current_dir, "..", "..", "..", "..", "..", "Data", "models", "neural_corrector_t5_lora")),
                os.path.abspath(os.path.join(current_dir, "..", "..", "Data", "models", "neural_corrector_t5_lora")),
                "Data/models/neural_corrector_t5_lora"
            ]
            for cand in candidates:
                if os.path.exists(cand) and (os.path.exists(os.path.join(cand, "adapter_model.safetensors")) or os.path.exists(os.path.join(cand, "adapter_config.json"))):
                    model_dir = cand
                    break
            if model_dir is None:
                model_dir = candidates[0]

        self.model_dir = model_dir
        self.base_model_name = base_model_name

        print(f"[NeuralErrorCorrector] Initializing on device: {self.device}...", flush=True)

        # Load Tokenizer
        if os.path.exists(os.path.join(model_dir, "tokenizer_config.json")):
            print(f"[NeuralErrorCorrector] Loading tokenizer from: {model_dir}", flush=True)
            self.tokenizer = AutoTokenizer.from_pretrained(model_dir)
        else:
            print(f"[NeuralErrorCorrector] Loading tokenizer from base: {base_model_name}", flush=True)
            self.tokenizer = AutoTokenizer.from_pretrained(base_model_name)

        # Load Model
        print(f"[NeuralErrorCorrector] Loading base model: {base_model_name}...", flush=True)
        base_model = T5ForConditionalGeneration.from_pretrained(base_model_name)

        adapter_file = os.path.join(model_dir, "adapter_model.safetensors")
        adapter_bin = os.path.join(model_dir, "adapter_model.bin")
        if os.path.exists(adapter_file) or os.path.exists(adapter_bin):
            print(f"[NeuralErrorCorrector] Loading fine-tuned LoRA adapter from: {model_dir}", flush=True)
            self.model = PeftModel.from_pretrained(base_model, model_dir)
        else:
            print(f"[NeuralErrorCorrector] [Notice] Adapter not found at {model_dir}. Using base model.", flush=True)
            self.model = base_model

        self.model.to(self.device)
        self.model.eval()
        print("[NeuralErrorCorrector] Ready for inference.", flush=True)

    def correct(
        self,
        text: str,
        max_new_tokens: int = 128,
        num_beams: int = 2,
        length_penalty: float = 1.0
    ) -> Dict[str, Any]:
        """
        Corrects an ASR output string into clean text.
        Returns a dict with latency, original, and corrected text.
        """
        if not text or not text.strip():
            return {
                "original": text,
                "corrected": text,
                "latency_ms": 0.0
            }

        t0 = time.perf_counter()
        prompt = "correct: " + text.strip()

        inputs = self.tokenizer(prompt, return_tensors="pt", truncation=True, max_length=128).to(self.device)

        with torch.no_grad():
            outputs = self.model.generate(
                input_ids=inputs.input_ids,
                attention_mask=inputs.attention_mask,
                max_new_tokens=max_new_tokens,
                num_beams=num_beams,
                length_penalty=length_penalty,
                early_stopping=True,
                no_repeat_ngram_size=3
            )

        corrected = self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        latency_ms = (time.perf_counter() - t0) * 1000.0

        return {
            "original": text,
            "corrected": corrected,
            "latency_ms": round(latency_ms, 2)
        }

    def correct_text(self, text: str) -> str:
        """Convenience method that returns just the corrected string."""
        return self.correct(text)["corrected"]

    def correct_batch(
        self,
        texts: List[str],
        max_new_tokens: int = 128,
        batch_size: int = 16
    ) -> List[str]:
        """Corrects a batch of texts efficiently."""
        results = []
        for i in range(0, len(texts), batch_size):
            chunk = texts[i:i + batch_size]
            prompts = ["correct: " + t.strip() for t in chunk]
            inputs = self.tokenizer(prompts, return_tensors="pt", padding=True, truncation=True, max_length=128).to(self.device)

            with torch.no_grad():
                outputs = self.model.generate(
                    input_ids=inputs.input_ids,
                    attention_mask=inputs.attention_mask,
                    max_new_tokens=max_new_tokens,
                    num_beams=1, # faster for batch
                    early_stopping=True
                )

            decoded = self.tokenizer.batch_decode(outputs, skip_special_tokens=True)
            results.extend([d.strip() for d in decoded])
        return results
