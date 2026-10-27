"""
Unit Tests for Latency, Throughput & Real-Time Factor (RTF) Benchmark Engine
============================================================================
"""

import os
import sys
import pytest
import pandas as pd
import numpy as np

current_dir = os.path.dirname(os.path.abspath(__file__))
src_dir = os.path.abspath(os.path.join(current_dir, "..", "src", "liemwhisper"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from benchmark_latency_rtf import (
    get_hardware_info,
    sample_representative_test_set
)


def test_get_hardware_info():
    info = get_hardware_info()
    assert isinstance(info, dict)
    assert "os" in info
    assert "cpu_count_logical" in info
    assert info["cpu_count_logical"] >= 1
    assert "python_version" in info


def test_sample_representative_test_set():
    mock_data = []
    durations = [4.5, 8.2, 12.0, 15.5, 22.0, 31.0]
    for i, d in enumerate(durations * 5):
        mock_data.append({
            "recording_id": f"rec_{i:03d}",
            "speaker_id": f"spk_{i%3}",
            "wav_file": f"rec_{i:03d}.wav",
            "duration_seconds": d,
            "split": "test"
        })
    df = pd.DataFrame(mock_data)

    samples = sample_representative_test_set(df, n_samples=6)
    assert len(samples) == 6
    rec_ids = [s["recording_id"] for s in samples]
    assert len(set(rec_ids)) == 6

    # Verify presence of multiple duration brackets
    durs = [s["duration_seconds"] for s in samples]
    assert any(d < 10 for d in durs)
    assert any(10 <= d <= 20 for d in durs)
    assert any(d > 20 for d in durs)


def test_rtf_and_speedup_math():
    audio_duration = 20.0  # 20 seconds
    e2e_ms = 4000.0  # 4 seconds
    e2e_sec = e2e_ms / 1000.0

    rtf = e2e_sec / audio_duration
    assert rtf == pytest.approx(0.20, abs=1e-4)

    speedup = 1.0 / rtf
    assert speedup == pytest.approx(5.0, abs=1e-4)  # 5x faster than real-time

    throughput = 1000.0 / e2e_ms
    assert throughput == pytest.approx(0.25, abs=1e-4)  # 0.25 utterances per second
