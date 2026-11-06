import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import numpy as np
import json

df_508 = pd.read_csv('Data/benchmark_results/unseen_predictions_508.csv')

# Unroll term occurrences
records = []
for _, r in df_508.iterrows():
    p = r['prompt_id']
    t_raw = r['gold_unseen_terms']
    if isinstance(t_raw, str):
        # Could be "['Term']" or "Term1;Term2"
        if t_raw.startswith('['):
            try:
                t_list = json.loads(t_raw.replace("'", '"'))
            except Exception:
                t_list = [t_raw]
        else:
            t_list = t_raw.split(';')
        for t in t_list:
            t = t.strip()
            if t:
                records.append({'prompt_id': p, 'term': t})

df_terms = pd.DataFrame(records)
print(f"Total term occurrences unrolled: {len(df_terms)}")
ct = pd.crosstab(df_terms['term'], df_terms['prompt_id'])
print("\nContingency Table (Term x Prompt on 508 Test Benchmark):")
print(ct)

# Calculate Information Theoretic Quantities on Test Set
N = len(df_terms)
p_tp = ct.values / N
p_p = p_tp.sum(axis=0)
p_t = p_tp.sum(axis=1)

mi = 0.0
for i in range(len(p_t)):
    for j in range(len(p_p)):
        if p_tp[i, j] > 0:
            mi += p_tp[i, j] * np.log2(p_tp[i, j] / (p_t[i] * p_p[j]))

h_t = -np.sum(p_t * np.log2(p_t))
h_p = -np.sum(p_p * np.log2(p_p))

print(f"\nH(Term) on Test Set   = {h_t:.4f} bits (Max log2(6) = {np.log2(6):.4f} bits)")
print(f"H(Prompt) on Test Set = {h_p:.4f} bits (Max log2(4) = {np.log2(4):.4f} bits)")
print(f"Mutual Information I(Term; Prompt) = {mi:.4f} bits")
print(f"Relative NMI I / H(Term) = {mi / h_t * 100:.2f}%\n")
