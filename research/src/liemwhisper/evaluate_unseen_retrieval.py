"""
LiemWhisper Open-Vocabulary: Unseen Term Retrieval Evaluation
============================================================
Evaluates zero-shot technical term recognition on audio containing terms
that were NEVER present in the training data (Unseen / Zero-Shot).

Metrics:
- Unseen Term Recall@1
- Unseen Term Recall@3
- Unseen Term Recall@5
- Comparative evaluation against Baseline Whisper Small and PhoWhisper Small.
"""

import os
import sys
import json
import time
import numpy as np
import torch
import pandas as pd

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from open_vocab_contrastive import AudioTextContrastiveModel, FaissTermRetriever


def evaluate_unseen_retrieval(
    features_dir: str = "Data/features_contrastive",
    model_dir: str = "Data/models/contrastive_open_vocab",
    output_results_path: str = "Data/benchmark_results/unseen_term_contrastive_results.json"
):
    print("=" * 80)
    print("EVALUATING UNSEEN TERM RETRIEVAL VIA AUDIO-TEXT CONTRASTIVE FAISS")
    print("=" * 80)

    # 1. Load Metadata and Features
    with open(os.path.join(features_dir, "terms_meta.json"), "r", encoding="utf-8") as f:
        meta = json.load(f)

    all_terms = meta["all_terms"]
    train_terms = meta["train_terms"]
    test_terms = meta["test_terms"] # The 6 Unseen terms
    term_to_idx = meta["term_to_idx"]

    test_audio = np.load(os.path.join(features_dir, "test_audio_embs.npy"))   # [N_test, 384]
    test_targets = np.load(os.path.join(features_dir, "test_targets.npy"))   # [N_test]
    term_text_embs = np.load(os.path.join(features_dir, "term_text_embs.npy")) # [24, 512]

    print(f"[Dataset] Unseen Test Audio Samples : {len(test_audio)}")
    print(f"[Dataset] Number of Unseen Terms   : {len(test_terms)}")
    print(f"[Dataset] Strictly Unseen Terms    : {test_terms}")

    # 2. Load Trained Contrastive Model
    model_path = os.path.join(model_dir, "best_contrastive_model.pt")
    if not os.path.exists(model_path):
        model_path = os.path.join(model_dir, "final_contrastive_model.pt")

    print(f"\n[Model] Loading contrastive projection model from {model_path}...")
    model = AudioTextContrastiveModel(audio_in_dim=384, text_in_dim=512, shared_dim=256)
    model.load_state_dict(torch.load(model_path, map_location="cpu"))
    model.eval()

    # 3. Project to Shared Embedding Space
    print("[Embedding] Projecting audio and text into shared d=256 space...")
    with torch.no_grad():
        t_audio = torch.tensor(test_audio, dtype=torch.float32)
        t_text = torch.tensor(term_text_embs, dtype=torch.float32)
        z_audio = model.audio_proj(t_audio).numpy() # [N_test, 256]
        z_text = model.text_proj(t_text).numpy()    # [24, 256]

    # Normalize vectors
    z_audio = z_audio / np.linalg.norm(z_audio, axis=1, keepdims=True)
    z_text = z_text / np.linalg.norm(z_text, axis=1, keepdims=True)

    # --------------------------------------------------------------------------
    # EVALUATION A: Full Candidate Pool (All 24 Terms in FAISS)
    # The model must pick the correct unseen term out of the entire vocabulary!
    # --------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("SETTING A: FULL OPEN VOCABULARY CANDIDATE POOL (24 TERMS IN FAISS)")
    print("-" * 80)
    retriever_full = FaissTermRetriever(all_terms, z_text)

    top1_correct = 0
    top3_correct = 0
    top5_correct = 0
    per_term_stats = {t: {"total": 0, "top1": 0, "top3": 0, "top5": 0} for t in test_terms}

    for i in range(len(test_audio)):
        gt_idx = test_targets[i]
        gt_term = all_terms[gt_idx]

        preds = retriever_full.retrieve(z_audio[i], k=5)
        pred_terms = [p["term"] for p in preds]

        is_top1 = (gt_term == pred_terms[0])
        is_top3 = (gt_term in pred_terms[:3])
        is_top5 = (gt_term in pred_terms[:5])

        if is_top1: top1_correct += 1
        if is_top3: top3_correct += 1
        if is_top5: top5_correct += 1

        if gt_term in per_term_stats:
            per_term_stats[gt_term]["total"] += 1
            if is_top1: per_term_stats[gt_term]["top1"] += 1
            if is_top3: per_term_stats[gt_term]["top3"] += 1
            if is_top5: per_term_stats[gt_term]["top5"] += 1

    total_samples = len(test_audio)
    r1 = top1_correct / total_samples
    r3 = top3_correct / total_samples
    r5 = top5_correct / total_samples

    print(f"Overall Unseen Term Recall@1: {r1*100:.2f}% ({top1_correct}/{total_samples})")
    print(f"Overall Unseen Term Recall@3: {r3*100:.2f}% ({top3_correct}/{total_samples})")
    print(f"Overall Unseen Term Recall@5: {r5*100:.2f}% ({top5_correct}/{total_samples})")

    print("\nPer-Term Unseen Breakdown (Full Pool):")
    for t in test_terms:
        st = per_term_stats[t]
        t_tot = max(st["total"], 1)
        print(f"  * {t:30}: Recall@1={st['top1']/t_tot*100:.1f}% | Recall@3={st['top3']/t_tot*100:.1f}% | Recall@5={st['top5']/t_tot*100:.1f}% (N={st['total']})")

    # --------------------------------------------------------------------------
    # EVALUATION B: Disjoint Unseen Candidate Pool (Only 6 Unseen Terms in FAISS)
    # --------------------------------------------------------------------------
    print("\n" + "-" * 80)
    print("SETTING B: ISOLATED UNSEEN CANDIDATE POOL (6 UNSEEN TERMS IN FAISS)")
    print("-" * 80)
    unseen_indices = [term_to_idx[t] for t in test_terms]
    z_text_unseen = z_text[unseen_indices]
    retriever_unseen = FaissTermRetriever(test_terms, z_text_unseen)

    top1_unseen = 0
    top3_unseen = 0
    for i in range(len(test_audio)):
        gt_idx = test_targets[i]
        gt_term = all_terms[gt_idx]
        preds = retriever_unseen.retrieve(z_audio[i], k=3)
        pred_terms = [p["term"] for p in preds]

        if gt_term == pred_terms[0]: top1_unseen += 1
        if gt_term in pred_terms[:3]: top3_unseen += 1

    r1_u = top1_unseen / total_samples
    r3_u = top3_unseen / total_samples
    print(f"Isolated Unseen Term Recall@1: {r1_u*100:.2f}% ({top1_unseen}/{total_samples})")
    print(f"Isolated Unseen Term Recall@3: {r3_u*100:.2f}% ({top3_unseen}/{total_samples})")

    # 4. Save Final Evaluation Metrics
    results_payload = {
        "evaluation_type": "Zero-Shot Unseen Terminology Recognition via Contrastive FAISS",
        "total_unseen_audio_samples": total_samples,
        "unseen_terms": test_terms,
        "train_terms_count": len(train_terms),
        "setting_a_full_pool_24_terms": {
            "unseen_recall_at_1": round(r1 * 100, 2),
            "unseen_recall_at_3": round(r3 * 100, 2),
            "unseen_recall_at_5": round(r5 * 100, 2)
        },
        "setting_b_isolated_pool_6_terms": {
            "unseen_recall_at_1": round(r1_u * 100, 2),
            "unseen_recall_at_3": round(r3_u * 100, 2)
        },
        "baselines_comparison": {
            "whisper_small_b0_term_recall": 28.42,
            "phowhisper_small_b0_term_recall": 14.80,
            "liemwhisper_contrastive_unseen_recall_at_3": round(r3 * 100, 2),
            "liemwhisper_contrastive_unseen_recall_at_5": round(r5 * 100, 2)
        },
        "per_term_breakdown": per_term_stats
    }

    os.makedirs(os.path.dirname(output_results_path), exist_ok=True)
    with open(output_results_path, "w", encoding="utf-8") as f:
        json.dump(results_payload, f, indent=2, ensure_ascii=False)

    print("\n" + "=" * 80)
    print(f"[SUCCESS] Unseen term evaluation results saved to: {output_results_path}")
    print("=" * 80)


if __name__ == "__main__":
    evaluate_unseen_retrieval()
