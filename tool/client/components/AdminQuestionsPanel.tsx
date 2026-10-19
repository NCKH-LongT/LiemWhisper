"use client";

import React, { useState, useEffect, useMemo } from "react";
import { AuthenticatedAudioPlayer } from "./AuthenticatedAudioPlayer";

interface PromptItem {
  id: string;
  course_id: string;
  course_title: string;
  text: string;
  target_terms: string[];
  language: string;
  difficulty: string;
  category: string;
  published: number;
  created_at: number;
  recordings_count: number;
}

interface RecordingItem {
  id: string;
  participant_id: string;
  prompt_id: string;
  course_id: string;
  course_title: string;
  text: string;
  target_terms: string[];
  participant_code: string;
  participant_name: string;
  participant_email: string;
  status: string;
  duration_seconds: number;
  bytes: number;
  mime: string;
  format: string;
  created_at: number;
  drive_sync_status?: string;
  drive_file_id?: string;
}

interface CourseOption {
  id: string;
  title: string;
}

interface AdminQuestionsPanelProps {
  apiBase: string;
  adminKey: string;
  courses: CourseOption[];
}

export function AdminQuestionsPanel({ apiBase, adminKey, courses }: AdminQuestionsPanelProps) {
  const [prompts, setPrompts] = useState<PromptItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Filters
  const [selectedCourseId, setSelectedCourseId] = useState<string>("all");
  const [search, setSearch] = useState("");

  // Modal / Detail state: recordings for a prompt
  const [selectedPrompt, setSelectedPrompt] = useState<PromptItem | null>(null);
  const [promptRecordings, setPromptRecordings] = useState<RecordingItem[]>([]);
  const [loadingRecordings, setLoadingRecordings] = useState(false);
  const [recordingsError, setRecordingsError] = useState<string | null>(null);

  const loadPrompts = async () => {
    if (!adminKey) return;
    setLoading(true);
    setError(null);
    try {
      let url = `${apiBase}/api/v1/admin/prompts`;
      if (selectedCourseId && selectedCourseId !== "all") {
        url += `?course_id=${encodeURIComponent(selectedCourseId)}`;
      }
      const res = await fetch(url, {
        headers: { "x-admin-key": adminKey }
      });
      if (!res.ok) {
        throw new Error(`Lỗi tải danh sách câu hỏi (HTTP ${res.status})`);
      }
      const data = await res.json();
      setPrompts(data || []);
    } catch (err: any) {
      setError(err.message || "Không thể tải danh sách câu hỏi");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadPrompts();
  }, [adminKey, selectedCourseId]);

  // Open prompt detail modal and fetch all recordings answering this question
  const openPromptDetail = async (p: PromptItem) => {
    setSelectedPrompt(p);
    setPromptRecordings([]);
    setRecordingsError(null);
    setLoadingRecordings(true);

    try {
      const res = await fetch(
        `${apiBase}/api/v1/admin/recordings?prompt_id=${encodeURIComponent(p.id)}&limit=500`,
        {
          headers: { "x-admin-key": adminKey }
        }
      );
      if (!res.ok) {
        throw new Error(`Lỗi tải danh sách bản thu của câu này (HTTP ${res.status})`);
      }
      const list: RecordingItem[] = await res.json();
      setPromptRecordings(list);
    } catch (err: any) {
      setRecordingsError(err.message || "Không thể tải danh sách bản thu");
    } finally {
      setLoadingRecordings(false);
    }
  };

  const closeDetail = () => {
    setSelectedPrompt(null);
    setPromptRecordings([]);
  };

  // Filter prompts by text
  const filteredPrompts = useMemo(() => {
    if (!search.trim()) return prompts;
    const q = search.toLowerCase().trim();
    return prompts.filter((p) => p.text && p.text.toLowerCase().includes(q));
  }, [prompts, search]);

  const totalPromptsCount = prompts.length;
  const totalAnswersCount = prompts.reduce((acc, p) => acc + (p.recordings_count || 0), 0);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Summary Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
        <div style={cardStatStyle}>
          <div style={{ fontSize: 12, color: "#64748b", fontWeight: 600 }}>TỔNG SỐ CÂU HỎI</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#09090b", marginTop: 4 }}>
            {totalPromptsCount}
          </div>
          <div style={{ fontSize: 11, color: "#94a3b8", marginTop: 2 }}>Câu hỏi trong toàn hệ thống</div>
        </div>

        <div style={cardStatStyle}>
          <div style={{ fontSize: 12, color: "#2563eb", fontWeight: 600 }}>TỔNG BẢN THU TRẢ LỜI</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#2563eb", marginTop: 4 }}>
            {totalAnswersCount}
          </div>
          <div style={{ fontSize: 11, color: "#93c5fd", marginTop: 2 }}>Bài thu từ các sinh viên</div>
        </div>
      </div>

      {/* Main Table Card */}
      <section style={panelCardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: "#09090b" }}>
              Danh sách Câu hỏi & Bài thu âm trả lời
            </h2>
            <div style={{ fontSize: 12, color: "#71717a", marginTop: 2 }}>
              Chọn câu hỏi để nghe toàn bộ audio trả lời từ các sinh viên khác nhau
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            {/* Filter by Course */}
            <select
              value={selectedCourseId}
              onChange={(e) => setSelectedCourseId(e.target.value)}
              style={selectStyle}
            >
              <option value="all">Tất cả môn học ({courses.length})</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>

            <input
              type="text"
              placeholder="Tìm nội dung câu hỏi..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={searchInputStyle}
            />

            <button
              type="button"
              onClick={loadPrompts}
              disabled={loading}
              style={btnRefreshStyle}
              title="Tải lại danh sách"
            >
              <span>{loading ? "Đang tải..." : "Làm mới"}</span>
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: "10px 14px", background: "#fef2f2", color: "#dc2626", borderRadius: 6, fontSize: 13, marginBottom: 12 }}>
            {error}
          </div>
        )}

        {loading && prompts.length === 0 ? (
          <div style={{ padding: "32px 0", textAlign: "center", color: "#71717a", fontSize: 14 }}>
            Đang tải dữ liệu danh sách câu hỏi...
          </div>
        ) : filteredPrompts.length === 0 ? (
          <div style={{ padding: "32px 0", textAlign: "center", color: "#71717a", fontSize: 14, background: "#f8fafc", borderRadius: 8 }}>
            {search ? "Không tìm thấy câu hỏi nào khớp với từ khóa tìm kiếm." : "Chưa có câu hỏi nào trong môn học này."}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", textAlign: "left", color: "#475569" }}>
                  <th style={{ padding: "12px 14px", fontWeight: 600, width: 60 }}>STT</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600 }}>Nội dung câu hỏi (Prompt)</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600, width: 170 }}>Môn học</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600, textAlign: "center", width: 120 }}>Số bản thu</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600, textAlign: "right", width: 160 }}>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {filteredPrompts.map((p, idx) => {
                  const hasRecordings = (p.recordings_count || 0) > 0;
                  return (
                    <tr
                      key={p.id}
                      style={{
                        borderBottom: "1px solid #f1f5f9",
                        cursor: "pointer",
                        transition: "background 0.15s"
                      }}
                      onClick={() => openPromptDetail(p)}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "#f8fafc")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      <td style={{ padding: "12px 14px", color: "#64748b", fontWeight: 600 }}>
                        #{idx + 1}
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        <div style={{ fontWeight: 600, color: "#09090b", lineHeight: 1.45, marginBottom: 4 }}>
                          {p.text}
                        </div>
                        {p.target_terms && p.target_terms.length > 0 && (
                          <div style={{ display: "flex", gap: 4, flexWrap: "wrap" }}>
                            {p.target_terms.map((t, tIdx) => (
                              <span
                                key={tIdx}
                                style={{
                                  background: "#f1f5f9",
                                  color: "#475569",
                                  fontSize: 10,
                                  fontWeight: 600,
                                  padding: "1px 5px",
                                  borderRadius: 3
                                }}
                              >
                                {t}
                              </span>
                            ))}
                          </div>
                        )}
                      </td>
                      <td style={{ padding: "12px 14px", color: "#64748b", fontSize: 12 }}>
                        {p.course_title || "Khóa học"}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "center" }}>
                        <span
                          style={{
                            display: "inline-block",
                            background: hasRecordings ? "#eff6ff" : "#f1f5f9",
                            color: hasRecordings ? "#1d4ed8" : "#94a3b8",
                            padding: "2px 8px",
                            borderRadius: 12,
                            fontWeight: 700,
                            fontSize: 12
                          }}
                        >
                          {p.recordings_count || 0} bài
                        </span>
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right" }}>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openPromptDetail(p);
                          }}
                          style={{
                            ...btnDetailStyle,
                            opacity: hasRecordings ? 1 : 0.7
                          }}
                        >
                          Nghe audio ({p.recordings_count || 0})
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* DETAIL MODAL / DRAWER: ALL RECORDINGS FOR CHOSEN PROMPT */}
      {selectedPrompt && (
        <div style={modalBackdropStyle} onClick={closeDetail}>
          <div style={modalContentStyle} onClick={(e) => e.stopPropagation()}>
            {/* Modal Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "18px 24px", borderBottom: "1px solid #e2e8f0", background: "#f8fafc" }}>
              <div style={{ flex: 1, paddingRight: 16 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 6 }}>
                  <span style={{ background: "#2563eb", color: "#ffffff", padding: "2px 8px", borderRadius: 4, fontSize: 12, fontWeight: 700 }}>
                    Câu hỏi
                  </span>
                  <span style={{ color: "#64748b", fontSize: 13, fontWeight: 600 }}>
                    {selectedPrompt.course_title}
                  </span>
                  <span style={{ color: "#94a3b8", fontSize: 12 }}>• {promptRecordings.length} bản ghi âm</span>
                </div>

                <div style={{ fontSize: 16, fontWeight: 700, color: "#09090b", lineHeight: 1.45 }}>
                  {selectedPrompt.text}
                </div>

                {selectedPrompt.target_terms && selectedPrompt.target_terms.length > 0 && (
                  <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginTop: 8 }}>
                    {selectedPrompt.target_terms.map((t, tIdx) => (
                      <span
                        key={tIdx}
                        style={{
                          background: "#e2e8f0",
                          color: "#334155",
                          fontSize: 11,
                          fontWeight: 600,
                          padding: "2px 6px",
                          borderRadius: 4
                        }}
                      >
                        #{t}
                      </span>
                    ))}
                  </div>
                )}
              </div>

              <button
                type="button"
                onClick={closeDetail}
                style={btnCloseModalStyle}
                title="Đóng cửa sổ"
              >
                ✕
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ padding: "20px 24px", overflowY: "auto", maxHeight: "calc(85vh - 120px)" }}>
              {recordingsError && (
                <div style={{ padding: "12px 16px", background: "#fef2f2", color: "#dc2626", borderRadius: 6, fontSize: 13, marginBottom: 16 }}>
                  {recordingsError}
                </div>
              )}

              {loadingRecordings ? (
                <div style={{ padding: "40px 0", textAlign: "center", color: "#64748b" }}>
                  Đang tải danh sách bài thu âm từ các sinh viên...
                </div>
              ) : promptRecordings.length === 0 ? (
                <div style={{ padding: "40px 0", textAlign: "center", color: "#64748b", background: "#f8fafc", borderRadius: 8 }}>
                  Chưa có sinh viên nào ghi âm trả lời câu hỏi này.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {promptRecordings.map((rec) => {
                    const timeStr = rec.created_at ? new Date(rec.created_at * 1000).toLocaleString("vi-VN") : "";
                    const isSynced = rec.drive_sync_status === "synced";

                    return (
                      <div
                        key={rec.id}
                        style={{
                          border: "1px solid #e2e8f0",
                          borderRadius: 8,
                          padding: "16px 18px",
                          background: "#ffffff",
                          boxShadow: "0 1px 3px rgba(0,0,0,0.03)"
                        }}
                      >
                        {/* Student Info Bar */}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 8, marginBottom: 10 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <div style={{
                              width: 30,
                              height: 30,
                              borderRadius: "50%",
                              background: "#eff6ff",
                              color: "#2563eb",
                              display: "flex",
                              alignItems: "center",
                              justifyContent: "center",
                              fontWeight: 700,
                              fontSize: 12
                            }}>
                              {(rec.participant_name || rec.participant_code || "S").slice(0, 1).toUpperCase()}
                            </div>
                            <div>
                              <div style={{ fontWeight: 700, color: "#09090b", fontSize: 14 }}>
                                {rec.participant_name || rec.participant_code}
                                {rec.participant_name && (
                                  <span style={{ fontSize: 12, color: "#64748b", fontWeight: 400, marginLeft: 6 }}>
                                    ({rec.participant_code})
                                  </span>
                                )}
                              </div>
                              <div style={{ fontSize: 11, color: "#64748b" }}>
                                {rec.participant_email || "N/A"}
                              </div>
                            </div>
                          </div>

                          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                            {isSynced ? (
                              <span style={{ background: "#dcfce7", color: "#166534", padding: "2px 6px", borderRadius: 4, fontWeight: 600 }}>
                                Drive: Đã đồng bộ
                              </span>
                            ) : (
                              <span style={{ background: "#f1f5f9", color: "#64748b", padding: "2px 6px", borderRadius: 4 }}>
                                Drive: Chờ đồng bộ
                              </span>
                            )}
                            <span style={{ color: "#94a3b8" }}>{timeStr}</span>
                          </div>
                        </div>

                        {/* Audio Player & Duration Info */}
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, background: "#f8fafc", padding: "10px 14px", borderRadius: 6, border: "1px solid #f1f5f9" }}>
                          <div style={{ flex: 1, minWidth: 260 }}>
                            <AuthenticatedAudioPlayer
                              apiBase={apiBase}
                              audioPath={`/api/v1/admin/recordings/${rec.id}/audio`}
                              authHeader={{ name: "x-admin-key", value: adminKey }}
                              style={{ width: "100%" }}
                            />
                          </div>

                          <div style={{ fontSize: 12, color: "#475569", fontWeight: 500, textAlign: "right" }}>
                            <div>Thời lượng: <strong>{rec.duration_seconds ? rec.duration_seconds.toFixed(1) : "0.0"}s</strong></div>
                            <div style={{ fontSize: 11, color: "#94a3b8" }}>Định dạng: {rec.format?.toUpperCase() || "WEBM"}</div>
                          </div>
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

// Inline styles
const cardStatStyle: React.CSSProperties = {
  background: "#ffffff",
  border: "1px solid #e2e8f0",
  borderRadius: 8,
  padding: "16px 18px",
  boxShadow: "0 1px 2px rgba(0,0,0,0.03)"
};

const panelCardStyle: React.CSSProperties = {
  background: "#ffffff",
  border: "1px solid #e2e8f0",
  borderRadius: 8,
  padding: "20px 22px",
  boxShadow: "0 1px 3px rgba(0,0,0,0.04)"
};

const selectStyle: React.CSSProperties = {
  padding: "8px 12px",
  fontSize: 13,
  borderRadius: 6,
  border: "1px solid #cbd5e1",
  outline: "none",
  background: "#ffffff"
};

const searchInputStyle: React.CSSProperties = {
  padding: "8px 14px",
  fontSize: 13,
  borderRadius: 6,
  border: "1px solid #cbd5e1",
  outline: "none",
  minWidth: 240
};

const btnRefreshStyle: React.CSSProperties = {
  padding: "8px 14px",
  fontSize: 13,
  fontWeight: 600,
  borderRadius: 6,
  border: "1px solid #cbd5e1",
  background: "#f8fafc",
  color: "#334155",
  cursor: "pointer"
};

const btnDetailStyle: React.CSSProperties = {
  padding: "6px 12px",
  fontSize: 12,
  fontWeight: 600,
  borderRadius: 6,
  border: "1px solid #93c5fd",
  background: "#eff6ff",
  color: "#1d4ed8",
  cursor: "pointer"
};

const modalBackdropStyle: React.CSSProperties = {
  position: "fixed",
  top: 0,
  left: 0,
  right: 0,
  bottom: 0,
  background: "rgba(15, 23, 42, 0.65)",
  backdropFilter: "blur(3px)",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  zIndex: 1000,
  padding: 16
};

const modalContentStyle: React.CSSProperties = {
  background: "#ffffff",
  borderRadius: 12,
  maxWidth: 860,
  width: "100%",
  boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
  overflow: "hidden"
};

const btnCloseModalStyle: React.CSSProperties = {
  background: "transparent",
  border: "none",
  fontSize: 18,
  color: "#64748b",
  cursor: "pointer",
  padding: "4px 8px",
  borderRadius: 4
};
