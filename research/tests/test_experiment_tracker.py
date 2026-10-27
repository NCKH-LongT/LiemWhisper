"""
Unit tests for LiemWhisper Unified Experiment Tracker (W&B / MLflow)
"""
import os
import sys
import pytest
import pandas as pd

src_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "src"))
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from liemwhisper.experiment_tracker import UnifiedExperimentTracker, _clean_num

def test_clean_num():
    assert _clean_num("12.34%") == 12.34
    assert _clean_num("45.6") == 45.6
    assert _clean_num(100) == 100.0
    assert _clean_num(None) == 0.0
    assert _clean_num("invalid") == 0.0

def test_unified_tracker_offline_lifecycle(tmp_path):
    tracker = UnifiedExperimentTracker(
        project_name="test-liemwhisper",
        run_name="unit_test_run",
        backend="both",
        offline=True,
        config={"test_param": 123}
    )

    # 1. Log Params
    tracker.log_params({"lr": 0.001, "batch_size": 4})

    # 2. Log Metrics
    tracker.log_metrics({"train_loss": 0.45, "val_loss": 0.52}, step=1)
    tracker.log_metrics({"train_loss": 0.35, "val_loss": 0.42}, step=2)

    # 3. Log Table
    dummy_df = pd.DataFrame({
        "System": ["B0", "P"],
        "Corpus WER": ["142.88%", "142.14%"],
        "Term F1": ["44.52%", "64.67%"]
    })
    tracker.log_benchmark_comparison(dummy_df)

    # 4. Finish
    tracker.finish()
