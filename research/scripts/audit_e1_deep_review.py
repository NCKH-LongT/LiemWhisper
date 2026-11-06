import os
import sys
import json
import time
import numpy as np
import pandas as pd
import soundfile as sf
import torch
import torch.nn.functional as F
from scipy import stats
from transformers import WhisperModel, WhisperFeatureExtractor, AutoTokenizer, AutoModel

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

current_dir = os.path.dirname(os.path.abspath(__file__))
capstone_dir = os.path.abspath(os.path.join(current_dir, ".."))
src_dir = os.path.join(capstone_dir, "Liem", "LiemWhisper", "research", "src", "liemwhisper")
if src_dir not in sys.path:
    sys.path.insert(0, src_dir)

from open_vocab_contrastive import AudioTextContrastiveModel, AudioProjectionHead, UNSEEN_TEST_TERMS

def main():
    print("=" * 80)
    print("COMPREHENSIVE AUDIT OF E1 & E1b: BOOTSTRAP, SPEAKERS, MARGINS, PROMPTS")
    print("=" * 80)

    # ---------------------------------------------------------
    # 1. LOAD TEST SPANS (30 SPANS ACROSS 6 UNSEEN TERMS)
    # ---------------------------------------------------------
    df_spans = pd.read_csv("Data/span_alignment_gold.csv")
    unseen_set = set(t.lower() for t in UNSEEN_TEST_TERMS)
    test_spans = df_spans[df_spans['term'].str.lower().isin(unseen_set) & (df_spans['split'] == 'unseen_test')].copy().reset_index(drop=True)
    print(f"Loaded {len(test_spans)} test spans across {test_spans['term'].nunique()} unseen terms.")
    assert len(test_spans) == 30, f"Expected 30 spans, got {len(test_spans)}"

    # ---------------------------------------------------------
    # 2. LOAD MODELS & ENCODE TEST SPANS
    # ---------------------------------------------------------
    fe = WhisperFeatureExtractor.from_pretrained("openai/whisper-tiny")
    audio_model = WhisperModel.from_pretrained("openai/whisper-tiny")
    audio_model.eval()

    tok = AutoTokenizer.from_pretrained("google-t5/t5-small")
    text_model = AutoModel.from_pretrained("google-t5/t5-small")
    text_model.eval()

    base_ckpt = torch.load("Data/models/contrastive_open_vocab/best_contrastive_model.pt", map_location="cpu")
    base_model = AudioTextContrastiveModel(audio_in_dim=384, text_in_dim=512, shared_dim=256)
    base_model.load_state_dict(base_ckpt)
    base_model.eval()

    e1b_ckpt = torch.load("Data/models/e1b_span_model.pt", map_location="cpu")
    e1b_span_head = AudioProjectionHead(in_features=384, shared_dim=256)
    e1b_span_head.load_state_dict(e1b_ckpt['span_audio_head_state_dict'])
    e1b_span_head.eval()

    # Precompute text embeddings for 6 unseen terms
    unseen_6_terms = UNSEEN_TEST_TERMS
    with torch.no_grad():
        t_inputs_6 = tok(unseen_6_terms, padding=True, truncation=True, return_tensors="pt")
        text_raw_6 = text_model.encoder(**t_inputs_6).last_hidden_state.mean(dim=1)
        text_embs_6 = base_model.text_proj(text_raw_6).numpy() # [6, 256]

    # Precompute text embeddings for 24 terms
    with open("Data/features_contrastive/terms_meta.json", "r", encoding="utf-8") as f:
        meta = json.load(f)
    all_24_terms = meta['all_terms']
    with torch.no_grad():
        t_inputs_24 = tok(all_24_terms, padding=True, truncation=True, return_tensors="pt")
        text_raw_24 = text_model.encoder(**t_inputs_24).last_hidden_state.mean(dim=1)
        text_embs_24 = base_model.text_proj(text_raw_24).numpy() # [24, 256]

    # Encode test representations
    df_gold = pd.read_csv("Data/gold_with_asr_v1.csv").set_index('recording_id')
    wav_dir = "Data/wav_16k"

    feats_e0, feats_e1a, feats_e1b, feats_e1b_crop = [], [], [], []

    for idx, row in test_spans.iterrows():
        rec_id = row['audio_id']
        wav_file = df_gold.loc[rec_id, 'wav_file']
        wav_path = os.path.join(wav_dir, wav_file)
        wav, sr = sf.read(wav_path)

        t_start, t_end = row['start_time'], row['end_time']

        inputs = fe(wav, sampling_rate=sr, return_tensors="pt")
        with torch.no_grad():
            enc_out = audio_model.encoder(inputs.input_features).last_hidden_state.squeeze(0) # [T, 384]

            # E0: Global Mean Pool
            global_raw = enc_out.mean(dim=0, keepdim=True)
            z_e0 = base_model.audio_proj(global_raw).squeeze(0).numpy()
            feats_e0.append(z_e0)

            # E1a & E1b: Contextualized Span Mean Pool
            total_frames = enc_out.shape[0]
            f_start = max(0, min(total_frames - 1, int(round(t_start * 50.0))))
            f_end = max(f_start + 1, min(total_frames, int(round(t_end * 50.0))))
            span_raw = enc_out[f_start:f_end, :].mean(dim=0, keepdim=True)

            z_e1a = base_model.audio_proj(span_raw).squeeze(0).numpy()
            feats_e1a.append(z_e1a)

            z_e1b = e1b_span_head(span_raw).squeeze(0).numpy()
            feats_e1b.append(z_e1b)

            # E1b-Crop: Pure Waveform Crop
            s_idx = max(0, int(t_start * sr))
            e_idx = min(len(wav), int(t_end * sr))
            crop_wav = wav[s_idx:e_idx]
            if len(crop_wav) < int(0.1 * sr):
                crop_wav = wav[s_idx : min(len(wav), s_idx + int(0.5 * sr))]

            crop_inputs = fe(crop_wav, sampling_rate=sr, return_tensors="pt")
            crop_enc = audio_model.encoder(crop_inputs.input_features).last_hidden_state.squeeze(0)
            crop_raw = crop_enc.mean(dim=0, keepdim=True)
            z_crop = e1b_span_head(crop_raw).squeeze(0).numpy()
            feats_e1b_crop.append(z_crop)

    models_feats = {
        'E0': np.array(feats_e0),
        'E1a': np.array(feats_e1a),
        'E1b': np.array(feats_e1b),
        'E1b-Crop': np.array(feats_e1b_crop)
    }

    # Build per-sample detailed evaluation dataframe for Setting B (6 terms)
    sample_evals = []
    for i, row in test_spans.iterrows():
        target_term = row['term']
        gt_idx = unseen_6_terms.index(target_term)

        rec = {
            'audio_id': row['audio_id'],
            'speaker_id': row['speaker_id'],
            'term': target_term
        }

        for m_name, feats in models_feats.items():
            sims = np.dot(feats[i], text_embs_6.T) # [6]
            pos_sim = float(sims[gt_idx])
            rank_order = np.argsort(-sims)
            rank = int(np.where(rank_order == gt_idx)[0][0]) + 1

            all_c = sims.copy()
            all_c[gt_idx] = -999.0
            hardest_neg = float(np.max(all_c))
            hard_neg_term = unseen_6_terms[int(np.argmax(all_c))]
            mean_neg = float(np.mean([s for idx_s, s in enumerate(sims) if idx_s != gt_idx]))

            rec[f'{m_name}_rank'] = rank
            rec[f'{m_name}_hit1'] = 1 if rank <= 1 else 0
            rec[f'{m_name}_hit3'] = 1 if rank <= 3 else 0
            rec[f'{m_name}_hit5'] = 1 if rank <= 5 else 0
            rec[f'{m_name}_pos_sim'] = pos_sim
            rec[f'{m_name}_hard_neg_sim'] = hardest_neg
            rec[f'{m_name}_hard_distractor'] = hard_neg_term
            rec[f'{m_name}_hard_margin'] = pos_sim - hardest_neg
            rec[f'{m_name}_mean_margin'] = pos_sim - mean_neg

        sample_evals.append(rec)

    df_eval = pd.DataFrame(sample_evals)
    df_eval.to_csv("Data/models/test_30_detailed_eval.csv", index=False)
    print("Saved test_30_detailed_eval.csv")

    # =========================================================================
    # AUDIT ITEM 1: BOOTSTRAP MECHANICS & EXACT P-VALUE AUDIT
    # =========================================================================
    print("\n" + "=" * 80)
    print("AUDIT ITEM 1: BOOTSTRAP MECHANICS (CLUSTER VS STANDARD PAIRED) & P-VALUE")
    print("=" * 80)

    # 1A. Cluster Bootstrap (by 5 speakers)
    np.random.seed(42)
    speakers = df_eval['speaker_id'].unique()
    diffs_cluster_r1 = []
    diffs_cluster_r3 = []
    e0_r1_list, e1b_r1_list = [], []
    e0_r3_list, e1b_r3_list = [], []

    for _ in range(10000):
        boot_spks = np.random.choice(speakers, size=len(speakers), replace=True)
        boot_df = pd.concat([df_eval[df_eval['speaker_id'] == spk] for spk in boot_spks])
        e0_r1 = boot_df['E0_hit1'].mean()
        e1b_r1 = boot_df['E1b_hit1'].mean()
        e0_r3 = boot_df['E0_hit3'].mean()
        e1b_r3 = boot_df['E1b_hit3'].mean()

        diffs_cluster_r1.append(e1b_r1 - e0_r1)
        diffs_cluster_r3.append(e1b_r3 - e0_r3)
        e0_r1_list.append(e0_r1)
        e1b_r1_list.append(e1b_r1)
        e0_r3_list.append(e0_r3)
        e1b_r3_list.append(e1b_r3)

    diffs_cluster_r1 = np.array(diffs_cluster_r1)
    diffs_cluster_r3 = np.array(diffs_cluster_r3)

    # 1B. Standard Paired Sample Bootstrap (resampling 30 rows directly)
    np.random.seed(42)
    diffs_std_r1 = []
    diffs_std_r3 = []
    for _ in range(10000):
        idx_boot = np.random.choice(len(df_eval), size=len(df_eval), replace=True)
        boot_df = df_eval.iloc[idx_boot]
        diffs_std_r1.append(boot_df['E1b_hit1'].mean() - boot_df['E0_hit1'].mean())
        diffs_std_r3.append(boot_df['E1b_hit3'].mean() - boot_df['E0_hit3'].mean())

    diffs_std_r1 = np.array(diffs_std_r1)
    diffs_std_r3 = np.array(diffs_std_r3)

    # Count breakdown of diffs
    print("Cluster Bootstrap Breakdown (10,000 iterations):")
    print(f"  Recall@1: Delta > 0: {(diffs_cluster_r1 > 0).sum()} ({(diffs_cluster_r1 > 0).mean()*100:.2f}%)")
    print(f"  Recall@1: Delta = 0: {(diffs_cluster_r1 == 0).sum()} ({(diffs_cluster_r1 == 0).mean()*100:.2f}%)")
    print(f"  Recall@1: Delta < 0: {(diffs_cluster_r1 < 0).sum()} ({(diffs_cluster_r1 < 0).mean()*100:.2f}%)")
    print(f"  Recall@1: Mean Delta = {diffs_cluster_r1.mean()*100:+.4f}%, 95% CI: [{np.percentile(diffs_cluster_r1, 2.5)*100:.2f}%, {np.percentile(diffs_cluster_r1, 97.5)*100:.2f}%]")

    print(f"\n  Recall@3: Delta > 0: {(diffs_cluster_r3 > 0).sum()} ({(diffs_cluster_r3 > 0).mean()*100:.2f}%)")
    print(f"  Recall@3: Delta = 0: {(diffs_cluster_r3 == 0).sum()} ({(diffs_cluster_r3 == 0).mean()*100:.2f}%)")
    print(f"  Recall@3: Delta < 0: {(diffs_cluster_r3 < 0).sum()} ({(diffs_cluster_r3 < 0).mean()*100:.2f}%)")
    print(f"  Recall@3: Mean Delta = {diffs_cluster_r3.mean()*100:+.4f}%, 95% CI: [{np.percentile(diffs_cluster_r3, 2.5)*100:.2f}%, {np.percentile(diffs_cluster_r3, 97.5)*100:.2f}%]")
    print(f"  Recall@3: p-val (Delta >= 0) = {(diffs_cluster_r3 >= 0).sum()} / 10000 = {(diffs_cluster_r3 >= 0).mean():.4f}")

    print("\nStandard Paired Sample Bootstrap Breakdown (10,000 iterations, N=30):")
    print(f"  Recall@1: Mean Delta = {diffs_std_r1.mean()*100:+.4f}%, 95% CI: [{np.percentile(diffs_std_r1, 2.5)*100:.2f}%, {np.percentile(diffs_std_r1, 97.5)*100:.2f}%]")
    print(f"  Recall@3: Mean Delta = {diffs_std_r3.mean()*100:+.4f}%, 95% CI: [{np.percentile(diffs_std_r3, 2.5)*100:.2f}%, {np.percentile(diffs_std_r3, 97.5)*100:.2f}%]")
    print(f"  Recall@3: p-val (Delta >= 0) = {(diffs_std_r3 >= 0).mean():.4f}")

    # =========================================================================
    # AUDIT ITEM 2: PER-SPEAKER BREAKDOWN FOR THE 5 SPEAKERS
    # =========================================================================
    print("\n" + "=" * 80)
    print("AUDIT ITEM 2: PER-SPEAKER PERFORMANCE BREAKDOWN (5 SPEAKERS)")
    print("=" * 80)
    spk_breakdown = []
    for spk, group in df_eval.groupby('speaker_id'):
        rec = {
            'speaker_id': spk,
            'spans': len(group),
            'E0_r1': f"{group['E0_hit1'].sum()}/{len(group)} ({group['E0_hit1'].mean()*100:.1f}%)",
            'E1b_r1': f"{group['E1b_hit1'].sum()}/{len(group)} ({group['E1b_hit1'].mean()*100:.1f}%)",
            'E0_r3': f"{group['E0_hit3'].sum()}/{len(group)} ({group['E0_hit3'].mean()*100:.1f}%)",
            'E1b_r3': f"{group['E1b_hit3'].sum()}/{len(group)} ({group['E1b_hit3'].mean()*100:.1f}%)",
            'E0_r5': f"{group['E0_hit5'].sum()}/{len(group)} ({group['E0_hit5'].mean()*100:.1f}%)",
            'E1b_r5': f"{group['E1b_hit5'].sum()}/{len(group)} ({group['E1b_hit5'].mean()*100:.1f}%)",
            'E1b_crop_r3': f"{group['E1b-Crop_hit3'].sum()}/{len(group)} ({group['E1b-Crop_hit3'].mean()*100:.1f}%)",
            'E0_pos_sim': group['E0_pos_sim'].mean(),
            'E1b_pos_sim': group['E1b_pos_sim'].mean(),
            'E1b_crop_pos_sim': group['E1b-Crop_pos_sim'].mean(),
            'E0_hard_margin': group['E0_hard_margin'].mean(),
            'E1b_hard_margin': group['E1b_hard_margin'].mean()
        }
        spk_breakdown.append(rec)
    df_spk = pd.DataFrame(spk_breakdown)
    df_spk.to_csv("Data/models/speaker_performance_breakdown.csv", index=False)
    print(df_spk.to_string(index=False))

    # =========================================================================
    # AUDIT ITEM 3: LEAVE-ONE-SPEAKER-OUT (LOSO) SENSITIVITY ANALYSIS
    # =========================================================================
    print("\n" + "=" * 80)
    print("AUDIT ITEM 3: LEAVE-ONE-SPEAKER-OUT (LOSO) SENSITIVITY ANALYSIS")
    print("=" * 80)
    loso_rows = []
    for spk in speakers:
        sub = df_eval[df_eval['speaker_id'] != spk]
        e0_r1 = sub['E0_hit1'].mean() * 100
        e1b_r1 = sub['E1b_hit1'].mean() * 100
        e0_r3 = sub['E0_hit3'].mean() * 100
        e1b_r3 = sub['E1b_hit3'].mean() * 100
        e0_r5 = sub['E0_hit5'].mean() * 100
        e1b_r5 = sub['E1b_hit5'].mean() * 100
        e0_margin = sub['E0_hard_margin'].mean()
        e1b_margin = sub['E1b_hard_margin'].mean()

        loso_rows.append({
            'excluded_speaker': spk,
            'remaining_spans': len(sub),
            'E0_R1': round(e0_r1, 2),
            'E1b_R1': round(e1b_r1, 2),
            'Delta_R1': round(e1b_r1 - e0_r1, 2),
            'E0_R3': round(e0_r3, 2),
            'E1b_R3': round(e1b_r3, 2),
            'Delta_R3': round(e1b_r3 - e0_r3, 2),
            'E0_R5': round(e0_r5, 2),
            'E1b_R5': round(e1b_r5, 2),
            'Delta_R5': round(e1b_r5 - e0_r5, 2),
            'Delta_Margin': round(e1b_margin - e0_margin, 4)
        })
    df_loso = pd.DataFrame(loso_rows)
    df_loso.to_csv("Data/models/loso_sensitivity_analysis.csv", index=False)
    print(df_loso.to_string(index=False))

    # =========================================================================
    # AUDIT ITEM 4: PROMPT-LABEL CONFOUNDING (TERM X PROMPT CROSSTAB)
    # =========================================================================
    print("\n" + "=" * 80)
    print("AUDIT ITEM 4: PROMPT-LABEL CONFOUNDING AUDIT (300 TRAINING SPANS)")
    print("=" * 80)
    df_300 = pd.read_csv("Data/training_spans_300.csv")
    ct = pd.crosstab(df_300['term_id'], df_300['prompt_id'])
    ct['Total_Spans'] = ct.sum(axis=1)
    ct['Prompts_Covered'] = (ct.iloc[:, :-1] > 0).sum(axis=1)
    ct.to_csv("Data/models/term_prompt_crosstab.csv")
    print(ct.to_string())

    # Summary metrics of prompt confounding
    prompts_per_term = (ct.iloc[:, :-2] > 0).sum(axis=1)
    terms_per_prompt = (ct.iloc[:, :-2] > 0).sum(axis=0)
    print(f"\nPrompts per Term: Min={prompts_per_term.min()}, Mean={prompts_per_term.mean():.2f}, Max={prompts_per_term.max()}")
    print(f"Terms per Prompt: Min={terms_per_prompt.min()}, Mean={terms_per_prompt.mean():.2f}, Max={terms_per_prompt.max()}")
    single_prompt_terms = prompts_per_term[prompts_per_term == 1].index.tolist()
    print(f"Terms appearing in only 1 prompt: {single_prompt_terms}")

    # =========================================================================
    # AUDIT ITEM 5: HARDEST MARGIN DISTRIBUTION ANALYSIS
    # =========================================================================
    print("\n" + "=" * 80)
    print("AUDIT ITEM 5: HARDEST MARGIN & POSITIVE COSINE DISTRIBUTION (SETTING B)")
    print("=" * 80)
    dist_metrics = []
    for m in ['E0', 'E1a', 'E1b', 'E1b-Crop']:
        pos_vals = df_eval[f'{m}_pos_sim'].values
        hard_m_vals = df_eval[f'{m}_hard_margin'].values

        rec = {
            'Model': m,
            'Pos_Min': np.min(pos_vals),
            'Pos_Q25': np.percentile(pos_vals, 25),
            'Pos_Median': np.median(pos_vals),
            'Pos_Mean': np.mean(pos_vals),
            'Pos_Q75': np.percentile(pos_vals, 75),
            'Pos_Max': np.max(pos_vals),
            'Pos_Std': np.std(pos_vals),
            'Margin_Min': np.min(hard_m_vals),
            'Margin_Q10': np.percentile(hard_m_vals, 10),
            'Margin_Q25': np.percentile(hard_m_vals, 25),
            'Margin_Median': np.median(hard_m_vals),
            'Margin_Mean': np.mean(hard_m_vals),
            'Margin_Q75': np.percentile(hard_m_vals, 75),
            'Margin_Q90': np.percentile(hard_m_vals, 90),
            'Margin_Max': np.max(hard_m_vals),
            'Margin_Std': np.std(hard_m_vals),
            'Margin_Skewness': float(stats.skew(hard_m_vals))
        }
        dist_metrics.append(rec)
    df_dist = pd.DataFrame(dist_metrics)
    df_dist.to_csv("Data/models/margin_distribution_metrics.csv", index=False)
    print(df_dist[['Model', 'Margin_Min', 'Margin_Q25', 'Margin_Median', 'Margin_Mean', 'Margin_Q75', 'Margin_Max', 'Margin_Skewness']].to_string(index=False))

    # Examine why E1b-Crop has Median (-1.45) << Mean (-1.02)
    crop_m = df_eval['E1b-Crop_hard_margin'].values
    print("\nE1b-Crop Hardest Margin Bimodal/Skew Breakdown:")
    print(f"  Spans with Margin < -1.4: {(crop_m < -1.4).sum()} / 30 ({(crop_m < -1.4).mean()*100:.1f}%)")
    print(f"  Spans with Margin in [-1.4, -0.5]: {((crop_m >= -1.4) & (crop_m < -0.5)).sum()} / 30")
    print(f"  Spans with Margin >= -0.5: {(crop_m >= -0.5).sum()} / 30 (pulling the mean upwards!)")

    print(f"Worst 5 Collapsed Spans in E1b-Crop:")
    worst_crop = df_eval.sort_values(by='E1b-Crop_hard_margin').head(5)
    print(worst_crop[['audio_id', 'speaker_id', 'term', 'E1b-Crop_pos_sim', 'E1b-Crop_hard_neg_sim', 'E1b-Crop_hard_distractor', 'E1b-Crop_hard_margin']].to_string(index=False))

    # Save summary json
    audit_data = {
        'cluster_bootstrap_diff_r1': {
            'mean': float(diffs_cluster_r1.mean()),
            'ci': [float(np.percentile(diffs_cluster_r1, 2.5)), float(np.percentile(diffs_cluster_r1, 97.5))],
            'pct_positive': float((diffs_cluster_r1 > 0).mean()),
            'pct_zero': float((diffs_cluster_r1 == 0).mean()),
            'pct_negative': float((diffs_cluster_r1 < 0).mean())
        },
        'cluster_bootstrap_diff_r3': {
            'mean': float(diffs_cluster_r3.mean()),
            'ci': [float(np.percentile(diffs_cluster_r3, 2.5)), float(np.percentile(diffs_cluster_r3, 97.5))],
            'p_val_delta_ge_zero': float((diffs_cluster_r3 >= 0).mean()),
            'pct_positive': float((diffs_cluster_r3 > 0).mean()),
            'pct_zero': float((diffs_cluster_r3 == 0).mean()),
            'pct_negative': float((diffs_cluster_r3 < 0).mean())
        },
        'std_bootstrap_diff_r3': {
            'mean': float(diffs_std_r3.mean()),
            'ci': [float(np.percentile(diffs_std_r3, 2.5)), float(np.percentile(diffs_std_r3, 97.5))],
            'p_val': float((diffs_std_r3 >= 0).mean())
        },
        'single_prompt_terms': single_prompt_terms,
        'dist_metrics': dist_metrics
    }
    with open("Data/models/e1_deep_audit_results.json", "w", encoding="utf-8") as f:
        json.dump(audit_data, f, indent=2)

    print("\nAudit successfully executed and all outputs saved.")

if __name__ == '__main__':
    main()
