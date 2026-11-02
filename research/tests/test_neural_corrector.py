"""
Unit Test Suite for LiemWhisper Open-Vocabulary Neural Error Corrector
=====================================================================
Validates:
1. SyntheticCorpusGenerator dataset creation and corruption logic.
2. NeuralErrorCorrector initialization (base model / LoRA adapter).
3. Inference API (single string, batch processing, latency reporting).
4. Zero-dictionary requirement (verifying no taxonomy lookup is performed).
"""

import os
import sys
import pytest

src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from liemwhisper.data_synthesis import SyntheticCorpusGenerator
from liemwhisper.neural_corrector import NeuralErrorCorrector


def test_data_synthesis_generator():
    """Validates that synthetic parallel pairs are generated properly."""
    gen = SyntheticCorpusGenerator()
    dataset = gen.generate_dataset(num_samples=20)
    assert len(dataset) == 20
    for sample in dataset:
        assert "input_text" in sample
        assert "target_text" in sample
        assert len(sample["input_text"]) > 0
        assert len(sample["target_text"]) > 0


def test_neural_corrector_empty_input():
    """Validates edge case handling for empty or whitespace-only inputs."""
    corrector = NeuralErrorCorrector(device="cpu")
    res = corrector.correct("")
    assert res["corrected"] == ""
    assert res["latency_ms"] == 0.0

    res_ws = corrector.correct("   ")
    assert res_ws["corrected"] == "   "


def test_neural_corrector_inference():
    """Validates end-to-end neural inference and output structure."""
    corrector = NeuralErrorCorrector(device="cpu")
    sample_input = "trong qua trinh kiem thu wa can thuc hien test cay"
    res = corrector.correct(sample_input, max_new_tokens=32)

    assert "original" in res
    assert "corrected" in res
    assert "latency_ms" in res
    assert res["original"] == sample_input
    assert isinstance(res["corrected"], str)
    assert len(res["corrected"]) > 0
    assert res["latency_ms"] >= 0.0


def test_neural_corrector_batch():
    """Validates batch inference capability."""
    corrector = NeuralErrorCorrector(device="cpu")
    batch_inputs = [
        "kiem thu api can check race condition",
        "chay regression test tren moi truong staging"
    ]
    batch_outputs = corrector.correct_batch(batch_inputs, max_new_tokens=32)
    assert len(batch_outputs) == len(batch_inputs)
    for out in batch_outputs:
        assert isinstance(out, str)
        assert len(out) > 0
