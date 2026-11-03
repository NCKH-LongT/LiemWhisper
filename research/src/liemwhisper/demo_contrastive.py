"""
LiemWhisper Interactive CLI: Audio-Text Contrastive FAISS Retrieval Tester
==========================================================================
Allows testing zero-shot / open-vocabulary technical term retrieval on any audio file:
    python Liem/LiemWhisper/research/src/liemwhisper/demo_contrastive.py
    python Liem/LiemWhisper/research/src/liemwhisper/demo_contrastive.py --audio "Data/wav_16k/SE171761_Cau14_492d2466.wav"
"""

import os
import sys
import json
import time
import argparse
import numpy as np
import soundfile as sf
import torch

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from transformers import WhisperModel, WhisperFeatureExtractor

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from open_vocab_contrastive import AudioTextContrastiveModel, FaissTermRetriever


class ContrastiveRetrievalEngine:
    def __init__(
        self,
        model_dir: str = "Data/models/contrastive_open_vocab",
        features_dir: str = "Data/features_contrastive"
    ):
        print("Đang khởi tạo LiemWhisper Contrastive Retrieval Engine...", flush=True)

        with open(os.path.join(features_dir, "terms_meta.json"), "r", encoding="utf-8") as f:
            self.meta = json.load(f)

        self.all_terms = self.meta["all_terms"]
        self.test_terms = self.meta["test_terms"] # 6 Unseen terms
        term_text_embs = np.load(os.path.join(features_dir, "term_text_embs.npy"))

        # Load Audio Encoder
        print("  * Loading Whisper-tiny acoustic encoder...", flush=True)
        self.fe = WhisperFeatureExtractor.from_pretrained("openai/whisper-tiny")
        self.audio_model = WhisperModel.from_pretrained("openai/whisper-tiny")
        self.audio_model.eval()

        # Load Contrastive Model
        print("  * Loading Audio-Text Projection Model...", flush=True)
        model_path = os.path.join(model_dir, "best_contrastive_model.pt")
        self.contrastive_model = AudioTextContrastiveModel(audio_in_dim=384, text_in_dim=512, shared_dim=256)
        self.contrastive_model.load_state_dict(torch.load(model_path, map_location="cpu"))
        self.contrastive_model.eval()

        # Build FAISS Indices
        print("  * Projecting text embeddings & building FAISS index...", flush=True)
        with torch.no_grad():
            t_text = torch.tensor(term_text_embs, dtype=torch.float32)
            z_text = self.contrastive_model.text_proj(t_text).numpy()
            z_text = z_text / np.linalg.norm(z_text, axis=1, keepdims=True)

        self.retriever_all = FaissTermRetriever(self.all_terms, z_text)

        unseen_indices = [self.meta["term_to_idx"][t] for t in self.test_terms]
        self.retriever_unseen = FaissTermRetriever(self.test_terms, z_text[unseen_indices])
        print("Engine sẵn sàng!\n", flush=True)

    def predict_from_audio(self, wav_path: str, k: int = 5):
        if not os.path.exists(wav_path):
            print(f"Lỗi: Không tìm thấy file {wav_path}")
            return None

        t0 = time.time()
        wav, sr = sf.read(wav_path)
        inputs = self.fe(wav, sampling_rate=sr, return_tensors="pt")
        with torch.no_grad():
            enc_out = self.audio_model.encoder(inputs.input_features).last_hidden_state
            pooled = enc_out.mean(dim=1) # [1, 384]
            z_audio = self.contrastive_model.audio_proj(pooled).numpy()
            z_audio = z_audio / np.linalg.norm(z_audio, axis=1, keepdims=True)

        preds_all = self.retriever_all.retrieve(z_audio, k=k)
        preds_unseen = self.retriever_unseen.retrieve(z_audio, k=min(k, len(self.test_terms)))
        dt = (time.time() - t0) * 1000.0

        return {
            "wav_path": wav_path,
            "latency_ms": round(dt, 1),
            "top_candidates_all": preds_all,
            "top_candidates_unseen": preds_unseen
        }


def print_results(res):
    if not res:
        return
    print("=" * 80)
    print("KẾT QUẢ TRUY XUẤT THUẬT NGỮ TỰ ĐỘNG BẰNG FAISS CONTRASTIVE")
    print("=" * 80)
    print(f"File âm thanh : {res['wav_path']}")
    print(f"Thời gian xử lý: {res['latency_ms']} ms")

    print("\n1. TOP DỰ ĐOÁN TRONG TOÀN BỘ 24 THUẬT NGỮ (FULL POOL):")
    for p in res["top_candidates_all"]:
        bar = "█" * int(p["similarity"] * 25)
        print(f"   Top {p['rank']}: {p['term']:32} | Cosine: {p['similarity']:.4f} {bar}")

    print("\n2. TOP DỰ ĐOÁN TRONG 6 THUẬT NGỮ UNSEEN (CHƯA TỪNG THẤY KHI TRAIN):")
    for p in res["top_candidates_unseen"]:
        bar = "█" * int(p["similarity"] * 25)
        print(f"   Top {p['rank']}: {p['term']:32} | Cosine: {p['similarity']:.4f} {bar}")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="LiemWhisper Contrastive FAISS Retrieval Tester")
    parser.add_argument("--audio", type=str, default=None, help="Đường dẫn file .wav cần kiểm tra")
    args = parser.parse_args()

    engine = ContrastiveRetrievalEngine()

    if args.audio:
        res = engine.predict_from_audio(args.audio)
        print_results(res)
        return

    # Interactive Console
    print("=" * 80)
    print("CHẾ ĐỘ TEST TRUY XUẤT THUẬT NGỮ KHÔNG CẦN TỪ ĐIỂN (FAISS RETRIEVAL)")
    print("Dán đường dẫn một file .wav để mô hình tự động trích xuất âm thanh và tìm kiếm thuật ngữ.")
    print("Gõ 'exit' để thoát.")
    print("=" * 80)

    # Example files of Unseen Terms
    print("\nVí dụ các file audio thực tế của thuật ngữ CHƯA TỪNG TRAIN (Unseen Terms):")
    print("  * Load Testing / Stress Testing: Data/wav_16k/SE171761_Cau14_492d2466.wav")
    print("  * Code Coverage:               Data/wav_16k/P_01FD37_Cau15_a96cbd80.wav")
    print("  * Bug Report:                  Data/wav_16k/P_01FD37_Cau10_be1e0892.wav")
    print("-" * 80)

    while True:
        try:
            user_input = input("\n>>> Nhập đường dẫn file .wav: ").strip().strip('"').strip("'")
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "q"]:
                print("Tạm biệt!")
                break
            res = engine.predict_from_audio(user_input)
            print_results(res)
        except (KeyboardInterrupt, EOFError):
            print("\nTạm biệt!")
            break


if __name__ == "__main__":
    main()
