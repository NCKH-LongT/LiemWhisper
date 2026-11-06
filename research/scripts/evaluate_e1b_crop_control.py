import os
import sys
import json
import time
import numpy as np
import pandas as pd
import soundfile as sf
import torch
import torch.nn.functional as F
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

def paired_speaker_cluster_bootstrap(sample_df, metric_col_a, metric_col_b, n_boot=10000, seed=42):
    np.random.seed(seed)
    speakers = sample_df['speaker_id'].unique()
    diffs = []
    vals_a = []
    vals_b = []

    for _ in range(n_boot):
        boot_speakers = np.random.choice(speakers, size=len(speakers), replace=True)
        boot_samples = pd.concat([sample_df[sample_df['speaker_id'] == spk] for spk in boot_speakers])
        va = boot_samples[metric_col_a].mean()
        vb = boot_samples[metric_col_b].mean()
        vals_a.append(va)
        vals_b.append(vb)
        diffs.append(vb - va)

    ci_a = (np.percentile(vals_a, 2.5), np.percentile(vals_a, 97.5))
    ci_b = (np.percentile(vals_b, 2.5), np.percentile(vals_b, 97.5))
    ci_diff = (np.percentile(diffs, 2.5), np.percentile(diffs, 97.5))
    p_val = (np.array(diffs) <= 0).mean() if np.mean(diffs) > 0 else (np.array(diffs) >= 0).mean()

    return {
        'mean_a': float(np.mean(vals_a)),
        'ci_a': [float(ci_a[0]), float(ci_a[1])],
        'mean_b': float(np.mean(vals_b)),
        'ci_b': [float(ci_b[0]), float(ci_b[1])],
        'mean_diff': float(np.mean(diffs)),
        'ci_diff': [float(ci_diff[0]), float(ci_diff[1])],
        'p_val': float(p_val)
    }

def main():
    print("=" * 80)
    print("PHASE E1b & E1b-CROP CONTROL EVALUATION")
    print("=" * 80)

    # 1. Load Alignment Gold Test Spans (30 Spans across 6 Unseen Terms)
    gold_spans_path = "Data/span_alignment_gold.csv"
    if not os.path.exists(gold_spans_path):
        gold_spans_path = "C:/Users/ACER/.gemini/antigravity/brain/188b44ec-9425-4d1c-852d-6957627afff6/span_alignment_gold.csv"
    
    df_spans = pd.read_csv(gold_spans_path)
    # Strictly filter for unseen test spans
    unseen_set = set(t.lower() for t in UNSEEN_TEST_TERMS)
    test_spans = df_spans[df_spans['term'].str.lower().isin(unseen_set) & (df_spans['split'] == 'unseen_test')].copy()
    print(f"Loaded unseen test spans: {len(test_spans)} spans across {test_spans['term'].nunique()} terms.")
    assert len(test_spans) == 30, f"Expected 30 test spans, got {len(test_spans)}"

    # 2. Load Models
    fe = WhisperFeatureExtractor.from_pretrained("openai/whisper-tiny")
    audio_model = WhisperModel.from_pretrained("openai/whisper-tiny")
    audio_model.eval()

    tok = AutoTokenizer.from_pretrained("google-t5/t5-small")
    text_model = AutoModel.from_pretrained("google-t5/t5-small")
    text_model.eval()

    # Load Base Global Checkpoint
    base_ckpt = torch.load("Data/models/contrastive_open_vocab/best_contrastive_model.pt", map_location="cpu")
    base_model = AudioTextContrastiveModel(audio_in_dim=384, text_in_dim=512, shared_dim=256)
    base_model.load_state_dict(base_ckpt)
    base_model.eval()

    # Load E1b Checkpoint (Dedicated Span Head)
    e1b_ckpt = torch.load("Data/models/e1b_span_model.pt", map_location="cpu")
    e1b_span_head = AudioProjectionHead(in_features=384, shared_dim=256)
    e1b_span_head.load_state_dict(e1b_ckpt['span_audio_head_state_dict'])
    e1b_span_head.eval()

    # Canonical 24 Terms & 6 Unseen Terms
    all_terms_meta_path = "Data/features_contrastive/terms_meta.json"
    with open(all_terms_meta_path, 'r', encoding='utf-8') as f:
        meta = json.load(f)
    all_24_terms = meta['all_terms']
    unseen_6_terms = UNSEEN_TEST_TERMS

    # Compute text prototype embeddings
    with torch.no_grad():
        t_inputs_24 = tok(all_24_terms, padding=True, truncation=True, return_tensors="pt")
        text_raw_24 = text_model.encoder(**t_inputs_24).last_hidden_state.mean(dim=1)
        text_embs_24 = base_model.text_proj(text_raw_24).numpy() # [24, 256]

        t_inputs_6 = tok(unseen_6_terms, padding=True, truncation=True, return_tensors="pt")
        text_raw_6 = text_model.encoder(**t_inputs_6).last_hidden_state.mean(dim=1)
        text_embs_6 = base_model.text_proj(text_raw_6).numpy() # [6, 256]

    # 3. Extract Representations for 4 Configurations on the 30 Test Spans
    df_gold = pd.read_csv("Data/gold_with_asr_v1.csv").set_index('recording_id')
    wav_dir = "Data/wav_16k"

    feats_e0 = []       # Global Pooling + Global Head
    feats_e1a = []      # Span Pooling + Global Head
    feats_e1b = []      # Span Pooling + Dedicated Span Head
    feats_e1b_crop = [] # Pure Waveform Crop + Dedicated Span Head

    for idx, row in test_spans.iterrows():
        rec_id = row['audio_id']
        wav_file = df_gold.loc[rec_id, 'wav_file']
        wav_path = os.path.join(wav_dir, wav_file)
        wav, sr = sf.read(wav_path)

        t_start = row['start_time']
        t_end = row['end_time']

        # A. Full Utterance Encoding
        inputs = fe(wav, sampling_rate=sr, return_tensors="pt")
        with torch.no_grad():
            enc_out = audio_model.encoder(inputs.input_features).last_hidden_state.squeeze(0) # [T, 384]

            # E0: Global Mean Pool
            global_raw = enc_out.mean(dim=0, keepdim=True) # [1, 384]
            z_e0 = base_model.audio_proj(global_raw).squeeze(0).numpy()
            feats_e0.append(z_e0)

            # E1a & E1b: Contextualized Span Mean Pool
            total_frames = enc_out.shape[0]
            f_start = max(0, min(total_frames - 1, int(round(t_start * 50.0))))
            f_end = max(f_start + 1, min(total_frames, int(round(t_end * 50.0))))
            span_raw = enc_out[f_start:f_end, :].mean(dim=0, keepdim=True) # [1, 384]

            # E1a: Global Head
            z_e1a = base_model.audio_proj(span_raw).squeeze(0).numpy()
            feats_e1a.append(z_e1a)

            # E1b: Dedicated Span Head
            z_e1b = e1b_span_head(span_raw).squeeze(0).numpy()
            feats_e1b.append(z_e1b)

            # B. Pure Waveform Crop Encoding (Context Control: E1b-Crop)
            s_idx = max(0, int(t_start * sr))
            e_idx = min(len(wav), int(t_end * sr))
            crop_wav = wav[s_idx:e_idx]
            if len(crop_wav) < int(0.1 * sr): # Ensure at least 0.1s
                crop_wav = wav[s_idx : min(len(wav), s_idx + int(0.5 * sr))]

            crop_inputs = fe(crop_wav, sampling_rate=sr, return_tensors="pt")
            crop_enc = audio_model.encoder(crop_inputs.input_features).last_hidden_state.squeeze(0) # [T_crop, 384]
            crop_raw = crop_enc.mean(dim=0, keepdim=True)
            z_crop = e1b_span_head(crop_raw).squeeze(0).numpy()
            feats_e1b_crop.append(z_crop)

    Z_e0 = np.array(feats_e0)
    Z_e1a = np.array(feats_e1a)
    Z_e1b = np.array(feats_e1b)
    Z_e1b_crop = np.array(feats_e1b_crop)

    models_dict = {
        'E0 (Global Baseline)': Z_e0,
        'E1a (Diagnostic Span)': Z_e1a,
        'E1b (Dedicated Span Head)': Z_e1b,
        'E1b-Crop (Context Control)': Z_e1b_crop
    }

    # 4. Evaluation Function
    def evaluate_setting(candidate_terms, text_embs, setting_name):
        print("\n" + "=" * 80)
        print(f"EVALUATING {setting_name.upper()} ({len(candidate_terms)} CANDIDATE TERMS)")
        print("=" * 80)

        results = {}
        eval_records = []

        for m_name, Z_audio in models_dict.items():
            sims = np.dot(Z_audio, text_embs.T) # [30, N_terms]
            r1_hits = []
            r3_hits = []
            r5_hits = []
            pos_sims = []
            hard_margins = []
            mean_margins = []

            for i, row in test_spans.reset_index(drop=True).iterrows():
                target_term = row['term']
                gt_idx = candidate_terms.index(target_term)
                target_sim = sims[i, gt_idx]
                
                # Ranked predictions
                rank_order = np.argsort(-sims[i])
                rank = int(np.where(rank_order == gt_idx)[0][0]) + 1
                
                hit1 = 1 if rank <= 1 else 0
                hit3 = 1 if rank <= 3 else 0
                hit5 = 1 if rank <= 5 else 0

                r1_hits.append(hit1)
                r3_hits.append(hit3)
                r5_hits.append(hit5)

                # Margins
                all_c = sims[i].copy()
                all_c[gt_idx] = -999.0
                hardest_neg = np.max(all_c)
                mean_neg = np.mean([s for idx_s, s in enumerate(sims[i]) if idx_s != gt_idx])

                pos_sims.append(target_sim)
                hard_margins.append(target_sim - hardest_neg)
                mean_margins.append(target_sim - mean_neg)

                eval_records.append({
                    'model': m_name,
                    'setting': setting_name,
                    'audio_id': row['audio_id'],
                    'speaker_id': row['speaker_id'],
                    'term': target_term,
                    'rank': rank,
                    'hit1': hit1,
                    'hit3': hit3,
                    'hit5': hit5,
                    'pos_sim': target_sim,
                    'hard_margin': target_sim - hardest_neg
                })

            results[m_name] = {
                'Recall@1': float(np.mean(r1_hits) * 100),
                'Recall@3': float(np.mean(r3_hits) * 100),
                'Recall@5': float(np.mean(r5_hits) * 100),
                'Pos_Sim_Mean': float(np.mean(pos_sims)),
                'Pos_Sim_Std': float(np.std(pos_sims)),
                'Mean_Margin': float(np.mean(mean_margins)),
                'Hard_Margin_Mean': float(np.mean(hard_margins)),
                'Hard_Margin_Median': float(np.median(hard_margins))
            }

        df_res = pd.DataFrame(results).T
        print(df_res.to_string())
        return df_res, pd.DataFrame(eval_records)

    res_a, recs_a = evaluate_setting(all_24_terms, text_embs_24, "Setting A (24 Terms)")
    res_b, recs_b = evaluate_setting(unseen_6_terms, text_embs_6, "Setting B (6 Unseen Terms)")

    # 5. Paired Speaker-Cluster Bootstrap on Setting B (E0 vs E1b, and E1b vs E1b-Crop)
    print("\n" + "=" * 80)
    print("PAIRED SPEAKER-CLUSTER BOOTSTRAP (10,000 ITERATIONS) ON SETTING B")
    print("=" * 80)
    
    # Pivot Setting B records
    piv_b = recs_b.pivot(index=['audio_id', 'speaker_id', 'term'], columns='model', values=['hit1', 'hit3', 'hit5', 'hard_margin'])
    piv_b.columns = [f"{col[0]}_{col[1]}" for col in piv_b.columns]
    piv_b = piv_b.reset_index()

    boot_e1b_vs_e0_r1 = paired_speaker_cluster_bootstrap(piv_b, 'hit1_E0 (Global Baseline)', 'hit1_E1b (Dedicated Span Head)')
    boot_e1b_vs_e0_r3 = paired_speaker_cluster_bootstrap(piv_b, 'hit3_E0 (Global Baseline)', 'hit3_E1b (Dedicated Span Head)')
    boot_e1b_vs_crop_r1 = paired_speaker_cluster_bootstrap(piv_b, 'hit1_E1b-Crop (Context Control)', 'hit1_E1b (Dedicated Span Head)')
    boot_e1b_vs_crop_r3 = paired_speaker_cluster_bootstrap(piv_b, 'hit3_E1b-Crop (Context Control)', 'hit3_E1b (Dedicated Span Head)')

    print(f"E1b vs E0 [Recall@1]: Delta = {boot_e1b_vs_e0_r1['mean_diff']*100:+.2f}%, 95% CI [{boot_e1b_vs_e0_r1['ci_diff'][0]*100:.2f}%, {boot_e1b_vs_e0_r1['ci_diff'][1]*100:.2f}%], p-val = {boot_e1b_vs_e0_r1['p_val']:.4f}")
    print(f"E1b vs E0 [Recall@3]: Delta = {boot_e1b_vs_e0_r3['mean_diff']*100:+.2f}%, 95% CI [{boot_e1b_vs_e0_r3['ci_diff'][0]*100:.2f}%, {boot_e1b_vs_e0_r3['ci_diff'][1]*100:.2f}%], p-val = {boot_e1b_vs_e0_r3['p_val']:.4f}")
    print(f"E1b vs E1b-Crop [Recall@1]: Delta = {boot_e1b_vs_crop_r1['mean_diff']*100:+.2f}%, 95% CI [{boot_e1b_vs_crop_r1['ci_diff'][0]*100:.2f}%, {boot_e1b_vs_crop_r1['ci_diff'][1]*100:.2f}%], p-val = {boot_e1b_vs_crop_r1['p_val']:.4f}")
    print(f"E1b vs E1b-Crop [Recall@3]: Delta = {boot_e1b_vs_crop_r3['mean_diff']*100:+.2f}%, 95% CI [{boot_e1b_vs_crop_r3['ci_diff'][0]*100:.2f}%, {boot_e1b_vs_crop_r3['ci_diff'][1]*100:.2f}%], p-val = {boot_e1b_vs_crop_r3['p_val']:.4f}")

    # 6. Save Complete Evaluation Results
    final_output = {
        'setting_a_summary': res_a.to_dict(),
        'setting_b_summary': res_b.to_dict(),
        'bootstrap': {
            'e1b_vs_e0_r1': boot_e1b_vs_e0_r1,
            'e1b_vs_e0_r3': boot_e1b_vs_e0_r3,
            'e1b_vs_crop_r1': boot_e1b_vs_crop_r1,
            'e1b_vs_crop_r3': boot_e1b_vs_crop_r3
        }
    }

    out_json = "Data/models/e1b_crop_evaluation.json"
    with open(out_json, "w", encoding="utf-8") as f:
        json.dump(final_output, f, indent=2)
    print(f"\nEvaluation successfully saved to: {out_json}")

if __name__ == '__main__':
    main()
