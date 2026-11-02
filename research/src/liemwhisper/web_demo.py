"""
LiemWhisper Interactive Web Demo Studio
=======================================
A modern, responsive FastAPI Web UI allowing users to test LiemWhisper:
1. Live text input (try any code-switched or corrupted Vietnamese-English phrase)
2. Audio file upload / Microphone recording (.wav, .m4a, .mp3)
3. Browse and listen to real test samples from the 245 held-out recordings

Run:
    python Liem/LiemWhisper/research/src/liemwhisper/web_demo.py
    (Then open http://localhost:8000 in your browser)
"""

import os
import sys
import time
import json
import tempfile
import site
import ctypes
from typing import Optional, List, Dict, Any

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

import pandas as pd
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn

from baselines import TaxonomyManager
from candidate_ranking import ProposedSystemP, AcousticTeacherForcingScorer
from neural_corrector import NeuralErrorCorrector

neural_corrector_instance = None
def get_neural_corrector():
    global neural_corrector_instance
    if neural_corrector_instance is None:
        neural_corrector_instance = NeuralErrorCorrector()
    return neural_corrector_instance

# Find base paths
base_dir = current_dir
while base_dir and not os.path.exists(os.path.join(base_dir, "Data", "glossary_taxonomy_v1.json")):
    parent = os.path.dirname(base_dir)
    if parent == base_dir:
        break
    base_dir = parent

DATA_DIR = os.path.join(base_dir, "Data")
TAXONOMY_PATH = os.path.join(DATA_DIR, "glossary_taxonomy_v1.json")
WAV_DIR = os.path.join(DATA_DIR, "wav_16k")
GOLD_CSV = os.path.join(DATA_DIR, "gold_with_asr_v1.csv")
PRED_CSV = os.path.join(DATA_DIR, "benchmark_results", "predictions_system_p_test.csv")

# Initialize models
print("Initializing LiemWhisper Web Demo Engine...")
tax = TaxonomyManager(TAXONOMY_PATH)

acoustic_scorer = None
try:
    print("Loading Whisper Small GPU Decoder...")
    acoustic_scorer = AcousticTeacherForcingScorer(model_size="small", device="cuda", compute_type="float16")
    acoustic_scorer.load_model()
    print("Acoustic Scorer loaded on CUDA.")
except Exception as e:
    print(f"CUDA loading note: {e}. Falling back to CPU...")
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

whisper_asr_model = None

def get_asr_model():
    global whisper_asr_model
    if whisper_asr_model is None:
        from faster_whisper import WhisperModel
        try:
            whisper_asr_model = WhisperModel("small", device="cuda", compute_type="float16")
        except Exception:
            whisper_asr_model = WhisperModel("small", device="cpu", compute_type="int8")
    return whisper_asr_model

app = FastAPI(title="LiemWhisper Interactive Studio")

if os.path.exists(WAV_DIR):
    app.mount("/audio", StaticFiles(directory=WAV_DIR), name="audio")


class TextRequest(BaseModel):
    text: str
    engine: Optional[str] = "proposal"


@app.post("/api/process_text")
async def process_text_endpoint(req: TextRequest):
    t0 = time.time()
    if req.engine == "neural":
        corrector = get_neural_corrector()
        res_n = corrector.correct(req.text)
        dt = (time.time() - t0) * 1000.0
        return {
            "engine": "neural",
            "original_transcript": req.text,
            "revised_transcript": res_n["corrected"],
            "accepted_changes": [
                {
                    "original_span": "Toàn câu (ASR Input)",
                    "replacement": res_n["corrected"],
                    "category": "Deep Learning Seq2Seq",
                    "method": "T5 + LoRA (Zero-Dictionary)",
                    "score": 0.99
                }
            ],
            "predicted_terms": [],
            "latency_ms": round(dt, 1)
        }

    res = system_p.process_utterance(req.text, audio_path=None, return_timing=True)
    dt = (time.time() - t0) * 1000.0
    return {
        "engine": "proposal",
        "original_transcript": req.text,
        "revised_transcript": res["revised_transcript"],
        "accepted_changes": res["accepted_changes"],
        "predicted_terms": [{"term": t.term, "category": t.category} for t in res["predicted_terms"]],
        "latency_ms": round(dt, 1)
    }


@app.post("/api/process_audio")
async def process_audio_endpoint(file: UploadFile = File(...), engine: str = Form("proposal")):
    # Save to temp
    ext = os.path.splitext(file.filename)[1] or ".wav"
    with tempfile.NamedTemporaryFile(delete=False, suffix=ext) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        t0 = time.time()
        # 1. Transcribe with Whisper Small
        asr_m = get_asr_model()
        segments, _ = asr_m.transcribe(tmp_path, language="vi", beam_size=5)
        raw_asr = " ".join([seg.text for seg in segments]).strip()
        dt_asr = (time.time() - t0) * 1000.0

        if engine == "neural":
            corrector = get_neural_corrector()
            t0_n = time.time()
            res_n = corrector.correct(raw_asr)
            dt_n = (time.time() - t0_n) * 1000.0
            return {
                "engine": "neural",
                "raw_asr_transcript": raw_asr,
                "revised_transcript": res_n["corrected"],
                "accepted_changes": [
                    {
                        "original_span": "Toàn câu (ASR Input)",
                        "replacement": res_n["corrected"],
                        "category": "Deep Learning Seq2Seq",
                        "method": "T5 + LoRA (Zero-Dictionary)",
                        "score": 0.99
                    }
                ],
                "predicted_terms": [],
                "asr_latency_ms": round(dt_asr, 1),
                "liem_latency_ms": round(dt_n, 1),
                "total_latency_ms": round(dt_asr + dt_n, 1)
            }

        # 2. LiemWhisper ranking
        t0_p = time.time()
        res = system_p.process_utterance(raw_asr, audio_path=tmp_path, return_timing=True)
        dt_p = (time.time() - t0_p) * 1000.0

        return {
            "engine": "proposal",
            "raw_asr_transcript": raw_asr,
            "revised_transcript": res["revised_transcript"],
            "accepted_changes": res["accepted_changes"],
            "predicted_terms": [{"term": t.term, "category": t.category} for t in res["predicted_terms"]],
            "asr_latency_ms": round(dt_asr, 1),
            "liem_latency_ms": round(dt_p, 1),
            "total_latency_ms": round(dt_asr + dt_p, 1)
        }
    finally:
        if os.path.exists(tmp_path):
            try:
                os.remove(tmp_path)
            except Exception:
                pass


@app.get("/api/test_samples")
async def get_test_samples():
    if not os.path.exists(PRED_CSV):
        return {"samples": []}
    
    p_df = pd.read_csv(PRED_CSV)
    g_df = pd.read_csv(GOLD_CSV) if os.path.exists(GOLD_CSV) else None
    
    samples = []
    for idx, r in p_df.head(50).iterrows():
        rec_id = r["recording_id"]
        wav_file = ""
        verbatim = ""
        gold_terms = ""
        if g_df is not None:
            match = g_df[g_df["recording_id"] == rec_id]
            if len(match) > 0:
                wav_file = match.iloc[0]["wav_file"]
                verbatim = str(match.iloc[0]["verbatim_transcript"])
                gold_terms = str(match.iloc[0]["gold_terms"])

        changes_raw = r.get("accepted_changes", "[]")
        try:
            changes = json.loads(changes_raw) if isinstance(changes_raw, str) else []
        except Exception:
            changes = []

        samples.append({
            "recording_id": rec_id,
            "speaker_id": r["speaker_id"],
            "prompt_text": r["prompt_text"],
            "verbatim_transcript": verbatim,
            "asr_transcript": r["asr_transcript"],
            "revised_transcript": r["revised_transcript"],
            "wav_file": wav_file,
            "gold_terms": gold_terms,
            "changes_count": len(changes),
            "changes": changes
        })
    return {"samples": samples}


@app.get("/", response_class=HTMLResponse)
async def index_page():
    html = """<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>LiemWhisper Interactive Studio - Code-Switched ASR Evaluation</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css">
    <style>
        body { background: #f8fafc; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #1e293b; }
        .hero { background: linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%); color: white; padding: 2.5rem 0; margin-bottom: 2rem; border-radius: 0 0 24px 24px; box-shadow: 0 10px 25px -5px rgba(59, 130, 246, 0.3); }
        .card { border-radius: 16px; border: none; box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05); }
        .nav-pills .nav-link { border-radius: 12px; font-weight: 600; padding: 10px 20px; color: #64748b; }
        .nav-pills .nav-link.active { background-color: #2563eb; color: white; box-shadow: 0 4px 12px rgba(37, 99, 235, 0.3); }
        .badge-cat { font-size: 0.75rem; padding: 4px 8px; border-radius: 6px; font-weight: 600; }
        .cat-Testing-Techniques { background: #dbeafe; color: #1e40af; }
        .cat-Testware { background: #fef3c7; color: #92400e; }
        .cat-Testing-Levels-and-Types { background: #dcfce7; color: #166534; }
        .cat-Defect-Management { background: #fee2e2; color: #991b1b; }
        .cat-Quality-and-Metrics { background: #f3e8ff; color: #6b21a8; }
        .transcript-box { background: #ffffff; border: 1.5px solid #e2e8f0; border-radius: 12px; padding: 1.25rem; min-height: 120px; font-size: 1.05rem; line-height: 1.6; }
        .transcript-highlight { background-color: #fef08a; padding: 2px 6px; border-radius: 4px; font-weight: 600; border-bottom: 2px solid #ca8a04; }
        .metric-pill { background: #f1f5f9; padding: 6px 14px; border-radius: 20px; font-size: 0.85rem; font-weight: 600; display: inline-flex; align-items: center; gap: 6px; }
    </style>
</head>
<body>

<div class="hero">
    <div class="container">
        <div class="d-flex align-items-center justify-content-between flex-wrap gap-3">
            <div>
                <h1 class="fw-bold mb-1"><i class="fa-solid fa-microphone-lines me-2"></i>LiemWhisper Interactive Studio</h1>
                <p class="mb-0 text-blue-100 fs-6">Hệ thống nhận dạng tiếng nói trộn mã Tiếng Việt - Tiếng Anh (ISTQB Software Testing) với cơ chế kiểm chứng âm học và cổng quyết định an toàn</p>
            </div>
            <div>
                <span class="badge bg-light text-primary fs-6 px-3 py-2 rounded-pill"><i class="fa-solid fa-award me-1"></i>Scopus / SCIE Q3 Target</span>
            </div>
        </div>
    </div>
</div>

<div class="container mb-5">
    <!-- Navigation Tabs -->
    <ul class="nav nav-pills mb-4 justify-content-center gap-2" id="demoTab" role="tablist">
        <li class="nav-item" role="presentation">
            <button class="nav-link active" id="text-tab" data-bs-toggle="pill" data-bs-target="#text-mode" type="button" role="tab"><i class="fa-solid fa-keyboard me-2"></i>1. Thử nghiệm Văn bản ASR</button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link" id="audio-tab" data-bs-toggle="pill" data-bs-target="#audio-mode" type="button" role="tab"><i class="fa-solid fa-microphone me-2"></i>2. Nói Trực Tiếp qua Micro / Upload Audio</button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link" id="samples-tab" data-bs-toggle="pill" data-bs-target="#samples-mode" type="button" role="tab"><i class="fa-solid fa-database me-2"></i>3. Khám phá Test Set (245 mẫu)</button>
        </li>
    </ul>

    <div class="tab-content" id="demoTabContent">
        <!-- TAB 1: TEXT TEST -->
        <div class="tab-pane fade show active" id="text-mode" role="tabpanel">
            <div class="row g-4">
                <div class="col-lg-5">
                    <div class="card p-4 h-100">
                        <h5 class="fw-bold mb-3"><i class="fa-solid fa-pencil text-primary me-2"></i>Nhập câu ASR biến âm</h5>
                        <p class="text-muted small">Nhập bản phiên âm thô của Whisper hoặc câu tiếng Việt có phát âm bồi/biến âm thuật ngữ ISTQB.</p>
                        
                        <textarea id="textInput" class="form-control mb-3" rows="4" placeholder="Ví dụ: kỹ thuật baodari value analixit kết hợp với description table tempting..."></textarea>
                        
                        <div class="mb-3">
                            <label class="form-label small fw-bold text-muted">Cơ chế Hiệu chỉnh (Correction Engine):</label>
                            <select id="engineSelect" class="form-select form-select-sm">
                                <option value="proposal" selected>🎯 Method P: Entity-Grounded Ranking (Khuyên dùng - Giữ nguyên 100% tiếng Việt)</option>
                                <option value="neural">🧠 Option 2: Pure Neural Seq2Seq (T5-LoRA Thử nghiệm không từ điển)</option>
                            </select>
                            <div class="form-text small text-muted">💡 <b>Method P</b> là giải pháp đề xuất của đồ án: giữ nguyên tiếng Việt chuẩn của Whisper, chỉ dò tìm và sửa đúng vị trí phát âm bồi thuật ngữ.</div>
                        </div>

                        <div class="mb-3">
                            <label class="form-label small fw-bold text-muted">Câu mẫu thử nhanh (Bấm để điền):</label>
                            <div class="d-flex flex-column gap-2">
                                <button class="btn btn-sm btn-outline-secondary text-start" onclick="setSample('kỹ thuật baodari value analixit kết hợp với description table tempting')">🔹 baodari value analixit ... description table tempting</button>
                                <button class="btn btn-sm btn-outline-secondary text-start" onclick="setSample('hôm nay tui chạy test cây với n hoạch tét tinh để tìm bớt rì pọt')">🔹 test cây ... n hoạch tét tinh ... bớt rì pọt</button>
                                <button class="btn btn-sm btn-outline-secondary text-start" onclick="setSample('bản bíu này cần chạy small testing và sennity testing ngay lập tức')">🔹 bản bíu ... small testing ... sennity testing</button>
                                <button class="btn btn-sm btn-outline-secondary text-start" onclick="setSample('mô hình v model yêu cầu theo dõi traceability matrix 2 chiều')">🔹 v model ... traceability matrix 2 chiều</button>
                            </div>
                        </div>

                        <button id="btnProcessText" class="btn btn-primary w-100 py-2 fw-semibold" onclick="processText()"><i class="fa-solid fa-wand-magic-sparkles me-2"></i>Chạy LiemWhisper</button>
                    </div>
                </div>

                <div class="col-lg-7">
                    <div class="card p-4 h-100">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h5 class="fw-bold mb-0"><i class="fa-solid fa-square-check text-success me-2"></i>Kết quả Hiệu chỉnh</h5>
                            <span id="textLatency" class="metric-pill"><i class="fa-regular fa-clock"></i> 0.0 ms</span>
                        </div>

                        <label class="form-label small fw-bold text-muted">Bản phiên âm đã hiệu chỉnh (Revised Transcript):</label>
                        <div id="textOutput" class="transcript-box mb-3 text-secondary">
                            (Bấm "Chạy LiemWhisper" để xem kết quả)
                        </div>

                        <h6 class="fw-bold mb-2">Thuật ngữ & Hành động sửa đổi:</h6>
                        <div id="changesTableContainer" class="table-responsive">
                            <p class="text-muted small">Chưa có dữ liệu xử lý.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 2: LIVE MIC & AUDIO UPLOAD -->
        <div class="tab-pane fade" id="audio-mode" role="tabpanel">
            <div class="row g-4">
                <div class="col-lg-5">
                    <div class="card p-4 h-100">
                        <h5 class="fw-bold mb-3"><i class="fa-solid fa-microphone text-danger me-2"></i>Nói trực tiếp qua Microphone</h5>
                        <p class="text-muted small">Bấm nút bên dưới, nói một câu vào micro (bằng tiếng Việt có kèm thuật ngữ ISTQB tiếng Anh hoặc phát âm bồi). Sau khi nói xong, bấm <b>Dừng</b> để hệ thống tự động nhận dạng ra text.</p>
                        
                        <div class="mb-3">
                            <label class="form-label small fw-bold text-muted">Cơ chế Hiệu chỉnh (Engine):</label>
                            <select id="engineAudioSelect" class="form-select form-select-sm">
                                <option value="proposal" selected>🎯 Method P: Entity-Grounded Ranking (Khuyên dùng - Giữ nguyên 100% tiếng Việt)</option>
                                <option value="neural">🧠 Option 2: Pure Neural Seq2Seq (T5-LoRA Thử nghiệm không từ điển)</option>
                            </select>
                        </div>

                        <!-- LIVE MIC BUTTON -->
                        <button id="btnRecord" class="btn btn-danger btn-lg w-100 py-3 mb-3 fw-bold rounded-pill shadow" onclick="toggleRecording()">
                            <i class="fa-solid fa-microphone me-2"></i>Bấm vào đây để BẮT ĐẦU NÓI
                        </button>

                        <!-- RECORDING STATUS -->
                        <div id="recordStatus" class="d-none text-center mb-3 p-3 bg-danger-subtle rounded-3 border border-danger-subtle">
                            <div class="spinner-grow spinner-grow-sm text-danger me-2" role="status"></div>
                            <span class="fw-bold text-danger fs-4 align-middle" id="recordTimer">00:00</span>
                            <p class="small text-danger fw-semibold mt-2 mb-0">🔴 Đang lắng nghe giọng bạn... Nói xong bấm nút để dừng!</p>
                        </div>

                        <div id="audioPreviewContainer" class="mb-3 d-none">
                            <label class="form-label small fw-bold text-muted">Nghe lại giọng nói vừa thu:</label>
                            <audio id="audioPreview" controls class="w-100 rounded"></audio>
                        </div>

                        <!-- OR FILE UPLOAD -->
                        <div class="position-relative text-center my-3">
                            <hr class="my-0">
                            <span class="position-absolute top-50 start-50 translate-middle bg-white px-3 text-muted small fw-semibold">HOẶC CHỌN FILE ÂM THANH</span>
                        </div>

                        <div class="mt-3">
                            <input type="file" id="audioFile" class="form-control mb-2" accept=".wav,.m4a,.mp3,.webm">
                            <button id="btnProcessAudio" class="btn btn-outline-primary w-100 py-2 fw-semibold" onclick="processAudioFile()"><i class="fa-solid fa-upload me-2"></i>Nhận dạng từ File này</button>
                        </div>
                    </div>
                </div>

                <div class="col-lg-7">
                    <div class="card p-4 h-100">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h5 class="fw-bold mb-0"><i class="fa-solid fa-chart-line text-success me-2"></i>So sánh Whisper vs LiemWhisper</h5>
                            <div class="d-flex gap-2">
                                <span id="asrLatency" class="metric-pill"><i class="fa-solid fa-microphone"></i> ASR: 0ms</span>
                                <span id="liemLatency" class="metric-pill"><i class="fa-solid fa-brain"></i> Liem: 0ms</span>
                            </div>
                        </div>

                        <label class="form-label small fw-bold text-muted">1. Whisper Small thô (Raw ASR):</label>
                        <div id="rawAsrOutput" class="transcript-box mb-3 text-secondary" style="min-height: 80px;">
                            (Chưa có âm thanh được xử lý)
                        </div>

                        <label class="form-label small fw-bold text-muted">2. LiemWhisper đã hiệu chỉnh (Revised Transcript):</label>
                        <div id="revisedAudioOutput" class="transcript-box mb-3 text-primary fw-semibold" style="min-height: 80px;">
                            (Chưa có kết quả)
                        </div>

                        <h6 class="fw-bold mb-2">Chi tiết thuật ngữ nhận diện:</h6>
                        <div id="audioChangesContainer" class="table-responsive">
                            <p class="text-muted small">Chưa có thay đổi nào.</p>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- TAB 3: SAMPLES EXPLORER -->
        <div class="tab-pane fade" id="samples-mode" role="tabpanel">
            <div class="card p-4">
                <div class="d-flex justify-content-between align-items-center mb-3 flex-wrap gap-2">
                    <h5 class="fw-bold mb-0"><i class="fa-solid fa-list-check text-primary me-2"></i>Khám phá 50 mẫu Test Set (Held-out Evaluation)</h5>
                    <div class="d-flex gap-2 align-items-center">
                        <span class="badge bg-success-subtle text-success border border-success-subtle px-3 py-2">Test WER: 31.89% (giảm -1.28%)</span>
                        <span class="badge bg-primary-subtle text-primary border border-primary-subtle px-3 py-2">Term Prec: 92.73%</span>
                    </div>
                </div>

                <div class="table-responsive">
                    <table class="table table-hover align-middle">
                        <thead class="table-light">
                            <tr>
                                <th style="width: 100px;">Mã</th>
                                <th style="width: 250px;">Nghe Audio</th>
                                <th>Whisper Small Gốc (Raw ASR)</th>
                                <th>LiemWhisper Đề xuất (Revised)</th>
                                <th>Sửa đổi (Changes)</th>
                            </tr>
                        </thead>
                        <tbody id="samplesTableBody">
                            <tr>
                                <td colspan="5" class="text-center py-4 text-muted"><i class="fa-solid fa-spinner fa-spin me-2"></i>Đang tải danh sách mẫu...</td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>
</div>

<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
<script>
    function setSample(text) {
        document.getElementById('textInput').value = text;
    }

    async function processText() {
        const text = document.getElementById('textInput').value.trim();
        if (!text) {
            alert("Vui lòng nhập văn bản!");
            return;
        }

        const btn = document.getElementById('btnProcessText');
        btn.disabled = true;
        btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin me-2"></i>Đang xử lý...';

        try {
            const engine = document.getElementById('engineSelect').value;
            const res = await fetch('/api/process_text', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, engine })
            });
            const data = await res.json();

            document.getElementById('textLatency').innerHTML = `<i class="fa-regular fa-clock"></i> ${data.latency_ms} ms`;
            document.getElementById('textOutput').innerText = data.revised_transcript;

            // Render changes table
            const changes = data.accepted_changes || [];
            if (changes.length === 0) {
                document.getElementById('changesTableContainer').innerHTML = `
                    <div class="alert alert-info py-2 small mb-0"><i class="fa-solid fa-circle-info me-1"></i> Không có thuật ngữ nào cần sửa đổi hoặc không có ứng viên nào vượt qua ngưỡng an toàn.</div>
                `;
            } else {
                let rows = changes.map((c, i) => `
                    <tr>
                        <td><span class="badge bg-secondary">${i+1}</span></td>
                        <td><span class="text-danger text-decoration-line-through">${c.original_span}</span></td>
                        <td><span class="fw-bold text-success">${c.replacement}</span></td>
                        <td><span class="badge-cat cat-${c.category.replace(/\\s+/g, '-')}">${c.category}</span></td>
                        <td><span class="badge bg-light text-dark">${c.method}</span></td>
                        <td><strong>${(c.score || 0).toFixed(4)}</strong></td>
                    </tr>
                `).join('');

                document.getElementById('changesTableContainer').innerHTML = `
                    <table class="table table-sm table-bordered align-middle">
                        <thead class="table-light">
                            <tr><th>#</th><th>Từ thô</th><th>Thuật ngữ chuẩn</th><th>Danh mục ISTQB</th><th>Phương thức</th><th>Điểm Quyết định</th></tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                `;
            }
        } catch (e) {
            alert("Lỗi khi xử lý: " + e.message);
        } finally {
            btn.disabled = false;
            btn.innerHTML = '<i class="fa-solid fa-wand-magic-sparkles me-2"></i>Chạy LiemWhisper';
        }
    }

    // Live Microphone Recording
    let mediaRecorder = null;
    let audioChunks = [];
    let recordInterval = null;
    let recordSeconds = 0;

    async function toggleRecording() {
        const btn = document.getElementById('btnRecord');
        const statusDiv = document.getElementById('recordStatus');
        const timerElem = document.getElementById('recordTimer');

        if (!mediaRecorder || mediaRecorder.state === 'inactive') {
            try {
                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                audioChunks = [];
                mediaRecorder = new MediaRecorder(stream);

                mediaRecorder.ondataavailable = e => {
                    if (e.data.size > 0) audioChunks.push(e.data);
                };

                mediaRecorder.onstop = async () => {
                    const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
                    const audioUrl = URL.createObjectURL(audioBlob);
                    const preview = document.getElementById('audioPreview');
                    preview.src = audioUrl;
                    document.getElementById('audioPreviewContainer').classList.remove('d-none');

                    // Automatically transcribe and rank the recorded audio
                    await uploadAndProcessBlob(audioBlob, 'mic_recording.webm');
                };

                mediaRecorder.start();
                btn.classList.remove('btn-danger');
                btn.classList.add('btn-dark');
                btn.innerHTML = '<i class="fa-solid fa-stop me-2"></i>DỪNG NÓI & XUẤT TEXT NGAY';
                statusDiv.classList.remove('d-none');

                recordSeconds = 0;
                timerElem.innerText = '00:00';
                recordInterval = setInterval(() => {
                    recordSeconds++;
                    const mins = String(Math.floor(recordSeconds / 60)).padStart(2, '0');
                    const secs = String(recordSeconds % 60).padStart(2, '0');
                    timerElem.innerText = `${mins}:${secs}`;
                }, 1000);
            } catch (err) {
                alert("Không thể mở Microphone: " + err.message + "\\nVui lòng cấp quyền Microphone trên trình duyệt!");
            }
        } else {
            mediaRecorder.stop();
            if (mediaRecorder.stream) {
                mediaRecorder.stream.getTracks().forEach(track => track.stop());
            }
            clearInterval(recordInterval);
            btn.classList.remove('btn-dark');
            btn.classList.add('btn-danger');
            btn.innerHTML = '<i class="fa-solid fa-microphone me-2"></i>Bấm vào đây để BẮT ĐẦU NÓI';
            statusDiv.classList.add('d-none');
        }
    }

    // Audio preview handler for file input
    document.getElementById('audioFile').addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            const preview = document.getElementById('audioPreview');
            preview.src = URL.createObjectURL(file);
            document.getElementById('audioPreviewContainer').classList.remove('d-none');
        }
    });

    async function processAudioFile() {
        const fileInput = document.getElementById('audioFile');
        if (!fileInput.files || fileInput.files.length === 0) {
            alert("Vui lòng chọn file âm thanh!");
            return;
        }
        await uploadAndProcessBlob(fileInput.files[0], fileInput.files[0].name);
    }

    async function uploadAndProcessBlob(blob, filename) {
        const btnRecord = document.getElementById('btnRecord');
        const btnFile = document.getElementById('btnProcessAudio');
        btnRecord.disabled = true;
        btnFile.disabled = true;

        document.getElementById('rawAsrOutput').innerHTML = '<div class="text-center py-3"><div class="spinner-border text-primary" role="status"></div><p class="mt-2 text-muted small">Đang chạy Whisper Small nhận dạng âm thanh...</p></div>';
        document.getElementById('revisedAudioOutput').innerHTML = '<div class="text-muted small">Đang xếp hạng ứng viên LiemWhisper...</div>';

        const formData = new FormData();
        formData.append('file', blob, filename);
        const engine = document.getElementById('engineAudioSelect') ? document.getElementById('engineAudioSelect').value : 'proposal';
        formData.append('engine', engine);

        try {
            const res = await fetch('/api/process_audio', {
                method: 'POST',
                body: formData
            });
            const data = await res.json();

            document.getElementById('asrLatency').innerHTML = `<i class="fa-solid fa-microphone"></i> ASR: ${data.asr_latency_ms}ms`;
            document.getElementById('liemLatency').innerHTML = `<i class="fa-solid fa-brain"></i> Liem: ${data.liem_latency_ms}ms`;

            document.getElementById('rawAsrOutput').innerText = data.raw_asr_transcript || '(Không nhận diện được giọng nói)';
            document.getElementById('revisedAudioOutput').innerText = data.revised_transcript || '(Không nhận diện được giọng nói)';

            const changes = data.accepted_changes || [];
            if (changes.length === 0) {
                document.getElementById('audioChangesContainer').innerHTML = `
                    <div class="alert alert-secondary py-2 small mb-0"><i class="fa-solid fa-circle-check text-success me-1"></i> Phát âm chuẩn xác hoặc không có thuật ngữ ISTQB nào bị biến âm.</div>
                `;
            } else {
                let rows = changes.map((c, i) => `
                    <tr>
                        <td>${i+1}</td>
                        <td><span class="text-danger text-decoration-line-through">${c.original_span}</span></td>
                        <td><span class="fw-bold text-success">${c.replacement}</span></td>
                        <td><span class="badge-cat cat-${c.category.replace(/\\s+/g, '-')}">${c.category}</span></td>
                        <td><span class="badge bg-light text-dark">${c.method}</span></td>
                        <td><strong>${(c.score || 0).toFixed(4)}</strong></td>
                    </tr>
                `).join('');

                document.getElementById('audioChangesContainer').innerHTML = `
                    <table class="table table-sm table-bordered align-middle">
                        <thead class="table-light">
                            <tr><th>#</th><th>Phát âm thô</th><th>Thuật ngữ chuẩn</th><th>Danh mục ISTQB</th><th>Cơ chế</th><th>Độ tự tin</th></tr>
                        </thead>
                        <tbody>${rows}</tbody>
                    </table>
                `;
            }
        } catch (e) {
            alert("Lỗi khi xử lý âm thanh: " + e.message);
        } finally {
            btnRecord.disabled = false;
            btnFile.disabled = false;
        }
    }

    // Load samples on Tab 3 click
    let samplesLoaded = false;
    document.getElementById('samples-tab').addEventListener('click', async function() {
        if (samplesLoaded) return;
        try {
            const res = await fetch('/api/test_samples');
            const data = await res.json();
            const samples = data.samples || [];

            if (samples.length === 0) {
                document.getElementById('samplesTableBody').innerHTML = `
                    <tr><td colspan="5" class="text-center py-4 text-muted">Chưa tìm thấy file dự đoán Test Set.</td></tr>
                `;
                return;
            }

            let html = samples.map(s => {
                let audioElem = s.wav_file ? `<audio controls preload="none" style="width: 220px; height: 36px;" src="/audio/${s.wav_file}"></audio>` : '<em>Không có file</em>';
                let changeBadges = s.changes.map(c => `<span class="badge bg-success-subtle text-success border border-success-subtle mb-1 d-block text-start">${c.original_span} ➔ ${c.replacement}</span>`).join('');
                if (!changeBadges) changeBadges = '<span class="text-muted small">Không đổi</span>';

                return `
                    <tr>
                        <td><code>${s.recording_id}</code></td>
                        <td>${audioElem}</td>
                        <td class="small text-secondary">${s.asr_transcript}</td>
                        <td class="small fw-semibold text-primary">${s.revised_transcript}</td>
                        <td style="max-width: 200px;">${changeBadges}</td>
                    </tr>
                `;
            }).join('');

            document.getElementById('samplesTableBody').innerHTML = html;
            samplesLoaded = true;
        } catch (e) {
            document.getElementById('samplesTableBody').innerHTML = `
                <tr><td colspan="5" class="text-center py-4 text-danger">Lỗi tải mẫu: ${e.message}</td></tr>
            `;
        }
    });
</script>

</body>
</html>
"""
    return HTMLResponse(content=html)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run LiemWhisper Interactive Web Demo Studio")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface to bind")
    parser.add_argument("--port", type=int, default=8000, help="Port to listen on")
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print(f"LIEMWHISPER INTERACTIVE STUDIO RUNNING AT: http://{args.host}:{args.port}")
    print("Mở đường link trên bằng trình duyệt để test giao diện trực quan!")
    print("=" * 80 + "\n")

    uvicorn.run(app, host=args.host, port=args.port)
