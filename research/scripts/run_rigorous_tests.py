import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import numpy as np
import scipy.stats as stats

df = pd.read_csv('Data/models/test_30_detailed_eval.csv')
print(f"Loaded {len(df)} test spans.")

y_e0 = df['E0_hit3'].values.astype(int)
y_e1b = df['E1b_hit3'].values.astype(int)

diff = y_e1b - y_e0 # Negative means E0 is better
obs_delta = diff.mean() # -0.20 (-20 pp)
print(f"Observed Delta (E1b - E0): {obs_delta*100:.2f} pp")

b = np.sum((y_e0 == 1) & (y_e1b == 0)) # E0 won
c = np.sum((y_e0 == 0) & (y_e1b == 1)) # E1b won
a = np.sum((y_e0 == 1) & (y_e1b == 1)) # both won
d = np.sum((y_e0 == 0) & (y_e1b == 0)) # both lost

print(f"Contingency: E0 won={b}, E1b won={c}, Both correct={a}, Both wrong={d}")

# McNemar's exact test (binomial distribution with n = b + c = 6, p = 0.5)
mcnemar_exact_one_sided = stats.binom.cdf(c, b + c, 0.5)
mcnemar_exact_two_sided = 2 * mcnemar_exact_one_sided
print(f"\n1. McNemar's Exact Binomial Test (on discordant pairs n={b+c}):")
print(f"   One-sided p (P(C <= {c})) = {mcnemar_exact_one_sided:.4f} (or {mcnemar_exact_one_sided*100:.2f}%)")
print(f"   Two-sided p = {mcnemar_exact_two_sided:.4f} ({mcnemar_exact_two_sided*100:.2f}%)")

# Paired Permutation Test (100,000 iterations)
np.random.seed(42)
n_perm = 100000
perm_deltas = np.zeros(n_perm)
for i in range(n_perm):
    signs = np.random.choice([-1, 1], size=len(diff))
    perm_deltas[i] = (diff * signs).mean()

p_perm_one_sided = np.mean(perm_deltas <= obs_delta)
p_perm_two_sided = np.mean(np.abs(perm_deltas) >= np.abs(obs_delta))

print(f"\n2. Paired Permutation Test (100,000 iterations):")
print(f"   One-sided p (Delta <= {obs_delta:.2f}) = {p_perm_one_sided:.4f} ({np.sum(perm_deltas <= obs_delta)}/{n_perm})")
print(f"   Two-sided p (|Delta| >= {np.abs(obs_delta):.2f}) = {p_perm_two_sided:.4f} ({np.sum(np.abs(perm_deltas) >= np.abs(obs_delta))}/{n_perm})")

# Cluster-Level Permutation Test (5 speakers)
# Under H0, swap speaker results between E0 and E1b
speakers = df['speaker_id'].unique()
n_spk = len(speakers)
print(f"\n3. Cluster Permutation Test (Exact 2^5 = 32 cluster permutations across 5 speakers):")
# Compute speaker deltas
spk_deltas = []
for spk in speakers:
    sub = df[df['speaker_id'] == spk]
    spk_deltas.append((sub['E1b_hit3'].values - sub['E0_hit3'].values).mean())
spk_deltas = np.array(spk_deltas)
print("   Speaker Deltas (E1b - E0):", [f"{x*100:.1f}pp" for x in spk_deltas])

# Enumerate all 2^5 = 32 sign flips
all_cluster_deltas = []
for i in range(32):
    pattern = [(i >> b) & 1 for b in range(5)]
    signs = np.array([1 if p == 0 else -1 for p in pattern])
    all_cluster_deltas.append(np.mean(spk_deltas * signs))

all_cluster_deltas = np.array(all_cluster_deltas)
obs_cluster_delta = np.mean(spk_deltas)
p_cluster_one_sided = np.mean(all_cluster_deltas <= obs_cluster_delta)
p_cluster_two_sided = np.mean(np.abs(all_cluster_deltas) >= np.abs(obs_cluster_delta))
print(f"   Exact Cluster Permutation One-sided p = {p_cluster_one_sided:.4f} ({np.sum(all_cluster_deltas <= obs_cluster_delta)}/32)")
print(f"   Exact Cluster Permutation Two-sided p = {p_cluster_two_sided:.4f} ({np.sum(np.abs(all_cluster_deltas) >= np.abs(obs_cluster_delta))}/32)")
