"""
LiemWhisper Latency, Throughput & Real-Time Factor (RTF) Benchmark Engine
========================================================================
Measures execution latencies, component breakdown, throughput, and Real-Time Factor (RTF)
across all baseline systems and Proposed System P on Vietnamese code-switched technical speech.

Systems Benchmarked:
1. B0: Raw Whisper Small (ASR + Exact Match)
2. B1: Glossary Prompting (ASR with initial domain prompt + Exact Match)
3. B2: Lexical Fuzzy Matching (ASR + sliding window sequence matching)
4. P (Fast / Real-time): Proposed System P w/o Acoustic Alignment (Low-latency mode)
5. P (Full / High-Precision): Proposed System P with Acoustic Teacher-Forcing Scorer

Outputs:
- Data/benchmark_results/latency_rtf_detailed_test.csv (per-utterance timings)
- Data/benchmark_results/latency_rtf_summary_test.csv (system-level aggregated metrics)
"""

import os
import sys
import time
import json
import platform
import argparse
from typing import List, Dict, Any, Optional, Tuple
import numpy as np
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from baselines import (
    TaxonomyManager,
    ExactMatchingBaseline,
    LexicalFuzzyMatcher
)
from candidate_ranking import (
    ProposedSystemP,
    AcousticTeacherForcingScorer
)


def get_hardware_info() -> Dict[str, Any]:
    """Captures CPU, RAM, OS, and runtime platform specifications."""
    info = {
        "os": f"{platform.system()} {platform.release()} ({platform.version()})",
        "cpu": platform.processor(),
        "cpu_count_logical": os.cpu_count() or 1,
        "python_version": platform.python_version(),
    }
    try:
        import psutil
        mem = psutil.virtual_memory()
        info["ram_total_gb"] = round(mem.total / (1024 ** 3), 2)
    except ImportError:
        info["ram_total_gb"] = "N/A"
    return info


class LatencyBenchmarkHarness:
    """
    Executes standardized, instrumented latency and RTF evaluation
    across representative test utterances.
    """

    def __init__(
        self,
        taxonomy_path: str,
        wav_dir: str,
        model_size: str = "small",
        device: str = "cpu",
        compute_type: str = "int8",
        cpu_threads: int = 8
    ):
        self.taxonomy = TaxonomyManager(taxonomy_path)
        self.wav_dir = wav_dir
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.cpu_threads = cpu_threads

        # Load shared WhisperModel
        print(f"[LatencyHarness] Initializing WhisperModel({model_size}, device={device}, compute_type={compute_type}, threads={cpu_threads})...")
        t0 = time.perf_counter()
        from faster_whisper import WhisperModel
        self.whisper_model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
            cpu_threads=cpu_threads
        )
        self.model_load_time_s = round(time.perf_counter() - t0, 3)
        print(f"[LatencyHarness] Model loaded in {self.model_load_time_s}s.")

        # Initialize Base Extractors
        self.exact_extractor = ExactMatchingBaseline(self.taxonomy)
        self.fuzzy_matcher = LexicalFuzzyMatcher(self.taxonomy, similarity_threshold=0.75)
        self.glossary_prompt = self.taxonomy.create_glossary_prompt()

        # Initialize Proposed Systems
        print("[LatencyHarness] Setting up Proposed Systems (Fast & Full)...")
        # P Fast (w/o acoustic)
        self.system_p_fast = ProposedSystemP(
            self.taxonomy,
            acoustic_scorer=None,
            enable_acoustic=False,
            enable_context=True,
            enable_phonetic=True,
            enable_gate=True
        )

        # P Full (with shared acoustic scorer)
        self.acoustic_scorer = AcousticTeacherForcingScorer(
            model_size=model_size,
            device=device,
            compute_type=compute_type,
            whisper_model=self.whisper_model
        )
        self.acoustic_scorer.load_model()
        self.system_p_full = ProposedSystemP(
            self.taxonomy,
            acoustic_scorer=self.acoustic_scorer,
            enable_acoustic=True,
            enable_context=True,
            enable_phonetic=True,
            enable_gate=True
        )

    def warmup(self, warmup_wav: str, rounds: int = 2):
        """Runs warmup iterations to prime JIT caches and CPU thread pools."""
        print(f"[LatencyHarness] Running {rounds} warmup iterations on {os.path.basename(warmup_wav)}...")
        for _ in range(rounds):
            segments, _ = self.whisper_model.transcribe(warmup_wav, language="vi")
            _ = " ".join(s.text for s in segments)
            _ = self.system_p_fast.process_utterance("Kỹ thuật unit testing và boundary value analysis", warmup_wav)
        print("[LatencyHarness] Warmup complete.")

    def run_benchmark(
        self,
        test_samples: List[Dict[str, Any]],
        run_full_acoustic: bool = True
    ) -> Tuple[pd.DataFrame, pd.DataFrame]:
        """
        Runs latency benchmark across test samples for all systems.
        """
        detailed_records = []

        n_samples = len(test_samples)
        print(f"\n[LatencyHarness] Commencing benchmark on {n_samples} test recordings...")

        for idx, item in enumerate(test_samples, 1):
            rec_id = item["recording_id"]
            wav_file = item["wav_file"]
            wav_path = os.path.join(self.wav_dir, wav_file)
            audio_duration = float(item["duration_seconds"])

            if not os.path.exists(wav_path):
                print(f"Warning: Audio file not found: {wav_path}")
                continue

            # -------------------------------------------------------------
            # System B0: Raw Whisper Small
            # -------------------------------------------------------------
            t_b0_start = time.perf_counter()
            segments_b0, _ = self.whisper_model.transcribe(wav_path, language="vi")
            b0_text = " ".join(s.text for s in segments_b0)
            t_b0_asr = (time.perf_counter() - t_b0_start) * 1000.0

            t_m0_start = time.perf_counter()
            _ = self.exact_extractor.extract_terms(b0_text)
            t_b0_post = (time.perf_counter() - t_m0_start) * 1000.0
            t_b0_e2e = t_b0_asr + t_b0_post
            rtf_b0 = (t_b0_e2e / 1000.0) / audio_duration

            # -------------------------------------------------------------
            # System B1: Glossary Prompting
            # -------------------------------------------------------------
            t_b1_start = time.perf_counter()
            segments_b1, _ = self.whisper_model.transcribe(
                wav_path,
                language="vi",
                initial_prompt=self.glossary_prompt
            )
            b1_text = " ".join(s.text for s in segments_b1)
            t_b1_asr = (time.perf_counter() - t_b1_start) * 1000.0

            t_m1_start = time.perf_counter()
            _ = self.exact_extractor.extract_terms(b1_text)
            t_b1_post = (time.perf_counter() - t_m1_start) * 1000.0
            t_b1_e2e = t_b1_asr + t_b1_post
            rtf_b1 = (t_b1_e2e / 1000.0) / audio_duration

            # -------------------------------------------------------------
            # System B2: Lexical Fuzzy Matching
            # -------------------------------------------------------------
            t_b2_start = time.perf_counter()
            _ = self.fuzzy_matcher.extract_terms(b0_text)
            t_b2_post = (time.perf_counter() - t_b2_start) * 1000.0
            t_b2_e2e = t_b0_asr + t_b2_post
            rtf_b2 = (t_b2_e2e / 1000.0) / audio_duration

            # -------------------------------------------------------------
            # System P-Fast (Proposed System P w/o Acoustic Alignment)
            # -------------------------------------------------------------
            res_p_fast = self.system_p_fast.process_utterance(
                b0_text,
                wav_path,
                return_timing=True
            )
            timing_p_fast = res_p_fast.get("timing", {})
            t_p_fast_post = timing_p_fast.get("t_post_ms", 0.0)
            t_p_fast_e2e = t_b0_asr + t_p_fast_post
            rtf_p_fast = (t_p_fast_e2e / 1000.0) / audio_duration

            # -------------------------------------------------------------
            # System P-Full (Proposed System P with Acoustic Teacher-Forcing)
            # -------------------------------------------------------------
            if run_full_acoustic:
                res_p_full = self.system_p_full.process_utterance(
                    b0_text,
                    wav_path,
                    return_timing=True
                )
                timing_p_full = res_p_full.get("timing", {})
                t_p_full_post = timing_p_full.get("t_post_ms", 0.0)
                t_p_full_e2e = t_b0_asr + t_p_full_post
                rtf_p_full = (t_p_full_e2e / 1000.0) / audio_duration
                t_acoust_ms = timing_p_full.get("t_acoust_ms", 0.0)
            else:
                t_p_full_post = np.nan
                t_p_full_e2e = np.nan
                rtf_p_full = np.nan
                t_acoust_ms = np.nan

            rec = {
                "recording_id": rec_id,
                "audio_duration_s": round(audio_duration, 2),
                # B0
                "b0_asr_ms": round(t_b0_asr, 1),
                "b0_post_ms": round(t_b0_post, 2),
                "b0_e2e_ms": round(t_b0_e2e, 1),
                "b0_rtf": round(rtf_b0, 4),
                # B1
                "b1_asr_ms": round(t_b1_asr, 1),
                "b1_post_ms": round(t_b1_post, 2),
                "b1_e2e_ms": round(t_b1_e2e, 1),
                "b1_rtf": round(rtf_b1, 4),
                # B2
                "b2_post_ms": round(t_b2_post, 2),
                "b2_e2e_ms": round(t_b2_e2e, 1),
                "b2_rtf": round(rtf_b2, 4),
                # P-Fast
                "p_fast_gen_ms": timing_p_fast.get("t_gen_ms", 0.0),
                "p_fast_ctx_ms": timing_p_fast.get("t_ctx_ms", 0.0),
                "p_fast_gate_ms": timing_p_fast.get("t_gate_ms", 0.0),
                "p_fast_post_ms": round(t_p_fast_post, 2),
                "p_fast_e2e_ms": round(t_p_fast_e2e, 1),
                "p_fast_rtf": round(rtf_p_fast, 4),
                # P-Full
                "p_full_acoust_ms": round(t_acoust_ms, 1) if not np.isnan(t_acoust_ms) else np.nan,
                "p_full_post_ms": round(t_p_full_post, 2) if not np.isnan(t_p_full_post) else np.nan,
                "p_full_e2e_ms": round(t_p_full_e2e, 1) if not np.isnan(t_p_full_e2e) else np.nan,
                "p_full_rtf": round(rtf_p_full, 4) if not np.isnan(rtf_p_full) else np.nan,
            }
            detailed_records.append(rec)

            if idx % 5 == 0 or idx == n_samples:
                print(f"  [{idx}/{n_samples}] Audio: {audio_duration:.1f}s | B0 RTF: {rtf_b0:.3f} | P-Fast RTF: {rtf_p_fast:.3f} | P-Fast Post: {t_p_fast_post:.1f}ms")

        detailed_df = pd.DataFrame(detailed_records)

        # Aggregate Summary Table
        summary_rows = []
        systems_cfg = [
            ("B0: Raw Whisper Small", "b0_post_ms", "b0_e2e_ms", "b0_rtf"),
            ("B1: Glossary Prompting", "b1_post_ms", "b1_e2e_ms", "b1_rtf"),
            ("B2: Lexical Fuzzy Matching", "b2_post_ms", "b2_e2e_ms", "b2_rtf"),
            ("P (Fast): Proposed w/o Acoustic", "p_fast_post_ms", "p_fast_e2e_ms", "p_fast_rtf"),
        ]
        if run_full_acoustic and detailed_df["p_full_rtf"].notna().any():
            systems_cfg.append(("P (Full): Proposed Multi-Evidence", "p_full_post_ms", "p_full_e2e_ms", "p_full_rtf"))

        b0_mean_e2e = detailed_df["b0_e2e_ms"].mean()

        for name, col_post, col_e2e, col_rtf in systems_cfg:
            e2e_vals = detailed_df[col_e2e].dropna()
            post_vals = detailed_df[col_post].dropna()
            rtf_vals = detailed_df[col_rtf].dropna()

            mean_e2e = e2e_vals.mean()
            median_e2e = e2e_vals.median()
            p90_e2e = np.percentile(e2e_vals, 90)
            p95_e2e = np.percentile(e2e_vals, 95)
            std_e2e = e2e_vals.std()

            mean_post = post_vals.mean()
            median_post = post_vals.median()

            mean_rtf = rtf_vals.mean()
            median_rtf = rtf_vals.median()
            p95_rtf = np.percentile(rtf_vals, 95)

            # Real-Time Speedup: how many times faster than real-time
            speedup = 1.0 / mean_rtf if mean_rtf > 0 else 0.0

            # Throughput (utterances/second)
            throughput = 1000.0 / mean_e2e if mean_e2e > 0 else 0.0

            # Overhead vs B0 (%)
            overhead_pct = ((mean_e2e - b0_mean_e2e) / b0_mean_e2e) * 100.0

            summary_rows.append({
                "System": name,
                "Mean Post-Processing (ms)": round(mean_post, 1),
                "Median Post-Processing (ms)": round(median_post, 1),
                "Mean E2E Latency (ms)": round(mean_e2e, 1),
                "Median E2E (ms)": round(median_e2e, 1),
                "P90 E2E (ms)": round(p90_e2e, 1),
                "P95 E2E (ms)": round(p95_e2e, 1),
                "Std E2E (ms)": round(std_e2e, 1),
                "Mean RTF": round(mean_rtf, 4),
                "Median RTF": round(median_rtf, 4),
                "P95 RTF": round(p95_rtf, 4),
                "Real-Time Speedup (x)": f"{speedup:.2f}x",
                "Throughput (utt/s)": round(throughput, 2),
                "Latency Overhead vs B0": f"+{overhead_pct:.1f}%" if overhead_pct >= 0 else f"{overhead_pct:.1f}%"
            })

        summary_df = pd.DataFrame(summary_rows)
        return detailed_df, summary_df


def sample_representative_test_set(df: pd.DataFrame, n_samples: int = 30) -> List[Dict[str, Any]]:
    """
    Selects a stratified representative sample covering short (<10s),
    medium (10-20s), and long (>20s) audio durations across different speakers.
    """
    test_df = df[df["split"] == "test"].copy()
    test_df["dur_bracket"] = pd.cut(
        test_df["duration_seconds"],
        bins=[0, 10, 20, 120],
        labels=["Short (<10s)", "Medium (10-20s)", "Long (>20s)"]
    )

    sampled_list = []
    per_bracket = max(1, n_samples // 3)

    for bracket in ["Short (<10s)", "Medium (10-20s)", "Long (>20s)"]:
        b_df = test_df[test_df["dur_bracket"] == bracket]
        take_n = min(len(b_df), per_bracket)
        if take_n > 0:
            sample_sub = b_df.sample(n=take_n, random_state=42)
            sampled_list.append(sample_sub)

    res_df = pd.concat(sampled_list).drop_duplicates(subset=["recording_id"])
    # If still below n_samples, fill with random samples
    if len(res_df) < n_samples:
        remaining = test_df[~test_df["recording_id"].isin(res_df["recording_id"])]
        take_more = min(len(remaining), n_samples - len(res_df))
        if take_more > 0:
            res_df = pd.concat([res_df, remaining.sample(n=take_more, random_state=42)])

    return res_df.to_dict(orient="records")


def parse_args():
    parser = argparse.ArgumentParser(description="LiemWhisper Latency, Throughput & RTF Benchmark")
    parser.add_argument("--samples", type=int, default=30, help="Number of representative test samples (default: 30)")
    parser.add_argument("--all", action="store_true", help="Run benchmark across all 245 test samples")
    parser.add_argument("--skip-full-acoustic", action="store_true", help="Skip full acoustic alignment to save CPU benchmark time")
    parser.add_argument("--device", type=str, default="cpu", help="Compute device: cpu or cuda")
    parser.add_argument("--compute-type", type=str, default="int8", help="Compute type: int8 or float16")
    parser.add_argument("--threads", type=int, default=8, help="Number of CPU worker threads")
    return parser.parse_args()


def main():
    args = parse_args()
    print("=" * 80)
    print("LIEMWHISPER LATENCY, THROUGHPUT & REAL-TIME FACTOR (RTF) BENCHMARK")
    print("=" * 80)

    # Discover workspace paths
    base_dir = current_dir
    while base_dir and not os.path.exists(os.path.join(base_dir, "Data", "glossary_taxonomy_v1.json")):
        parent = os.path.dirname(base_dir)
        if parent == base_dir:
            break
        base_dir = parent

    data_dir = os.path.join(base_dir, "Data")
    taxonomy_path = os.path.join(data_dir, "glossary_taxonomy_v1.json")
    wav_dir = os.path.join(data_dir, "wav_16k")
    manifest_path = os.path.join(data_dir, "clean_manifest_v1_gold.csv")
    out_dir = os.path.join(data_dir, "benchmark_results")
    os.makedirs(out_dir, exist_ok=True)

    hw_info = get_hardware_info()
    print(f"Hardware Environment : {hw_info['os']} | CPU Cores: {hw_info['cpu_count_logical']} | RAM: {hw_info['ram_total_gb']} GB")
    print(f"Inference Device     : {args.device} ({args.compute_type}) | CPU Threads: {args.threads}")

    manifest_df = pd.read_csv(manifest_path)
    if args.all:
        test_samples = manifest_df[manifest_df["split"] == "test"].to_dict(orient="records")
    else:
        test_samples = sample_representative_test_set(manifest_df, n_samples=args.samples)

    print(f"Evaluation Set Size  : {len(test_samples)} recordings")

    harness = LatencyBenchmarkHarness(
        taxonomy_path=taxonomy_path,
        wav_dir=wav_dir,
        model_size="small",
        device=args.device,
        compute_type=args.compute_type,
        cpu_threads=args.threads
    )

    # Run warmup
    warmup_wav = os.path.join(wav_dir, test_samples[0]["wav_file"])
    harness.warmup(warmup_wav, rounds=2)

    # Execute benchmark
    detailed_df, summary_df = harness.run_benchmark(
        test_samples,
        run_full_acoustic=not args.skip_full_acoustic
    )

    # Export results
    detailed_csv = os.path.join(out_dir, "latency_rtf_detailed_test.csv")
    summary_csv = os.path.join(out_dir, "latency_rtf_summary_test.csv")

    detailed_df.to_csv(detailed_csv, index=False, encoding="utf-8-sig")
    summary_df.to_csv(summary_csv, index=False, encoding="utf-8-sig")

    print("\n" + "=" * 80)
    print("BENCHMARK SUMMARY RESULTS:")
    print("=" * 80)
    print(summary_df.to_string(index=False))
    print(f"\nSaved detailed measurements to: {detailed_csv}")
    print(f"Saved summary metrics to      : {summary_csv}")


if __name__ == "__main__":
    main()
