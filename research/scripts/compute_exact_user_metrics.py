import sys, io, os, json
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
import pandas as pd
import numpy as np
from rapidfuzz.distance import Levenshtein

ground_truths = [
    "Trong quá trình đánh giá chất lượng phần mềm, QA cần phân tích False Positive Rate, False Negative Rate, Precision, Recall và F1-Score để xác định mức độ chính xác của hệ thống phân loại lỗi.",
    "Khi kiểm thử ứng dụng web, nhóm QA cần đánh giá cơ chế Cross-Origin Resource Sharing (CORS), kiểm tra khả năng chống Cross-Site Request Forgery (CSRF) và xác minh tính an toàn của Content Security Policy (CSP).",
    "Trong quá trình kiểm thử cơ sở dữ liệu, kỹ sư cần kiểm tra Database Normalization, đánh giá hiệu suất Query Optimization, phát hiện N+1 Query Problem và xác minh cơ chế Transaction Isolation.",
    "Khi đánh giá hệ thống phân tán, QA cần kiểm tra Service Discovery, xác minh cơ chế Load Balancing, phân tích Network Partitioning và đánh giá khả năng duy trì High Availability.",
    "Trong quá trình kiểm thử mô hình học máy, nhóm nghiên cứu cần đánh giá Overfitting, Underfitting, Feature Extraction, Hyperparameter Tuning và khả năng Model Generalization trên dữ liệu thực tế.",
    "Khi phát triển hệ thống nhận dạng giọng nói, nhóm nghiên cứu cần phân tích Phoneme Recognition, đánh giá Acoustic Modeling, kiểm tra Language Modeling và xác minh khả năng xử lý Background Noise trong môi trường ghi âm phức tạp.",
    "Trong quá trình đánh giá dữ liệu huấn luyện AI, chuyên gia cần kiểm tra Data Augmentation, phát hiện Label Noise, đánh giá Sampling Bias và xác minh tính đại diện của Training Distribution so với dữ liệu triển khai thực tế.",
    "Khi kiểm thử hệ thống CI/CD, kỹ sư cần xác minh Build Pipeline, đánh giá cơ chế Automated Deployment, kiểm tra Rollback Strategy và phân tích các lỗi phát sinh trong quá trình Continuous Integration.",
    "Trong quá trình đánh giá mô hình nhận dạng thuật ngữ chuyên ngành, nhóm nghiên cứu cần kiểm tra Zero-Shot Learning, phân tích Contrastive Loss, đánh giá Cosine Similarity và xác minh khả năng phân biệt các thuật ngữ thông qua Embedding Space.",
    "Khi kiểm thử hiệu năng nền tảng trực tuyến, QA cần đo lường Response Time, phân tích Throughput, kiểm tra Latency ở phân vị P95 và P99, đồng thời đánh giá mức tiêu thụ CPU Utilization và Memory Footprint khi hệ thống hoạt động liên tục."
]

key_terms = [
    ["False Positive Rate", "False Negative Rate", "Precision", "Recall", "F1-Score"],
    ["Cross-Origin Resource Sharing", "CORS", "Cross-Site Request Forgery", "CSRF", "Content Security Policy", "CSP"],
    ["Database Normalization", "Query Optimization", "N+1 Query Problem", "Transaction Isolation"],
    ["Service Discovery", "Load Balancing", "Network Partitioning", "High Availability"],
    ["Overfitting", "Underfitting", "Feature Extraction", "Hyperparameter Tuning", "Model Generalization"],
    ["Phoneme Recognition", "Acoustic Modeling", "Language Modeling", "Background Noise"],
    ["Data Augmentation", "Label Noise", "Sampling Bias", "Training Distribution"],
    ["Build Pipeline", "Automated Deployment", "Rollback Strategy", "Continuous Integration"],
    ["Zero-Shot Learning", "Contrastive Loss", "Cosine Similarity", "Embedding Space"],
    ["Response Time", "Throughput", "Latency", "P95", "P99", "CPU Utilization", "Memory Footprint"]
]

total_terms = sum(len(ts) for ts in key_terms)
df = pd.read_csv("Data/benchmark_results/user_recordings_benchmark.csv")

def norm(text):
    if not isinstance(text, str):
        return ""
    import re
    text = text.lower()
    text = re.sub(r'[^\w\s]', ' ', text)
    return " ".join(text.split())

def calc_wer(ref, hyp):
    r_words = norm(ref).split()
    h_words = norm(hyp).split()
    if not r_words:
        return 1.0 if h_words else 0.0
    dist = Levenshtein.distance(r_words, h_words)
    return dist / len(r_words)

def calc_cer(ref, hyp):
    r_chars = list(norm(ref).replace(" ", ""))
    h_chars = list(norm(hyp).replace(" ", ""))
    if not r_chars:
        return 1.0 if h_chars else 0.0
    dist = Levenshtein.distance(r_chars, h_chars)
    return dist / len(r_chars)

models = ["whisper_tiny", "whisper_base", "whisper_small"]
wers = {m: [] for m in models}
cers = {m: [] for m in models}
term_hits = {m: 0 for m in models}
eval_results = []

for i in range(10):
    ref = ground_truths[i]
    terms = key_terms[i]
    row = df.iloc[i]
    s_res = {"sentence_id": i+1, "ref": ref, "terms": terms}
    for m in models:
        hyp = str(row[m]) if pd.notna(row[m]) else ""
        wer = calc_wer(ref, hyp)
        cer = calc_cer(ref, hyp)
        wers[m].append(wer)
        cers[m].append(cer)
        h_norm = norm(hyp)
        hits = [t for t in terms if norm(t) in h_norm]
        term_hits[m] += len(hits)
        s_res[f"{m}_hyp"] = hyp
        s_res[f"{m}_wer"] = round(wer * 100, 2)
        s_res[f"{m}_cer"] = round(cer * 100, 2)
        s_res[f"{m}_term_hits"] = hits
    eval_results.append(s_res)

print("=" * 80)
print("OVERALL 10-SENTENCE BENCHMARK SUMMARY")
print("=" * 80)
for m in models:
    mean_wer = np.mean(wers[m]) * 100
    mean_cer = np.mean(cers[m]) * 100
    t_rec = term_hits[m] / total_terms * 100
    print(f"Model: {m:15} | Corpus WER: {mean_wer:5.2f}% | Corpus CER: {mean_cer:5.2f}% | Term Recall: {t_rec:5.2f}% ({term_hits[m]}/{total_terms})")

out_file = "Data/benchmark_results/user_10_sentences_eval.json"
with open(out_file, "w", encoding="utf-8") as f:
    json.dump({
        "models_summary": {
            m: {
                "mean_wer": round(float(np.mean(wers[m])) * 100, 2),
                "mean_cer": round(float(np.mean(cers[m])) * 100, 2),
                "term_recall": round(term_hits[m] / total_terms * 100, 2),
                "term_hits": term_hits[m],
                "total_terms": total_terms
            } for m in models
        },
        "sentence_details": eval_results
    }, f, indent=2, ensure_ascii=False)

print(f"\nSaved detailed evaluation to {out_file}")
