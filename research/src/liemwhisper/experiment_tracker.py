"""
LiemWhisper Unified Experiment Tracking Engine (W&B / MLflow)
============================================================
Provides unified, publication-grade experiment tracking for:
- Weights & Biases (W&B): Cloud/offline dashboards, Loss curves, and exportable vector plots.
- MLflow: Local-first experiment tracking with zero-setup UI (stored in Data/mlruns/).

Supports:
1. Tracking LoRA training metrics (train/val loss, learning rate, GPU memory).
2. Tracking Table 4.4 and Table 4.5 comparative benchmark metrics (WER, CER, Term F1, HCR, RTF, Latency).
3. 100% offline safety fallback (never crashes or hangs if internet or API key is absent).
"""

import os
import sys
import argparse
from typing import Dict, Any, Optional, List, Union
import pandas as pd
import numpy as np

# Suppress MLflow telemetry banner
os.environ["MLFLOW_DISABLE_AGENT_HINT"] = "1"

# Discover base directories
current_dir = os.path.dirname(os.path.abspath(__file__))
cand_base = current_dir
while cand_base and not os.path.exists(os.path.join(cand_base, "Data", "glossary_taxonomy_v1.json")):
    parent = os.path.dirname(cand_base)
    if parent == cand_base:
        break
    cand_base = parent

BASE_DIR = cand_base
DATA_DIR = os.path.join(BASE_DIR, "Data")
MLFLOW_DB = os.path.join(DATA_DIR, "mlflow.db")
MLRUNS_DIR = os.path.join(DATA_DIR, "mlruns")


def _clean_num(val: Any) -> float:
    if val is None or pd.isna(val):
        return 0.0
    s = str(val).replace("%", "").strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


class UnifiedExperimentTracker:
    """
    Unified experiment tracker supporting W&B and MLflow simultaneously or independently.
    """

    def __init__(
        self,
        project_name: str = "liemwhisper",
        run_name: Optional[str] = None,
        backend: str = "both",  # 'wandb', 'mlflow', 'both', 'none'
        offline: bool = False,
        config: Optional[Dict[str, Any]] = None
    ):
        self.project_name = project_name
        self.run_name = run_name or f"run_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}"
        self.backend = backend.lower()
        self.offline = offline
        self.config = config or {}

        self.wandb_run = None
        self.mlflow_run = None

        self._init_backends()

    def _init_backends(self):
        # 1. Initialize Weights & Biases
        if self.backend in ["wandb", "both"]:
            try:
                import wandb
                # If offline requested or no WANDB_API_KEY, use offline mode to avoid interactive prompt
                if self.offline or not os.environ.get("WANDB_API_KEY"):
                    os.environ["WANDB_MODE"] = "offline"

                self.wandb_run = wandb.init(
                    project=self.project_name,
                    name=self.run_name,
                    config=self.config,
                    reinit=True
                )
                print(f"[W&B] Initialized run '{self.run_name}' (mode: {os.environ.get('WANDB_MODE', 'online')})")
            except Exception as e:
                print(f"[W&B] Warning: Failed to initialize W&B ({e}). Skipping W&B.")
                self.wandb_run = None

        # 2. Initialize MLflow
        if self.backend in ["mlflow", "both"]:
            try:
                import mlflow
                os.makedirs(DATA_DIR, exist_ok=True)
                db_uri = f"sqlite:///{os.path.abspath(MLFLOW_DB).replace(os.sep, '/')}"
                mlflow.set_tracking_uri(db_uri)
                mlflow.set_experiment(self.project_name)
                self.mlflow_run = mlflow.start_run(run_name=self.run_name)
                if self.config:
                    # Flatten config dict for MLflow params
                    flat_params = {k: str(v) for k, v in self.config.items() if not isinstance(v, (dict, list))}
                    mlflow.log_params(flat_params)
                print(f"[MLflow] Initialized run '{self.run_name}' with SQLite store: {MLFLOW_DB}")
            except Exception as e:
                print(f"[MLflow] Warning: Failed to initialize MLflow ({e}). Skipping MLflow.")
                self.mlflow_run = None

    def log_params(self, params: Dict[str, Any]):
        """Logs hyperparameters or metadata."""
        if self.wandb_run is not None:
            import wandb
            wandb.config.update(params, allow_val_change=True)

        if self.mlflow_run is not None:
            import mlflow
            flat = {str(k): str(v) for k, v in params.items() if not isinstance(v, (dict, list))}
            mlflow.log_params(flat)

    def log_metrics(self, metrics: Dict[str, Union[float, int]], step: Optional[int] = None):
        """Logs numerical scalar metrics."""
        clean_metrics = {}
        for k, v in metrics.items():
            if isinstance(v, (int, float, np.integer, np.floating)):
                clean_metrics[k] = float(v)

        if self.wandb_run is not None:
            import wandb
            if step is not None:
                wandb.log(clean_metrics, step=step)
            else:
                wandb.log(clean_metrics)

        if self.mlflow_run is not None:
            import mlflow
            for k, v in clean_metrics.items():
                mlflow.log_metric(k, v, step=step)

    def log_table(self, table_name: str, df: pd.DataFrame):
        """Logs a tabular dataset or summary table."""
        if self.wandb_run is not None:
            try:
                import wandb
                wandb.log({table_name: wandb.Table(dataframe=df)})
            except Exception as e:
                print(f"[W&B] Failed to log table {table_name}: {e}")

        if self.mlflow_run is not None:
            try:
                import mlflow
                csv_path = os.path.join(DATA_DIR, f"{table_name}.csv")
                df.to_csv(csv_path, index=False)
                mlflow.log_artifact(csv_path)
            except Exception as e:
                print(f"[MLflow] Failed to log table artifact {table_name}: {e}")

    def log_benchmark_comparison(self, df_summary: pd.DataFrame):
        """
        Logs complete Table 4.4 and Table 4.5 benchmark metrics with interactive comparison charts.
        """
        print(f"[ExperimentTracker] Logging comparative benchmark table ({len(df_summary)} systems)...")
        self.log_table("table_4_4_comparative_benchmark", df_summary)

        # Log individual system metrics for comparative charting
        for _, row in df_summary.iterrows():
            sys_name = str(row.get("System", row.get("system_name", row.get("system_id", "unknown"))))
            # MLflow only allows alphanumerics, underscores, dashes, periods, spaces, and slashes
            import re
            safe_prefix = re.sub(r'[^a-zA-Z0-9_\-\./ ]', '_', sys_name).replace(" ", "_")
            
            metrics = {}
            for k in ["Corpus WER", "corpus_wer"]:
                if k in row: metrics[f"{safe_prefix}/wer"] = _clean_num(row[k])
            for k in ["Corpus CER", "corpus_cer"]:
                if k in row: metrics[f"{safe_prefix}/cer"] = _clean_num(row[k])
            for k in ["Term F1", "term_f1"]:
                if k in row: metrics[f"{safe_prefix}/term_f1"] = _clean_num(row[k])
            for k in ["Term Recall", "term_recall"]:
                if k in row: metrics[f"{safe_prefix}/term_recall"] = _clean_num(row[k])
            for k in ["Term Prec", "term_precision"]:
                if k in row: metrics[f"{safe_prefix}/term_precision"] = _clean_num(row[k])
            for k in ["Harmful Correction Rate (HCR)", "harmful_correction_rate"]:
                if k in row: metrics[f"{safe_prefix}/harmful_corruption_rate"] = _clean_num(row[k])
            for k in ["Net Gain", "net_gain"]:
                if k in row: metrics[f"{safe_prefix}/net_gain"] = _clean_num(row[k])
            for k in ["latency_mean_ms"]:
                if k in row: metrics[f"{safe_prefix}/latency_ms"] = _clean_num(row[k])
            for k in ["rtf"]:
                if k in row: metrics[f"{safe_prefix}/rtf"] = _clean_num(row[k])

            if metrics:
                self.log_metrics(metrics)

        print("[ExperimentTracker] Benchmark metrics successfully recorded across active backends!")

    def finish(self):
        """Concludes the tracking sessions."""
        if self.wandb_run is not None:
            import wandb
            wandb.finish()
            print("[W&B] Session finished successfully.")

        if self.mlflow_run is not None:
            import mlflow
            mlflow.end_run()
            db_uri = f"sqlite:///{os.path.abspath(MLFLOW_DB).replace(os.sep, '/')}"
            print(f"[MLflow] Session saved. View local dashboard with:\n  mlflow ui --backend-store-uri \"{db_uri}\"")


def log_existing_benchmark_results(backend: str = "both", offline: bool = True):
    """
    Utility to load existing benchmark results and log them to W&B and MLflow.
    """
    summary_path = os.path.join(DATA_DIR, "benchmark_results", "comparative_results_all_systems_test.csv")
    latency_summary_path = os.path.join(DATA_DIR, "benchmark_results", "latency_rtf_summary_test.csv")

    if not os.path.exists(summary_path):
        print(f"Error: Benchmark summary not found at {summary_path}")
        return

    df_acc = pd.read_csv(summary_path)
    print(f"Loaded accuracy benchmark summary: {len(df_acc)} rows")

    tracker = UnifiedExperimentTracker(
        project_name="liemwhisper-benchmark",
        run_name="table_4_4_official_evaluation",
        backend=backend,
        offline=offline,
        config={"dataset": "ISTQB CTFL v4.0.1", "split": "test", "total_utterances": 245}
    )

    tracker.log_benchmark_comparison(df_acc)
    tracker.finish()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="LiemWhisper Experiment Tracker CLI")
    parser.add_argument("--log-benchmark", action="store_true", help="Log existing benchmark results to W&B and MLflow")
    parser.add_argument("--backend", type=str, default="both", choices=["wandb", "mlflow", "both"])
    parser.add_argument("--offline", action="store_true", default=True, help="Use offline mode for W&B")
    parser.add_argument("--ui", action="store_true", help="Launch local MLflow UI server")
    args = parser.parse_args()

    if args.ui:
        import subprocess
        db_uri = f"sqlite:///{os.path.abspath(MLFLOW_DB).replace(os.sep, '/')}"
        print(f"Starting MLflow UI on http://localhost:5000 using store: {db_uri}")
        subprocess.run(["mlflow", "ui", "--backend-store-uri", db_uri, "--port", "5000"])
    elif args.log_benchmark:
        log_existing_benchmark_results(backend=args.backend, offline=args.offline)
    else:
        log_existing_benchmark_results(backend="both", offline=True)
