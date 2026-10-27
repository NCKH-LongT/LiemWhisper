"""
LiemWhisper Web Annotation Studio
=================================
A modern, ergonomic FastAPI + HTML5 Web Application designed specifically for
Annotator A and Annotator B to rapidly listen to audio recordings, verify verbatim
transcripts, identify ISTQB technical terms, and produce gold standard datasets.

Usage:
    python research/src/liemwhisper/annotation_app.py
    python research/src/liemwhisper/annotation_app.py --port 8000 --host 0.0.0.0
"""

import os
import sys
import json
import time
import argparse
from typing import List, Dict, Any, Optional
import pandas as pd
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

current_dir = os.path.dirname(os.path.abspath(__file__))
if current_dir not in sys.path:
    sys.path.insert(0, current_dir)

from baselines import TaxonomyManager, TextNormalizer

# Discover base paths
base_dir = current_dir
while base_dir and not os.path.exists(os.path.join(base_dir, "Data", "glossary_taxonomy_v1.json")):
    parent = os.path.dirname(base_dir)
    if parent == base_dir:
        break
    base_dir = parent

DATA_DIR = os.path.join(base_dir, "Data")
TAXONOMY_PATH = os.path.join(DATA_DIR, "glossary_taxonomy_v1.json")
WAV_DIR = os.path.join(DATA_DIR, "wav_16k")
ASSIGN_DIR = os.path.join(DATA_DIR, "annotator_assignments")
FILE_A = os.path.join(ASSIGN_DIR, "annotation_batch_annotator_A.csv")
FILE_B = os.path.join(ASSIGN_DIR, "annotation_batch_annotator_B.csv")

# Initialize Taxonomy
taxonomy = TaxonomyManager(TAXONOMY_PATH)

app = FastAPI(title="LiemWhisper Web Annotation Studio", version="1.0.0")

# Mount audio directory
if os.path.exists(WAV_DIR):
    app.mount("/audio", StaticFiles(directory=WAV_DIR), name="audio")


class SaveAnnotationRequest(BaseModel):
    recording_id: str
    annotator_id: str
    verbatim_transcript: str
    annotator_identified_terms: List[Dict[str, Any]]
    annotator_status: str
    audio_quality_flag: str
    annotator_comments: Optional[str] = ""


def get_annotator_file(annotator: str) -> str:
    ann = annotator.upper().strip()
    if ann in ["A", "ANNOTATOR_A"]:
        return FILE_A
    elif ann in ["B", "ANNOTATOR_B"]:
        return FILE_B
    raise HTTPException(status_code=400, detail=f"Unknown annotator '{annotator}'. Must be 'A' or 'B'.")


def load_annotator_df(annotator: str) -> pd.DataFrame:
    file_path = get_annotator_file(annotator)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail=f"Batch file not found: {file_path}")
    df = pd.read_csv(file_path)
    return df


def save_annotator_df(annotator: str, df: pd.DataFrame):
    file_path = get_annotator_file(annotator)
    # Write atomically
    tmp_path = file_path + ".tmp"
    df.to_csv(tmp_path, index=False, encoding="utf-8-sig")
    os.replace(tmp_path, file_path)


# ==============================================================================
# API ENDPOINTS
# ==============================================================================

@app.get("/api/taxonomy")
def get_taxonomy():
    """Returns canonical ISTQB terms and their taxonomy metadata."""
    terms_list = []
    for term in taxonomy.canonical_terms:
        terms_list.append({
            "term": term,
            "category": taxonomy.get_category(term)
        })
    return {
        "categories": taxonomy.categories,
        "terms": terms_list
    }


@app.get("/api/stats")
def get_stats(annotator: str = "A"):
    """Returns progress statistics for the selected annotator."""
    df = load_annotator_df(annotator)
    total = len(df)
    completed = (df["annotator_status"] == "completed").sum()
    pending = total - completed
    flagged = (df["audio_quality_flag"].fillna("normal") != "normal").sum()
    double_cand = df["is_double_annotation_candidate"].fillna(False).astype(bool).sum()

    return {
        "annotator": annotator.upper(),
        "total": int(total),
        "completed": int(completed),
        "pending": int(pending),
        "flagged": int(flagged),
        "double_annotation_candidates": int(double_cand),
        "progress_pct": round((completed / total) * 100.0, 1) if total > 0 else 0.0
    }


@app.get("/api/records")
def get_records(annotator: str = "A", filter_status: str = "all"):
    """Returns list of record summaries matching the filter."""
    df = load_annotator_df(annotator)
    if filter_status == "pending":
        df = df[df["annotator_status"] != "completed"]
    elif filter_status == "completed":
        df = df[df["annotator_status"] == "completed"]
    elif filter_status == "double":
        df = df[df["is_double_annotation_candidate"].fillna(False).astype(bool)]
    elif filter_status == "flagged":
        df = df[df["audio_quality_flag"].fillna("normal") != "normal"]

    records = []
    for idx, row in df.iterrows():
        records.append({
            "index": int(idx),
            "recording_id": str(row["recording_id"]),
            "speaker_name": str(row.get("speaker_name", "")),
            "prompt_id": str(row.get("prompt_id", "")),
            "target_terms_hint": str(row.get("target_terms_hint", "")),
            "annotator_status": str(row.get("annotator_status", "pending")),
            "audio_quality_flag": str(row.get("audio_quality_flag", "normal")),
            "duration_seconds": float(row.get("duration_seconds", 0.0))
        })
    return {"records": records, "count": len(records)}


@app.get("/api/record/{annotator}/{recording_id}")
def get_record_detail(annotator: str, recording_id: str):
    """Returns full details of an individual recording."""
    df = load_annotator_df(annotator)
    match = df[df["recording_id"] == recording_id]
    if match.empty:
        raise HTTPException(status_code=404, detail=f"Recording {recording_id} not found in Annotator {annotator} batch.")

    row = match.iloc[0]
    wav_file = str(row["wav_file"])
    wav_exists = os.path.exists(os.path.join(WAV_DIR, wav_file))

    # Parse identified terms
    raw_terms = row.get("annotator_identified_terms", "[]")
    parsed_terms = []
    if pd.notna(raw_terms) and str(raw_terms).strip():
        s = str(raw_terms).strip()
        if s.startswith("[") and s.endswith("]"):
            try:
                items = json.loads(s)
                for it in items:
                    if isinstance(it, dict):
                        parsed_terms.append(it)
                    elif isinstance(it, str):
                        parsed_terms.append({"term": it, "category": taxonomy.get_category(it)})
            except Exception:
                pass
        else:
            for p in s.split(";"):
                p_clean = p.strip()
                if p_clean:
                    parsed_terms.append({"term": p_clean, "category": taxonomy.get_category(p_clean)})

    return {
        "recording_id": str(row["recording_id"]),
        "annotator_id": annotator.upper(),
        "speaker_id": str(row.get("speaker_id", "")),
        "speaker_name": str(row.get("speaker_name", "")),
        "wav_file": wav_file,
        "wav_exists": wav_exists,
        "audio_url": f"/audio/{wav_file}" if wav_exists else None,
        "duration_seconds": float(row.get("duration_seconds", 0.0)),
        "prompt_id": str(row.get("prompt_id", "")),
        "prompt_text": str(row.get("prompt_text", "")),
        "target_terms_hint": str(row.get("target_terms_hint", "")),
        "primary_category_hint": str(row.get("primary_category_hint", "")),
        "is_double_annotation_candidate": bool(row.get("is_double_annotation_candidate", False)),
        "verbatim_transcript": "" if pd.isna(row.get("verbatim_transcript")) else str(row.get("verbatim_transcript")),
        "annotator_identified_terms": parsed_terms,
        "annotator_status": str(row.get("annotator_status", "pending")),
        "audio_quality_flag": str(row.get("audio_quality_flag", "normal")),
        "annotator_comments": "" if pd.isna(row.get("annotator_comments")) else str(row.get("annotator_comments"))
    }


@app.post("/api/save")
def save_annotation(payload: SaveAnnotationRequest):
    """Saves updated annotation, updates batch CSV atomically, and returns next pending recording."""
    ann = payload.annotator_id.upper()
    df = load_annotator_df(ann)
    idx_match = df.index[df["recording_id"] == payload.recording_id].tolist()
    if not idx_match:
        raise HTTPException(status_code=404, detail=f"Recording {payload.recording_id} not found.")

    row_idx = idx_match[0]

    # Format identified terms as JSON string
    terms_json_str = json.dumps(payload.annotator_identified_terms, ensure_ascii=False)

    df.at[row_idx, "verbatim_transcript"] = payload.verbatim_transcript.strip()
    df.at[row_idx, "annotator_identified_terms"] = terms_json_str
    df.at[row_idx, "annotator_status"] = payload.annotator_status
    df.at[row_idx, "audio_quality_flag"] = payload.audio_quality_flag
    df.at[row_idx, "annotator_comments"] = (payload.annotator_comments or "").strip()

    save_annotator_df(ann, df)

    # Find next pending record
    subsequent_pending = df.iloc[row_idx + 1:]
    next_pending = subsequent_pending[subsequent_pending["annotator_status"] != "completed"]
    if next_pending.empty:
        # Wrap around from beginning
        all_pending = df[df["annotator_status"] != "completed"]
        next_rec_id = all_pending.iloc[0]["recording_id"] if not all_pending.empty else None
    else:
        next_rec_id = next_pending.iloc[0]["recording_id"]

    return {
        "status": "success",
        "saved_recording_id": payload.recording_id,
        "next_recording_id": next_rec_id
    }


# ==============================================================================
# HTML5 FRONTEND
# ==============================================================================

HTML_CONTENT = """<!DOCTYPE html>
<html lang="vi">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LiemWhisper Web Annotation Studio</title>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --bg: #0f172a;
      --card-bg: #1e293b;
      --card-border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --primary: #3b82f6;
      --primary-hover: #2563eb;
      --success: #10b981;
      --warning: #f59e0b;
      --danger: #ef4444;
      --accent: #8b5cf6;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; font-family: 'Inter', sans-serif; }
    body { background-color: var(--bg); color: var(--text); min-height: 100vh; display: flex; flex-direction: column; }
    
    /* Header */
    header {
      background: var(--card-bg);
      border-bottom: 1px solid var(--card-border);
      padding: 12px 24px;
      display: flex;
      justify-content: space-between;
      align-items: center;
      position: sticky;
      top: 0;
      z-index: 100;
    }
    .logo-area { display: flex; align-items: center; gap: 12px; }
    .logo-badge { background: linear-gradient(135deg, #3b82f6, #8b5cf6); color: white; padding: 4px 10px; border-radius: 6px; font-weight: 700; font-size: 14px; }
    .annotator-toggle { display: flex; background: #0f172a; border-radius: 8px; padding: 3px; border: 1px solid var(--card-border); }
    .toggle-btn { background: none; border: none; color: var(--text-muted); padding: 6px 16px; border-radius: 6px; cursor: pointer; font-weight: 600; font-size: 13px; transition: all 0.2s; }
    .toggle-btn.active { background: var(--primary); color: white; }
    
    .stats-bar { display: flex; gap: 16px; font-size: 13px; color: var(--text-muted); align-items: center; }
    .stat-pill { background: #0f172a; padding: 4px 10px; border-radius: 6px; border: 1px solid var(--card-border); }
    .stat-val { color: var(--text); font-weight: 600; }
    .progress-track { width: 120px; height: 8px; background: #334155; border-radius: 4px; overflow: hidden; }
    .progress-fill { height: 100%; background: var(--success); width: 0%; transition: width 0.3s; }

    /* Layout */
    .main-container { display: flex; flex: 1; height: calc(100vh - 65px); }
    
    /* Sidebar List */
    .sidebar { width: 320px; background: #131d31; border-right: 1px solid var(--card-border); display: flex; flex-direction: column; }
    .sidebar-filter { padding: 12px; border-bottom: 1px solid var(--card-border); display: flex; gap: 6px; }
    .filter-btn { flex: 1; padding: 6px 4px; font-size: 11px; font-weight: 600; border-radius: 4px; background: var(--card-bg); color: var(--text-muted); border: 1px solid var(--card-border); cursor: pointer; text-align: center; }
    .filter-btn.active { background: var(--primary); color: white; border-color: var(--primary); }
    .search-box { padding: 8px 12px; background: #0f172a; border-bottom: 1px solid var(--card-border); }
    .search-input { width: 100%; background: var(--card-bg); border: 1px solid var(--card-border); color: white; padding: 6px 10px; border-radius: 6px; font-size: 12px; }
    .records-list { flex: 1; overflow-y: auto; }
    .record-item { padding: 10px 14px; border-bottom: 1px solid rgba(255,255,255,0.05); cursor: pointer; transition: background 0.15s; font-size: 13px; }
    .record-item:hover { background: rgba(59, 130, 246, 0.1); }
    .record-item.active { background: rgba(59, 130, 246, 0.25); border-left: 3px solid var(--primary); }
    .rec-top { display: flex; justify-content: space-between; margin-bottom: 4px; }
    .rec-id { font-weight: 600; color: #60a5fa; }
    .rec-status { font-size: 10px; padding: 2px 6px; border-radius: 4px; text-transform: uppercase; font-weight: 700; }
    .status-pending { background: rgba(245, 158, 11, 0.2); color: #fbbf24; }
    .status-completed { background: rgba(16, 185, 129, 0.2); color: #34d399; }
    .rec-hint { font-size: 11px; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }

    /* Work Area */
    .workspace { flex: 1; padding: 24px; overflow-y: auto; display: flex; flex-direction: column; gap: 18px; }
    .card { background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 10px; padding: 18px; }
    
    /* Header Card */
    .rec-header-card { display: flex; justify-content: space-between; align-items: flex-start; }
    .rec-title-row { display: flex; align-items: center; gap: 10px; }
    .badge-double { background: rgba(139, 92, 246, 0.2); color: #c4b5fd; border: 1px solid #8b5cf6; font-size: 11px; padding: 3px 8px; border-radius: 4px; font-weight: 600; }
    
    /* Question / Target Hint */
    .prompt-box { background: #0f172a; border-left: 3px solid var(--primary); padding: 12px 16px; border-radius: 6px; margin-top: 10px; font-size: 14px; line-height: 1.5; }
    .hint-container { margin-top: 12px; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
    .hint-label { font-size: 12px; color: var(--text-muted); font-weight: 600; }
    .term-pill-click { background: rgba(59, 130, 246, 0.15); border: 1px solid var(--primary); color: #93c5fd; padding: 4px 10px; border-radius: 20px; font-size: 12px; font-weight: 600; cursor: pointer; transition: all 0.2s; }
    .term-pill-click:hover { background: var(--primary); color: white; transform: translateY(-1px); }

    /* Audio Player */
    .player-card { display: flex; align-items: center; gap: 16px; background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; padding: 12px 18px; }
    audio { flex: 1; height: 38px; outline: none; }
    .speed-btn-group { display: flex; gap: 4px; }
    .speed-btn { background: var(--card-bg); border: 1px solid var(--card-border); color: var(--text-muted); padding: 5px 8px; font-size: 11px; font-weight: 600; border-radius: 4px; cursor: pointer; }
    .speed-btn.active { background: var(--primary); color: white; border-color: var(--primary); }
    .hotkey-tip { font-size: 11px; color: var(--text-muted); }

    /* Transcript Editor */
    .editor-label-row { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
    .transcript-textarea { width: 100%; min-height: 140px; background: #0f172a; border: 1px solid var(--card-border); border-radius: 8px; color: white; padding: 14px; font-size: 15px; line-height: 1.6; resize: vertical; outline: none; transition: border-color 0.2s; }
    .transcript-textarea:focus { border-color: var(--primary); box-shadow: 0 0 0 2px rgba(59, 130, 246, 0.2); }

    /* Terms Tags Section */
    .terms-section { margin-top: 14px; }
    .tags-container { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; min-height: 34px; padding: 6px; background: #0f172a; border-radius: 6px; border: 1px solid var(--card-border); }
    .tag-item { background: rgba(16, 185, 129, 0.15); border: 1px solid var(--success); color: #6ee7b7; padding: 4px 10px; border-radius: 6px; font-size: 12px; display: flex; align-items: center; gap: 6px; }
    .tag-remove { cursor: pointer; font-weight: bold; color: #f87171; }
    .tag-remove:hover { color: #ef4444; }
    
    .add-term-row { display: flex; gap: 8px; margin-top: 8px; }
    .term-select { flex: 1; background: #0f172a; border: 1px solid var(--card-border); color: white; padding: 8px; border-radius: 6px; font-size: 13px; }
    .btn-add-term { background: var(--card-bg); border: 1px solid var(--card-border); color: var(--text); padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 600; }
    .btn-add-term:hover { background: #334155; }

    /* Quality Flags & Action Footer */
    .meta-row { display: flex; gap: 16px; align-items: center; }
    .quality-select { background: #0f172a; border: 1px solid var(--card-border); color: white; padding: 8px 12px; border-radius: 6px; font-size: 13px; }
    .comment-input { flex: 1; background: #0f172a; border: 1px solid var(--card-border); color: white; padding: 8px 12px; border-radius: 6px; font-size: 13px; }

    .action-footer { display: flex; justify-content: space-between; align-items: center; padding-top: 10px; border-top: 1px solid var(--card-border); }
    .btn-save { background: var(--success); color: white; border: none; padding: 12px 28px; border-radius: 8px; font-weight: 700; font-size: 14px; cursor: pointer; display: flex; align-items: center; gap: 8px; transition: all 0.2s; }
    .btn-save:hover { background: #059669; transform: translateY(-1px); box-shadow: 0 4px 12px rgba(16, 185, 129, 0.3); }
    .nav-buttons { display: flex; gap: 8px; }
    .btn-nav { background: var(--card-bg); border: 1px solid var(--card-border); color: white; padding: 10px 16px; border-radius: 6px; font-size: 13px; font-weight: 600; cursor: pointer; }
    .btn-nav:hover { background: #334155; }
  </style>
</head>
<body>

  <header>
    <div class="logo-area">
      <div class="logo-badge">LIEMWHISPER</div>
      <h2 style="font-size: 16px; font-weight: 600;">Web Annotation Studio</h2>
      <div class="annotator-toggle">
        <button class="toggle-btn active" id="btn-ann-a" onclick="switchAnnotator('A')">Annotator A</button>
        <button class="toggle-btn" id="btn-ann-b" onclick="switchAnnotator('B')">Annotator B</button>
      </div>
    </div>
    <div class="stats-bar">
      <div class="stat-pill">Tiến độ: <span class="stat-val" id="stat-completed">0</span> / <span id="stat-total">1198</span> (<span id="stat-pct">0%</span>)</div>
      <div class="progress-track"><div class="progress-fill" id="stat-progress-bar"></div></div>
      <div class="stat-pill">Còn lại: <span class="stat-val" id="stat-pending" style="color: #fbbf24;">1198</span></div>
      <div class="stat-pill">Gắn cờ: <span class="stat-val" id="stat-flagged" style="color: #f87171;">0</span></div>
    </div>
  </header>

  <div class="main-container">
    <!-- Sidebar -->
    <div class="sidebar">
      <div class="sidebar-filter">
        <button class="filter-btn active" onclick="setFilter('all', this)">TẤT CẢ</button>
        <button class="filter-btn" onclick="setFilter('pending', this)">CHƯA DUYỆT</button>
        <button class="filter-btn" onclick="setFilter('completed', this)">ĐÃ DUYỆT</button>
        <button class="filter-btn" onclick="setFilter('double', this)">CHÉO (IAA)</button>
      </div>
      <div class="search-box">
        <input type="text" class="search-input" id="search-input" placeholder="Tìm theo mã REC hoặc từ..." oninput="renderSidebar()">
      </div>
      <div class="records-list" id="records-list">
        <!-- Rendered dynamically -->
      </div>
    </div>

    <!-- Main Workspace -->
    <div class="workspace">
      <!-- Record Info Header -->
      <div class="card rec-header-card">
        <div>
          <div class="rec-title-row">
            <h2 id="disp-rec-id" style="font-size: 20px; font-weight: 700;">REC_0001</h2>
            <span id="disp-double-badge" class="badge-double" style="display: none;">ĐÁNH GIÁ CHÉO (IAA)</span>
            <span id="disp-status-badge" class="rec-status status-pending">PENDING</span>
          </div>
          <div style="font-size: 13px; color: var(--text-muted); margin-top: 4px;">
            Người nói: <strong id="disp-speaker" style="color: var(--text);">---</strong> | Thời lượng: <strong id="disp-dur" style="color: var(--text);">0.0s</strong> | Tệp: <code id="disp-wav">---.wav</code>
          </div>
        </div>
      </div>

      <!-- Question & Hints -->
      <div class="card">
        <div style="font-size: 12px; font-weight: 700; color: #60a5fa; text-transform: uppercase;">Câu hỏi thí sinh trả lời (<span id="disp-prompt-id">Q01</span>):</div>
        <div class="prompt-box" id="disp-prompt-text">Đang tải câu hỏi...</div>
        <div class="hint-container">
          <span class="hint-label">Thuật ngữ ISTQB mục tiêu:</span>
          <div id="disp-hint-badges" style="display: flex; gap: 6px; flex-wrap: wrap;"></div>
        </div>
      </div>

      <!-- Audio Player Card -->
      <div class="player-card">
        <audio id="audio-player" controls preload="auto"></audio>
        <div class="speed-btn-group">
          <button class="speed-btn" onclick="setPlaybackSpeed(0.85, this)">0.85x</button>
          <button class="speed-btn active" onclick="setPlaybackSpeed(1.0, this)">1.0x</button>
          <button class="speed-btn" onclick="setPlaybackSpeed(1.2, this)">1.2x</button>
        </div>
        <div class="hotkey-tip">Phím tắt: <code>Space</code> (Bật/Tắt) | <code>Alt+←</code> (-3s) | <code>Ctrl+Enter</code> (Lưu & Tiếp)</div>
      </div>

      <!-- Transcript Editor Card -->
      <div class="card">
        <div class="editor-label-row">
          <label style="font-weight: 600; font-size: 14px;">Bản dịch nguyên văn (Verbatim Transcript):</label>
          <span style="font-size: 12px; color: var(--text-muted);">Sửa lại chính xác các từ Whisper nghe nhầm thành thuật ngữ tiếng Anh ISTQB</span>
        </div>
        <textarea id="transcript-editor" class="transcript-textarea" placeholder="Nhập bản dịch chuẩn..."></textarea>

        <!-- Terms Identified Section -->
        <div class="terms-section">
          <div style="font-size: 13px; font-weight: 600; color: var(--text-muted);">Danh sách thuật ngữ ISTQB đã phát hiện trong câu này:</div>
          <div class="tags-container" id="terms-tags-container"></div>
          
          <div class="add-term-row">
            <select id="term-dropdown" class="term-select">
              <option value="">-- Chọn thuật ngữ ISTQB để chèn nhanh --</option>
            </select>
            <button class="btn-add-term" onclick="addSelectedDropdownTerm()">+ Thêm Thuật Ngữ</button>
          </div>
        </div>
      </div>

      <!-- Quality Flag & Comments -->
      <div class="card meta-row">
        <label style="font-size: 13px; font-weight: 600;">Chất lượng âm thanh:</label>
        <select id="quality-flag-select" class="quality-select">
          <option value="normal">Bình thường (Rõ ràng)</option>
          <option value="noisy">Nhiều tạp âm môi trường</option>
          <option value="muffled">Giọng nghẹt / Mic nhỏ</option>
          <option value="distorted">Âm méo / Rè</option>
          <option value="unintelligible">Không nghe rõ / Đứt quãng</option>
        </select>
        <input type="text" id="comments-input" class="comment-input" placeholder="Ghi chú thêm nếu có (ví dụ: phát âm nuốt đuôi, tiếng ồn quạt...)">
      </div>

      <!-- Action Footer -->
      <div class="action-footer">
        <div class="nav-buttons">
          <button class="btn-nav" onclick="navigatePrevious()">← Câu trước</button>
          <button class="btn-nav" onclick="navigateNext()">Câu sau →</button>
        </div>
        <button class="btn-save" onclick="saveCurrentAnnotation()">
          <span>✓ LƯU & TIẾP TỤC (Ctrl+Enter)</span>
        </button>
      </div>

    </div>
  </div>

  <script>
    let currentAnnotator = 'A';
    let currentFilter = 'all';
    let currentRecords = [];
    let currentRecordId = null;
    let currentRecordData = null;
    let identifiedTermsList = [];
    let fullTaxonomyTerms = [];

    // Initialize
    window.addEventListener('DOMContentLoaded', async () => {
      await loadTaxonomy();
      await refreshAll();
      setupHotkeys();
    });

    async function switchAnnotator(ann) {
      currentAnnotator = ann;
      document.getElementById('btn-ann-a').classList.toggle('active', ann === 'A');
      document.getElementById('btn-ann-b').classList.toggle('active', ann === 'B');
      await refreshAll();
    }

    async function setFilter(f, btn) {
      currentFilter = f;
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      await loadRecordsList();
    }

    async function refreshAll() {
      await updateStats();
      await loadRecordsList();
    }

    async function loadTaxonomy() {
      try {
        const res = await fetch('/api/taxonomy');
        const data = await res.json();
        fullTaxonomyTerms = data.terms;
        const select = document.getElementById('term-dropdown');
        select.innerHTML = '<option value="">-- Chọn thuật ngữ ISTQB để chèn nhanh --</option>';
        data.terms.forEach(t => {
          const opt = document.createElement('option');
          opt.value = t.term;
          opt.textContent = `${t.term} (${t.category})`;
          select.appendChild(opt);
        });
      } catch (e) {
        console.error('Error loading taxonomy:', e);
      }
    }

    async function updateStats() {
      try {
        const res = await fetch(`/api/stats?annotator=${currentAnnotator}`);
        const s = await res.json();
        document.getElementById('stat-completed').textContent = s.completed;
        document.getElementById('stat-total').textContent = s.total;
        document.getElementById('stat-pct').textContent = s.progress_pct + '%';
        document.getElementById('stat-pending').textContent = s.pending;
        document.getElementById('stat-flagged').textContent = s.flagged;
        document.getElementById('stat-progress-bar').style.width = s.progress_pct + '%';
      } catch (e) {
        console.error('Error updating stats:', e);
      }
    }

    async function loadRecordsList() {
      try {
        const res = await fetch(`/api/records?annotator=${currentAnnotator}&filter_status=${currentFilter}`);
        const data = await res.json();
        currentRecords = data.records;
        renderSidebar();
        if (currentRecords.length > 0 && (!currentRecordId || !currentRecords.some(r => r.recording_id === currentRecordId))) {
          loadRecord(currentRecords[0].recording_id);
        }
      } catch (e) {
        console.error('Error loading records:', e);
      }
    }

    function renderSidebar() {
      const q = document.getElementById('search-input').value.toLowerCase().trim();
      const listEl = document.getElementById('records-list');
      listEl.innerHTML = '';

      const filtered = currentRecords.filter(r => {
        if (!q) return true;
        return r.recording_id.toLowerCase().includes(q) ||
               r.target_terms_hint.toLowerCase().includes(q) ||
               r.prompt_id.toLowerCase().includes(q);
      });

      filtered.forEach(r => {
        const item = document.createElement('div');
        item.className = 'record-item' + (r.recording_id === currentRecordId ? ' active' : '');
        item.onclick = () => loadRecord(r.recording_id);

        const statusClass = r.annotator_status === 'completed' ? 'status-completed' : 'status-pending';
        item.innerHTML = `
          <div class="rec-top">
            <span class="rec-id">${r.recording_id} (${r.prompt_id})</span>
            <span class="rec-status ${statusClass}">${r.annotator_status}</span>
          </div>
          <div class="rec-hint">${r.target_terms_hint || 'Không có gợi ý'}</div>
        `;
        listEl.appendChild(item);
      });
    }

    async function loadRecord(recId) {
      currentRecordId = recId;
      renderSidebar();
      try {
        const res = await fetch(`/api/record/${currentAnnotator}/${recId}`);
        const d = await res.json();
        currentRecordData = d;

        document.getElementById('disp-rec-id').textContent = d.recording_id;
        document.getElementById('disp-speaker').textContent = d.speaker_name || d.speaker_id;
        document.getElementById('disp-dur').textContent = d.duration_seconds.toFixed(1) + 's';
        document.getElementById('disp-wav').textContent = d.wav_file;
        document.getElementById('disp-double-badge').style.display = d.is_double_annotation_candidate ? 'inline-block' : 'none';
        
        const stBadge = document.getElementById('disp-status-badge');
        stBadge.textContent = d.annotator_status.toUpperCase();
        stBadge.className = 'rec-status ' + (d.annotator_status === 'completed' ? 'status-completed' : 'status-pending');

        document.getElementById('disp-prompt-id').textContent = d.prompt_id;
        document.getElementById('disp-prompt-text').textContent = d.prompt_text || 'Chưa có văn bản câu hỏi.';
        
        // Render Hints
        const badgesContainer = document.getElementById('disp-hint-badges');
        badgesContainer.innerHTML = '';
        if (d.target_terms_hint) {
          d.target_terms_hint.split(';').forEach(term => {
            const t = term.trim();
            if (t) {
              const pill = document.createElement('button');
              pill.className = 'term-pill-click';
              pill.textContent = '+ ' + t;
              pill.onclick = () => insertTermAtCursor(t);
              badgesContainer.appendChild(pill);
            }
          });
        }

        // Set Audio
        const audio = document.getElementById('audio-player');
        if (d.audio_url) {
          audio.src = d.audio_url;
        } else {
          audio.removeAttribute('src');
        }

        // Set Transcript
        document.getElementById('transcript-editor').value = d.verbatim_transcript || '';

        // Set Identified Terms
        identifiedTermsList = d.annotator_identified_terms || [];
        renderTermsTags();

        // Quality & Comments
        document.getElementById('quality-flag-select').value = d.audio_quality_flag || 'normal';
        document.getElementById('comments-input').value = d.annotator_comments || '';

      } catch (e) {
        console.error('Error loading record detail:', e);
      }
    }

    function insertTermAtCursor(text) {
      const ta = document.getElementById('transcript-editor');
      const start = ta.selectionStart;
      const end = ta.selectionEnd;
      const current = ta.value;
      ta.value = current.substring(0, start) + text + current.substring(end);
      ta.focus();
      ta.setSelectionRange(start + text.length, start + text.length);

      // Also add to tags if not present
      if (!identifiedTermsList.some(item => item.term.toLowerCase() === text.toLowerCase())) {
        const match = fullTaxonomyTerms.find(t => t.term.toLowerCase() === text.toLowerCase());
        const cat = match ? match.category : 'General';
        identifiedTermsList.push({ term: text, category: cat });
        renderTermsTags();
      }
    }

    function renderTermsTags() {
      const container = document.getElementById('terms-tags-container');
      container.innerHTML = '';
      if (identifiedTermsList.length === 0) {
        container.innerHTML = '<span style="font-size: 12px; color: var(--text-muted);">Chưa có thuật ngữ nào được gán. Click vào gợi ý ở trên hoặc chọn từ dropdown dưới.</span>';
        return;
      }
      identifiedTermsList.forEach((item, idx) => {
        const tag = document.createElement('div');
        tag.className = 'tag-item';
        tag.innerHTML = `
          <span>${item.term}</span>
          <span style="font-size: 10px; opacity: 0.7;">(${item.category})</span>
          <span class="tag-remove" onclick="removeTermTag(${idx})">×</span>
        `;
        container.appendChild(tag);
      });
    }

    function removeTermTag(idx) {
      identifiedTermsList.splice(idx, 1);
      renderTermsTags();
    }

    function addSelectedDropdownTerm() {
      const sel = document.getElementById('term-dropdown');
      const termName = sel.value;
      if (!termName) return;
      if (!identifiedTermsList.some(item => item.term.toLowerCase() === termName.toLowerCase())) {
        const match = fullTaxonomyTerms.find(t => t.term.toLowerCase() === termName.toLowerCase());
        const cat = match ? match.category : 'General';
        identifiedTermsList.push({ term: termName, category: cat });
        renderTermsTags();
      }
      sel.value = '';
    }

    async function saveCurrentAnnotation() {
      if (!currentRecordId) return;
      const transcript = document.getElementById('transcript-editor').value;
      const quality = document.getElementById('quality-flag-select').value;
      const comments = document.getElementById('comments-input').value;

      const payload = {
        recording_id: currentRecordId,
        annotator_id: currentAnnotator,
        verbatim_transcript: transcript,
        annotator_identified_terms: identifiedTermsList,
        annotator_status: 'completed',
        audio_quality_flag: quality,
        annotator_comments: comments
      };

      try {
        const res = await fetch('/api/save', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload)
        });
        const result = await res.json();
        await updateStats();
        
        // Update local item status
        const item = currentRecords.find(r => r.recording_id === currentRecordId);
        if (item) item.annotator_status = 'completed';

        if (result.next_recording_id) {
          loadRecord(result.next_recording_id);
        } else {
          alert('Tuyệt vời! Bạn đã hoàn thành tất cả các câu trong danh sách!');
        }
      } catch (e) {
        console.error('Error saving annotation:', e);
        alert('Lỗi khi lưu: ' + e);
      }
    }

    function navigatePrevious() {
      const idx = currentRecords.findIndex(r => r.recording_id === currentRecordId);
      if (idx > 0) {
        loadRecord(currentRecords[idx - 1].recording_id);
      }
    }

    function navigateNext() {
      const idx = currentRecords.findIndex(r => r.recording_id === currentRecordId);
      if (idx >= 0 && idx < currentRecords.length - 1) {
        loadRecord(currentRecords[idx + 1].recording_id);
      }
    }

    function setPlaybackSpeed(speed, btn) {
      const audio = document.getElementById('audio-player');
      audio.playbackRate = speed;
      document.querySelectorAll('.speed-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
    }

    function setupHotkeys() {
      document.addEventListener('keydown', (e) => {
        const audio = document.getElementById('audio-player');
        const activeTag = document.activeElement.tagName;

        // Ctrl + Enter: Save and next
        if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
          e.preventDefault();
          saveCurrentAnnotation();
          return;
        }

        // Alt + Left: Replay 3s
        if (e.altKey && e.key === 'ArrowLeft') {
          e.preventDefault();
          audio.currentTime = Math.max(0, audio.currentTime - 3);
          return;
        }

        // Alt + Right: Forward 3s
        if (e.altKey && e.key === 'ArrowRight') {
          e.preventDefault();
          audio.currentTime = Math.min(audio.duration || 0, audio.currentTime + 3);
          return;
        }

        // Space to toggle play/pause when NOT typing in textarea or input
        if (e.key === ' ' && activeTag !== 'TEXTAREA' && activeTag !== 'INPUT') {
          e.preventDefault();
          if (audio.paused) {
            audio.play();
          } else {
            audio.pause();
          }
        }
      });
    }
  </script>
</body>
</html>
"""

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(content=HTML_CONTENT)


def main():
    parser = argparse.ArgumentParser(description="LiemWhisper Web Annotation Studio")
    parser.add_argument("--host", type=str, default="127.0.0.1", help="Host interface (default: 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port to run server on (default: 8000)")
    args = parser.parse_args()

    import uvicorn
    print("=" * 80)
    print("LIEMWHISPER WEB ANNOTATION STUDIO")
    print("=" * 80)
    print(f"Server running at    : http://{args.host}:{args.port}")
    print(f"Annotator A Batch    : {FILE_A}")
    print(f"Annotator B Batch    : {FILE_B}")
    print(f"Audio Repository     : {WAV_DIR}")
    print("=" * 80)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
