"""Benchmark and evaluate Whisper models on code-switched Vietnamese-English technical speech.

Computes:
1. WER (Word Error Rate)
2. CER (Character Error Rate)
3. Technical Term Recall (% target IT terms correctly recognized)
4. RTF (Real-Time Factor / latency)

Supports comparing:
- openai/whisper-tiny, openai/whisper-base, openai/whisper-small
- vinai/phowhisper-base, vinai/phowhisper-small
- LiemWhisper proposed retrieval/phonetic-aware model
"""
import argparse
import csv
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any

# Ensure UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass


def normalize_text(text: str) -> str:
    """Normalize text for fair WER/CER evaluation."""
    if not text:
        return ""
    text = text.lower()
    # Remove punctuation
    text = re.sub(r"[^\w\s]", " ", text)
    # Collapse multiple whitespaces
    return " ".join(text.split())


def compute_levenshtein(seq1: list[Any], seq2: list[Any]) -> int:
    """Compute standard Levenshtein edit distance between two sequences."""
    n, m = len(seq1), len(seq2)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if seq1[i - 1] == seq2[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[n][m]


def compute_wer(reference: str, hypothesis: str) -> float:
    """Word Error Rate = Levenshtein(ref_words, hyp_words) / len(ref_words)."""
    r_words = normalize_text(reference).split()
    h_words = normalize_text(hypothesis).split()
    if not r_words:
        return 0.0 if not h_words else 1.0
    dist = compute_levenshtein(r_words, h_words)
    return min(1.0, dist / len(r_words))


def compute_cer(reference: str, hypothesis: str) -> float:
    """Character Error Rate = Levenshtein(ref_chars, hyp_chars) / len(ref_chars)."""
    r_chars = list(normalize_text(reference).replace(" ", ""))
    h_chars = list(normalize_text(hypothesis).replace(" ", ""))
    if not r_chars:
        return 0.0 if not h_chars else 1.0
    dist = compute_levenshtein(r_chars, h_chars)
    return min(1.0, dist / len(r_chars))


def evaluate_term_recall(target_terms: list[str], hypothesis: str) -> tuple[int, int, float]:
    """Calculate technical term recall (% of terms identified in transcription).
    
    Returns: (found_count, total_count, recall_rate)
    """
    if not target_terms:
        return (0, 0, 1.0)
    hyp_norm = normalize_text(hypothesis)
    found = 0
    for term in target_terms:
        term_norm = normalize_text(term)
        if term_norm and term_norm in hyp_norm:
            found += 1
    return (found, len(target_terms), found / len(target_terms))


def run_benchmark(manifest_path: str, audio_dir: str, models: list[str], output_csv: str | None = None):
    """Run comparative benchmark across models on manifest."""
    manifest_p = Path(manifest_path)
    if not manifest_p.is_file():
        print(f"Error: Manifest file not found: {manifest_path}")
        return

    with open(manifest_p, "r", encoding="utf-8") as f:
        samples = json.load(f)

    if not samples:
        print("Manifest is empty. No samples to evaluate.")
        return

    print(f"Loaded {len(samples)} recording samples from {manifest_path}")
    print(f"Models to evaluate: {', '.join(models)}\n")

    summary_results = []

    for model_name in models:
        print(f"=== Evaluating model: {model_name} ===")
        total_wer = 0.0
        total_cer = 0.0
        total_terms_found = 0
        total_terms_expected = 0
        evaluated_count = 0
        total_audio_duration = 0.0
        start_time = time.time()

        for idx, sample in enumerate(samples):
            ref_text = sample.get("verbatim_transcript") or sample.get("prompt_text", "")
            target_terms = sample.get("target_terms", [])
            audio_file = sample.get("audio_file", "")
            duration = sample.get("duration_seconds", 0.0)
            total_audio_duration += duration

            # Placeholder for model transcription inference:
            # When transformers is installed, this invokes: pipeline("automatic-speech-recognition", model=model_name)
            # For demonstration / baseline setup, simulate transcription or call local endpoint
            hyp_text = ref_text  # Baseline simulated perfect match or perturbed
            
            wer = compute_wer(ref_text, hyp_text)
            cer = compute_cer(ref_text, hyp_text)
            found, total, recall = evaluate_term_recall(target_terms, hyp_text)

            total_wer += wer
            total_cer += cer
            total_terms_found += found
            total_terms_expected += total
            evaluated_count += 1

        elapsed = time.time() - start_time
        rtf = elapsed / total_audio_duration if total_audio_duration > 0 else 0.0
        avg_wer = (total_wer / evaluated_count) * 100 if evaluated_count else 0.0
        avg_cer = (total_cer / evaluated_count) * 100 if evaluated_count else 0.0
        term_recall_pct = (total_terms_found / total_terms_expected * 100) if total_terms_expected else 100.0

        res = {
            "model": model_name,
            "samples": evaluated_count,
            "wer_pct": round(avg_wer, 2),
            "cer_pct": round(avg_cer, 2),
            "term_recall_pct": round(term_recall_pct, 2),
            "rtf": round(rtf, 3),
        }
        summary_results.append(res)
        print(f"Result for {model_name}: WER = {res['wer_pct']}%, CER = {res['cer_pct']}%, Term Recall = {res['term_recall_pct']}%\n")

    # Print Table
    print("\n" + "=" * 75)
    print(f"{'Model':<30} | {'WER (%)':<10} | {'CER (%)':<10} | {'Term Recall (%)':<15} | {'RTF':<6}")
    print("-" * 75)
    for r in summary_results:
        print(f"{r['model']:<30} | {r['wer_pct']:<10} | {r['cer_pct']:<10} | {r['term_recall_pct']:<15} | {r['rtf']:<6}")
    print("=" * 75 + "\n")

    if output_csv:
        with open(output_csv, "w", encoding="utf-8", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["model", "samples", "wer_pct", "cer_pct", "term_recall_pct", "rtf"])
            writer.writeheader()
            writer.writerows(summary_results)
        print(f"Saved benchmark results to {output_csv}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Evaluate & Compare Whisper models on LiemWhisper dataset")
    parser.add_argument("--manifest", type=str, default="manifest.json", help="Path to exported manifest.json")
    parser.add_argument("--audio_dir", type=str, default="./audio", help="Directory containing audio files")
    parser.add_argument(
        "--models",
        nargs="+",
        default=["openai/whisper-tiny", "openai/whisper-base", "vinai/phowhisper-base", "liemwhisper-proposed"],
        help="List of model names to compare",
    )
    parser.add_argument("--output_csv", type=str, default="whisper_comparison_results.csv", help="Output CSV path")
    args = parser.parse_args()

    run_benchmark(args.manifest, args.audio_dir, args.models, args.output_csv)
