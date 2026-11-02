"""
LiemWhisper Interactive CLI Tester
==================================
Allows researchers and developers to quickly test LiemWhisper:
1. By typing a raw ASR transcript (e.g. text with phonetic corruptions)
2. By providing an audio file path (.wav, .m4a, .mp3)
3. In interactive console mode

Usage:
    python Liem/LiemWhisper/research/src/liemwhisper/demo_cli.py
    python Liem/LiemWhisper/research/src/liemwhisper/demo_cli.py --text "kỹ thuật baodari value analixit kết hợp với test cay"
    python Liem/LiemWhisper/research/src/liemwhisper/demo_cli.py --audio "path/to/recording.wav"
"""

import os
import sys
import time
import argparse
import site
import ctypes

if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

# Ensure NVIDIA CUDA DLLs are found on Windows
for sp in site.getsitepackages():
    for sub in ['cublas', 'cudnn', 'cuda_nvrtc']:
        p = os.path.join(sp, 'nvidia', sub, 'bin')
        if os.path.exists(p):
            if hasattr(os, 'add_dll_directory'):
                try:
                    os.add_dll_directory(p)
                except Exception:
                    pass
            os.environ['PATH'] = p + os.pathsep + os.environ.get('PATH', '')
    cublas_bin = os.path.join(sp, 'nvidia', 'cublas', 'bin')
    if os.path.exists(cublas_bin):
        for dll_name in ['cublasLt64_12.dll', 'cublas64_12.dll']:
            dll_path = os.path.join(cublas_bin, dll_name)
            if os.path.exists(dll_path):
                try:
                    ctypes.CDLL(dll_path)
                except Exception:
                    pass

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from baselines import TaxonomyManager
from candidate_ranking import ProposedSystemP, AcousticTeacherForcingScorer
from neural_corrector import NeuralErrorCorrector

# Find base Data dir
base_dir = current_dir
while base_dir and not os.path.exists(os.path.join(base_dir, "Data", "glossary_taxonomy_v1.json")):
    parent = os.path.dirname(base_dir)
    if parent == base_dir:
        break
    base_dir = parent

TAXONOMY_PATH = os.path.join(base_dir, "Data", "glossary_taxonomy_v1.json")


def load_pipeline(enable_gpu=True):
    print("Loading ISTQB Taxonomy...", end=" ", flush=True)
    tax = TaxonomyManager(TAXONOMY_PATH)
    print(f"Done ({len(tax.canonical_terms)} terms).")

    acoustic_scorer = None
    if enable_gpu:
        try:
            print("Loading Whisper Small Decoder on GPU...", end=" ", flush=True)
            acoustic_scorer = AcousticTeacherForcingScorer(model_size="small", device="cuda", compute_type="float16")
            acoustic_scorer.load_model()
            print("Done (CUDA enabled).")
        except Exception as e:
            print(f"Note: GPU loading fallback to CPU ({e})")
            try:
                acoustic_scorer = AcousticTeacherForcingScorer(model_size="small", device="cpu", compute_type="int8")
                acoustic_scorer.load_model()
            except Exception:
                acoustic_scorer = None

    system_p = ProposedSystemP(
        taxonomy=tax,
        acoustic_scorer=acoustic_scorer,
        generator_threshold=0.45,
        acceptance_threshold=0.50,
        enable_acoustic=(acoustic_scorer is not None),
        enable_context=True,
        enable_phonetic=True,
        enable_gate=True
    )
    return system_p, acoustic_scorer


def process_text_or_audio(system_p, acoustic_scorer, text_input=None, audio_path=None):
    raw_asr = text_input

    # If audio provided, transcribe with Whisper first
    if audio_path and os.path.exists(audio_path):
        print(f"\n[ASR Stage] Transcribing audio file: {audio_path}...")
        t0 = time.time()
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cuda", compute_type="float16")
        segments, _ = model.transcribe(audio_path, language="vi", beam_size=5)
        raw_asr = " ".join([seg.text for seg in segments]).strip()
        dt_asr = time.time() - t0
        print(f"  -> Raw Whisper Transcript ({dt_asr:.2f}s): \"{raw_asr}\"")

    if not raw_asr:
        print("Error: No text or audio provided!")
        return

    print(f"\n[LiemWhisper Stage] Processing transcript through Evidence Ranking Engine...")
    t0_p = time.time()
    res = system_p.process_utterance(raw_asr, audio_path=audio_path if audio_path and os.path.exists(audio_path) else None, return_timing=True)
    dt_p = (time.time() - t0_p) * 1000.0

    print("=" * 80)
    print("LIEMWHISPER CORRECTION RESULTS")
    print("=" * 80)
    print(f"1. Raw ASR Input    : {raw_asr}")
    print(f"2. Revised Output   : {res['revised_transcript']}")
    print(f"3. Processing Time  : {dt_p:.1f} ms")
    
    changes = res.get("accepted_changes", [])
    print(f"\n4. Accepted Term Corrections ({len(changes)} corrections):")
    if changes:
        for idx, c in enumerate(changes, 1):
            print(f"   [{idx}] \"{c.get('original_span')}\" -> \"{c.get('replacement')}\"")
            print(f"       Category      : {c.get('category')}")
            print(f"       Method        : {c.get('method')}")
            print(f"       Score         : {c.get('score', 0):.4f} (Decision Prob: {c.get('decision_score', c.get('score', 0)):.4f})")
            if "acoustic_delta" in c:
                print(f"       Acoustic Delta: {c.get('acoustic_delta', 0):.4f}")
    else:
        print("   (No corrections needed or no candidate passed decision gate)")

    preds = res.get("predicted_terms", [])
    print(f"\n5. Recognized Canonical Terms ({len(preds)} terms):")
    for t in preds:
        print(f"   - {t.term} [{t.category}]")
    print("=" * 80)


def process_neural(corrector, text_input=None, audio_path=None):
    raw_asr = text_input

    # If audio provided, transcribe with Whisper first
    if audio_path and os.path.exists(audio_path):
        print(f"\n[ASR Stage] Transcribing audio file: {audio_path}...")
        t0 = time.time()
        from faster_whisper import WhisperModel
        model = WhisperModel("small", device="cuda", compute_type="float16")
        segments, _ = model.transcribe(audio_path, language="vi", beam_size=5)
        raw_asr = " ".join([seg.text for seg in segments]).strip()
        dt_asr = time.time() - t0
        print(f"  -> Raw Whisper Transcript ({dt_asr:.2f}s): \"{raw_asr}\"")

    if not raw_asr:
        print("Error: No text or audio provided!")
        return

    print(f"\n[Neural Corrector Stage] Processing transcript through Pure Seq2Seq Transformer (Zero-Dictionary)...")
    t0 = time.time()
    res = corrector.correct(raw_asr)
    dt_ms = (time.time() - t0) * 1000.0

    print("=" * 80)
    print("OPEN-VOCABULARY NEURAL CORRECTION RESULTS (100% PURE MACHINE LEARNING)")
    print("=" * 80)
    print(f"1. Raw ASR Input     : {raw_asr}")
    print(f"2. Neural Corrected  : {res['corrected']}")
    print(f"3. Latency           : {res['latency_ms']:.1f} ms (Total: {dt_ms:.1f} ms)")
    print(f"4. Model Architecture: T5-Small + LoRA Adapter (294K params)")
    print(f"5. Dictionary Status : NONE (Zero taxonomy lookup, fully open-vocabulary)")
    print("=" * 80)


def main():
    parser = argparse.ArgumentParser(description="LiemWhisper Interactive CLI Tester")
    parser.add_argument("--text", type=str, default=None, help="Raw ASR text with code-switching / mispronunciations")
    parser.add_argument("--audio", type=str, default=None, help="Path to audio file (.wav, .m4a, .mp3)")
    parser.add_argument("--no-gpu", action="store_true", help="Run without GPU decoder")
    parser.add_argument("--engine", type=str, choices=["proposal", "neural"], default="proposal",
                        help="Correction engine: 'proposal' (Method P, taxonomy-grounded) or 'neural' (Option 2, open-vocabulary Seq2Seq)")
    args = parser.parse_args()

    if args.engine == "neural":
        print(f"Loading Open-Vocabulary Neural Corrector (LoRA)...", flush=True)
        corrector = NeuralErrorCorrector()
        if args.audio or args.text:
            process_neural(corrector, text_input=args.text, audio_path=args.audio)
            return

        print("\n" + "=" * 80)
        print("CHẾ ĐỘ TEST TƯƠNG TÁC: NEURAL SEQ2SEQ (ZERO-DICTIONARY)")
        print("Nhập một câu ASR bất kỳ để mô hình Deep Learning tự động sửa lỗi không cần từ điển.")
        print("Gõ 'exit' hoặc 'quit' để thoát.")
        print("=" * 80)

        while True:
            try:
                user_input = input("\n>>> Nhập câu ASR hoặc file audio: ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ['exit', 'quit', 'q']:
                    print("Tạm biệt!")
                    break
                if os.path.exists(user_input):
                    process_neural(corrector, audio_path=user_input)
                else:
                    process_neural(corrector, text_input=user_input)
            except (KeyboardInterrupt, EOFError):
                print("\nTạm biệt!")
                break
        return

    system_p, acoustic_scorer = load_pipeline(enable_gpu=not args.no_gpu)

    if args.audio or args.text:
        process_text_or_audio(system_p, acoustic_scorer, text_input=args.text, audio_path=args.audio)
        return

    # Interactive Console Mode
    print("\n" + "=" * 80)
    print("CHẾ ĐỘ TEST TƯƠNG TÁC (INTERACTIVE CONSOLE)")
    print("Nhập một câu ASR hoặc đường dẫn file âm thanh (.wav/.m4a) để test.")
    print("Gõ 'exit' hoặc 'quit' để thoát.")
    print("=" * 80)

    # Some example sentences for quick copy-paste
    examples = [
        "hôm nay tui chạy test cây với n hoạch tét tinh để tìm bớt rì pọt",
        "kỹ thuật baodari value analixit kết hợp với description table tempting",
        "bản bíu này cần chạy small testing và sennity testing ngay lập tức",
        "mô hình v model yêu cầu truy xuất traceability matrix"
    ]
    print("\nVí dụ các câu biến âm thực tế bạn có thể thử:")
    for ex in examples:
        print(f"  * {ex}")
    print("-" * 80)

    while True:
        try:
            user_input = input("\n>>> Nhập câu ASR hoặc file audio: ").strip()
            if not user_input:
                continue
            if user_input.lower() in ['exit', 'quit', 'q']:
                print("Tạm biệt!")
                break
            
            # Check if input is a file path
            if os.path.exists(user_input):
                process_text_or_audio(system_p, acoustic_scorer, audio_path=user_input)
            else:
                process_text_or_audio(system_p, acoustic_scorer, text_input=user_input)
        except (KeyboardInterrupt, EOFError):
            print("\nTạm biệt!")
            break


if __name__ == "__main__":
    main()
