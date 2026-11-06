import sys, io, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.path.insert(0, os.path.abspath("Liem/LiemWhisper/research/src/liemwhisper"))

import json
import numpy as np
import pandas as pd
import torch
from transformers import AutoTokenizer, AutoModel
from open_vocab_contrastive import AudioTextContrastiveModel

# Load E0 model and terms
with open("Data/features_contrastive/terms_meta.json", "r", encoding="utf-8") as f:
    meta = json.load(f)

test_terms = meta["test_terms"] # 6 unseen terms
term_text_embs = np.load("Data/features_contrastive/term_text_embs.npy") # [24, 512]
term_to_idx = meta["term_to_idx"]
unseen_idx = [term_to_idx[t] for t in test_terms]

# Load Contrastive Model text projection
model = AudioTextContrastiveModel(audio_in_dim=384, text_in_dim=512, shared_dim=256)
model.load_state_dict(torch.load("Data/models/contrastive_open_vocab/best_contrastive_model.pt", map_location="cpu"))
model.eval()

with torch.no_grad():
    t_text = torch.tensor(term_text_embs[unseen_idx], dtype=torch.float32)
    z_terms = model.text_proj(t_text).numpy()
    z_terms = z_terms / np.linalg.norm(z_terms, axis=1, keepdims=True) # [6, 256]

# Load T5 tokenizer and encoder to encode the prompt texts
tokenizer = AutoTokenizer.from_pretrained("google-t5/t5-small")
t5_model = AutoModel.from_pretrained("google-t5/t5-small")
t5_model.eval()

gold = pd.read_csv('Data/gold_with_asr_v1.csv')
prompt_dict = gold[['prompt_id', 'prompt_text']].drop_duplicates().set_index('prompt_id')['prompt_text'].to_dict()

prompt_preds = {}
print("=== PROMPT TEXT ENCODING & UNSEEN TERM MATCHING ===")
for pid in ['Q01', 'Q10', 'Q14', 'Q15']:
    ptext = prompt_dict[pid]
    inputs = tokenizer(ptext, return_tensors="pt", truncation=True, max_length=128)
    with torch.no_grad():
        out = t5_model.encoder(**inputs).last_hidden_state.mean(dim=1)
        z_p = model.text_proj(out).numpy()[0]
        z_p = z_p / np.linalg.norm(z_p)
    
    sims = np.dot(z_terms, z_p)
    ranked_indices = np.argsort(-sims)
    ranked_terms = [test_terms[i] for i in ranked_indices]
    prompt_preds[pid] = ranked_terms
    print(f"\nPrompt {pid}: {ptext[:65]}...")
    for rank, idx in enumerate(ranked_indices):
        print(f"  Rank {rank+1}: {test_terms[idx]:30} (Sim: {sims[idx]:+.4f})")

# Evaluate this Text-Only Prompt Baseline on the 508 benchmark!
df_508 = pd.read_csv('Data/benchmark_results/unseen_predictions_508.csv')
p_r1, p_r3, p_r5 = [], [], []

for _, r in df_508.iterrows():
    pid = r['prompt_id']
    preds = prompt_preds[pid]
    gt_raw = r['gold_unseen_terms']
    if gt_raw.startswith('['):
        gts = json.loads(gt_raw.replace("'", '"'))
    else:
        gts = gt_raw.split(';')
    
    hits_1 = sum(1 for g in gts if g == preds[0])
    hits_3 = sum(1 for g in gts if g in preds[:3])
    hits_5 = sum(1 for g in gts if g in preds[:5])
    
    p_r1.append(hits_1 / len(gts))
    p_r3.append(hits_3 / len(gts))
    p_r5.append(hits_5 / len(gts))

print("\n=== TEXT-ONLY PROMPT BASELINE PERFORMANCE ON 508 BENCHMARK ===")
print(f"Macro Recall@1 : {np.mean(p_r1)*100:.2f}%")
print(f"Macro Recall@3 : {np.mean(p_r3)*100:.2f}%")
print(f"Macro Recall@5 : {np.mean(p_r5)*100:.2f}%")

# Weighted micro
gold_counts = df_508['gold_count'].values
micro_r1 = np.sum(np.array(p_r1) * gold_counts) / np.sum(gold_counts)
micro_r3 = np.sum(np.array(p_r3) * gold_counts) / np.sum(gold_counts)
micro_r5 = np.sum(np.array(p_r5) * gold_counts) / np.sum(gold_counts)
print(f"Micro Recall@1 : {micro_r1*100:.2f}%")
print(f"Micro Recall@3 : {micro_r3*100:.2f}%")
print(f"Micro Recall@5 : {micro_r5*100:.2f}%")
