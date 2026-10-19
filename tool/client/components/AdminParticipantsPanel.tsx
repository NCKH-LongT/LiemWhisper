"use client";

import React, { useState, useEffect, useMemo } from "react";
import { AuthenticatedAudioPlayer } from "./AuthenticatedAudioPlayer";

interface ParticipantItem {
  id: string;
  participant_code: string;
  name: string;
  email: string;
  onboarded: number;
  consent_at: number;
  completed_at: number;
  is_admin?: number;
  drive_folder_id?: string;
  recordings_count: number;
  total_duration_seconds: number;
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

interface AdminParticipantsPanelProps {
  apiBase: string;
  adminKey: string;
}

export function AdminParticipantsPanel({ apiBase, adminKey }: AdminParticipantsPanelProps) {
  const [participants, setParticipants] = useState<ParticipantItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");

  // Modal / Detail state
  const [selectedParticipant, setSelectedParticipant] = useState<ParticipantItem | null>(null);
  const [recordings, setRecordings] = useState<RecordingItem[]>([]);
  const [loadingRecordings, setLoadingRecordings] = useState(false);
  const [recordingsError, setRecordingsError] = useState<string | null>(null);

  const loadParticipants = async () => {
    if (!adminKey) return;
    setLoading(true);
    setError(null);
    try {
      const res = await fetch(`${apiBase}/api/v1/admin/participants?limit=500`, {
        headers: { "x-admin-key": adminKey }
      });
      if (!res.ok) {
        throw new Error(`Lỗi tải danh sách người dùng (HTTP ${res.status})`);
      }
      const data = await res.json();
      setParticipants(data.participants || []);
    } catch (err: any) {
      setError(err.message || "Không thể tải danh sách người tham gia");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadParticipants();
  }, [adminKey]);

  // Open participant detail modal and fetch their recordings
  const openParticipantDetail = async (p: ParticipantItem) => {
    setSelectedParticipant(p);
    setRecordings([]);
    setRecordingsError(null);
    setLoadingRecordings(true);

    try {
      const res = await fetch(
        `${apiBase}/api/v1/admin/recordings?participant_id=${encodeURIComponent(p.id)}&limit=500`,
        {
          headers: { "x-admin-key": adminKey }
        }
      );
      if (!res.ok) {
        throw new Error(`Lỗi tải danh sách bản thu (HTTP ${res.status})`);
      }
      const list: RecordingItem[] = await res.json();
      setRecordings(list);
    } catch (err: any) {
      setRecordingsError(err.message || "Không thể tải các câu thu âm của người này");
    } finally {
      setLoadingRecordings(false);
    }
  };

  const closeDetail = () => {
    setSelectedParticipant(null);
    setRecordings([]);
  };

  // Filtered list
  const filteredParticipants = useMemo(() => {
    if (!search.trim()) return participants;
    const q = search.toLowerCase().trim();
    return participants.filter(
      (p) =>
        (p.participant_code && p.participant_code.toLowerCase().includes(q)) ||
        (p.name && p.name.toLowerCase().includes(q)) ||
        (p.email && p.email.toLowerCase().includes(q))
    );
  }, [participants, search]);

  // High-level aggregates
  const totalRecordedCount = participants.reduce((acc, p) => acc + (p.recordings_count || 0), 0);
  const totalCompletedCount = participants.filter((p) => (p.completed_at || 0) > 0).length;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* Summary Cards */}
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
        <div style={cardStatStyle}>
          <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>TỔNG NGƯỜI ĐĂNG KÝ</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "var(--text)", marginTop: 4 }}>
            {participants.length}
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>Thí sinh trong hệ thống</div>
        </div>

        <div style={cardStatStyle}>
          <div style={{ fontSize: 12, color: "var(--success)", fontWeight: 600 }}>ĐÃ HOÀN THÀNH</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "var(--success)", marginTop: 4 }}>
            {totalCompletedCount}
          </div>
          <div style={{ fontSize: 11, color: "var(--success-bg)", marginTop: 2 }}>Đã nộp bài đầy đủ</div>
        </div>

        <div style={cardStatStyle}>
          <div style={{ fontSize: 12, color: "var(--primary)", fontWeight: 600 }}>TỔNG BẢN THU ÂM</div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "var(--primary)", marginTop: 4 }}>
            {totalRecordedCount}
          </div>
          <div style={{ fontSize: 11, color: "var(--border)", marginTop: 2 }}>Câu đã được ghi âm</div>
        </div>
      </div>

      {/* Main Table Card */}
      <section style={panelCardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
          <div>
            <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: "var(--text)" }}>
              Danh sách Người dùng / Sinh viên đăng ký
            </h2>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
              Bấm vào tên hoặc nút "Xem chi tiết" để nghe toàn bộ audio các câu người đó đã thu
            </div>
          </div>

          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <input
              type="text"
              placeholder="Tìm theo Mã SV, họ tên, email..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={searchInputStyle}
            />
            <button
              type="button"
              onClick={loadParticipants}
              disabled={loading}
              style={btnRefreshStyle}
              title="Tải lại danh sách"
            >
              <span>{loading ? "Đang tải..." : "Làm mới"}</span>
            </button>
          </div>
        </div>

        {error && (
          <div style={{ padding: "10px 14px", background: "var(--danger-bg)", color: "var(--danger)", borderRadius: 6, fontSize: 13, marginBottom: 12 }}>
            {error}
          </div>
        )}

        {loading && participants.length === 0 ? (
          <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontSize: 14 }}>
            Đang tải dữ liệu danh sách người dùng...
          </div>
        ) : filteredParticipants.length === 0 ? (
          <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontSize: 14, background: "var(--subtle)", borderRadius: 8 }}>
            {search ? "Không tìm thấy người tham gia nào khớp với từ khóa tìm kiếm." : "Chưa có người dùng nào đăng ký."}
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "var(--subtle)", borderBottom: "1px solid var(--border)", textAlign: "left", color: "var(--muted)" }}>
                  <th style={{ padding: "12px 14px", fontWeight: 600 }}>Mã SV / Thí sinh</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600 }}>Họ và tên</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600 }}>Tài khoản Gmail</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600 }}>Trạng thái</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600, textAlign: "center" }}>Số câu đã thu</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600, textAlign: "center" }}>Thời lượng</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600 }}>Ngày đăng ký</th>
                  <th style={{ padding: "12px 14px", fontWeight: 600, textAlign: "right" }}>Thao tác</th>
                </tr>
              </thead>
              <tbody>
                {filteredParticipants.map((p) => {
                  const isCompleted = Boolean(p.completed_at && p.completed_at > 0);
                  const regDate = p.consent_at ? new Date(p.consent_at * 1000).toLocaleString("vi-VN") : "N/A";
                  const totalSec = p.total_duration_seconds || 0;
                  const durationStr = totalSec >= 60 ? `${(totalSec / 60).toFixed(1)} phút` : `${totalSec.toFixed(1)}s`;

                  return (
                    <tr
                      key={p.id}
                      style={{
                        borderBottom: "1px solid var(--subtle)",
                        cursor: "pointer",
                        transition: "background 0.15s"
                      }}
                      onClick={() => openParticipantDetail(p)}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--subtle)")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      <td style={{ padding: "12px 14px" }}>
                        <div style={{ fontWeight: 700, color: "var(--text)", display: "flex", alignItems: "center", gap: 6 }}>
                          <span>{p.participant_code || `SV_${p.id.slice(0, 6)}`}</span>
                          {p.is_admin ? (
                            <span style={{ fontSize: 10, background: "var(--subtle)", color: "var(--primary)", padding: "1px 5px", borderRadius: 3, fontWeight: 600 }}>
                              Admin
                            </span>
                          ) : null}
                        </div>
                      </td>
                      <td style={{ padding: "12px 14px", color: "var(--text)", fontWeight: 500 }}>
                        {p.name || <span style={{ color: "var(--muted)" }}>Chưa cập nhật</span>}
                      </td>
                      <td style={{ padding: "12px 14px", color: "var(--muted)" }}>
                        {p.email || <span style={{ color: "var(--muted)" }}>-</span>}
                      </td>
                      <td style={{ padding: "12px 14px" }}>
                        {isCompleted ? (
                          <span style={{ display: "inline-block", background: "var(--success-bg)", color: "var(--success)", padding: "3px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>
                            Đã hoàn thành
                          </span>
                        ) : (
                          <span style={{ display: "inline-block", background: "var(--subtle)", color: "var(--warning)", padding: "3px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>
                            Đang thu âm
                          </span>
                        )}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "center" }}>
                        <span style={{ display: "inline-block", background: p.recordings_count > 0 ? "var(--subtle)" : "var(--subtle)", color: p.recordings_count > 0 ? "var(--primary)" : "var(--muted)", padding: "2px 8px", borderRadius: 12, fontWeight: 700, fontSize: 12 }}>
                          {p.recordings_count || 0} câu
                        </span>
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "center", color: "var(--muted)", fontWeight: 500 }}>
                        {p.recordings_count > 0 ? durationStr : "-"}
                      </td>
                      <td style={{ padding: "12px 14px", color: "var(--muted)", fontSize: 12 }}>
                        {regDate}
                      </td>
                      <td style={{ padding: "12px 14px", textAlign: "right" }}>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openParticipantDetail(p);
                          }}
                          style={btnDetailStyle}
                        >
                          Xem audio ({p.recordings_count || 0})
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

      {/* DETAIL MODAL / DRAWER: ALL RECORDINGS OF CHOSEN PARTICIPANT */}
      {selectedParticipant && (
        <div style={modalBackdropStyle} onClick={closeDetail}>
          <div
            style={modalContentStyle}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", padding: "18px 24px", borderBottom: "1px solid var(--border)", background: "var(--subtle)" }}>
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
                  <h3 style={{ fontSize: 18, fontWeight: 700, margin: 0, color: "var(--text)" }}>
                    {selectedParticipant.name || selectedParticipant.participant_code}
                  </h3>
                  <span style={{ background: "var(--border)", color: "var(--text)", padding: "2px 8px", borderRadius: 4, fontSize: 12, fontWeight: 600 }}>
                    Mã SV: {selectedParticipant.participant_code}
                  </span>
                  {selectedParticipant.completed_at ? (
                    <span style={{ background: "var(--success-bg)", color: "var(--success)", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>
                      Đã hoàn thành bài thi
                    </span>
                  ) : (
                    <span style={{ background: "var(--subtle)", color: "var(--warning)", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>
                      Chưa hoàn thành
                    </span>
                  )}
                </div>
                <div style={{ fontSize: 13, color: "var(--muted)", marginTop: 4 }}>
                  Email: {selectedParticipant.email || "N/A"} • Tổng số: {recordings.length} câu đã thu âm
                </div>
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
            <div style={{ padding: "20px 24px", overflowY: "auto", maxHeight: "calc(85vh - 90px)" }}>
              {recordingsError && (
                <div style={{ padding: "12px 16px", background: "var(--danger-bg)", color: "var(--danger)", borderRadius: 6, fontSize: 13, marginBottom: 16 }}>
                  {recordingsError}
                </div>
              )}

              {loadingRecordings ? (
                <div style={{ padding: "40px 0", textAlign: "center", color: "var(--muted)" }}>
                  Đang tải danh sách bài thu âm và âm thanh...
                </div>
              ) : recordings.length === 0 ? (
                <div style={{ padding: "40px 0", textAlign: "center", color: "var(--muted)", background: "var(--subtle)", borderRadius: 8 }}>
                  Người dùng này chưa có bản thu âm nào.
                </div>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {recordings.map((rec, index) => {
                    const timeStr = rec.created_at ? new Date(rec.created_at * 1000).toLocaleString("vi-VN") : "";
                    const isSynced = rec.drive_sync_status === "synced";

                    return (
                      <div
                        key={rec.id}
                        style={{
                          border: "1px solid var(--border)",
                          borderRadius: 8,
                          padding: "16px 18px",
                          background: "var(--surface)",
                          boxShadow: "0 1px 3px rgba(0,0,0,0.03)"
                        }}
                      >
                        {/* Question Title & Meta */}
                        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", flexWrap: "wrap", gap: 8, marginBottom: 8 }}>
                          <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                            <span style={{ background: "var(--primary)", color: "var(--on-primary)", fontSize: 12, fontWeight: 700, padding: "2px 8px", borderRadius: 4 }}>
                              Câu {index + 1}
                            </span>
                            <span style={{ fontSize: 12, color: "var(--muted)", fontWeight: 600 }}>
                              {rec.course_title || "Khóa học"}
                            </span>
                          </div>

                          <div style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 12 }}>
                            {isSynced ? (
                              <span style={{ background: "var(--success-bg)", color: "var(--success)", padding: "2px 6px", borderRadius: 4, fontWeight: 600 }}>
                                Drive: Đã đồng bộ
                              </span>
                            ) : (
                              <span style={{ background: "var(--subtle)", color: "var(--muted)", padding: "2px 6px", borderRadius: 4 }}>
                                Drive: Chờ đồng bộ
                              </span>
                            )}
                            <span style={{ color: "var(--muted)" }}>{timeStr}</span>
                          </div>
                        </div>

                        {/* Prompt Text */}
                        <div style={{ fontSize: 15, fontWeight: 600, color: "var(--text)", marginBottom: 10, lineHeight: 1.45 }}>
                          {rec.text}
                        </div>

                        {/* Target Terms Badges */}
                        {rec.target_terms && rec.target_terms.length > 0 && (
                          <div style={{ display: "flex", gap: 6, flexWrap: "wrap", marginBottom: 12 }}>
                            {rec.target_terms.map((term, tIdx) => (
                              <span
                                key={tIdx}
                                style={{
                                  background: "var(--subtle)",
                                  color: "var(--text)",
                                  fontSize: 11,
                                  fontWeight: 600,
                                  padding: "2px 6px",
                                  borderRadius: 4
                                }}
                              >
                                #{term}
                              </span>
                            ))}
                          </div>
                        )}

                        {/* Audio Player & Duration Info */}
                        <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", flexWrap: "wrap", gap: 12, background: "var(--subtle)", padding: "10px 14px", borderRadius: 6, border: "1px solid var(--subtle)" }}>
                          <div style={{ flex: 1, minWidth: 260 }}>
                            <AuthenticatedAudioPlayer
                              apiBase={apiBase}
                              audioPath={`/api/v1/admin/recordings/${rec.id}/audio`}
                              authHeader={{ name: "x-admin-key", value: adminKey }}
                              style={{ width: "100%" }}
                            />
                          </div>

                          <div style={{ fontSize: 12, color: "var(--muted)", fontWeight: 500, textAlign: "right" }}>
                            <div>Thời lượng: <strong>{rec.duration_seconds ? rec.duration_seconds.toFixed(1) : "0.0"}s</strong></div>
                            <div style={{ fontSize: 11, color: "var(--muted)" }}>Định dạng: {rec.format?.toUpperCase() || "WEBM"}</div>
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
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "16px 18px",
  boxShadow: "0 1px 2px rgba(0,0,0,0.03)"
};

const panelCardStyle: React.CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--border)",
  borderRadius: 8,
  padding: "20px 22px",
  boxShadow: "0 1px 3px rgba(0,0,0,0.04)"
};

const searchInputStyle: React.CSSProperties = {
  padding: "8px 14px",
  fontSize: 13,
  borderRadius: 6,
  border: "1px solid var(--border)",
  outline: "none",
  minWidth: 260
};

const btnRefreshStyle: React.CSSProperties = {
  padding: "8px 14px",
  fontSize: 13,
  fontWeight: 600,
  borderRadius: 6,
  border: "1px solid var(--border)",
  background: "var(--subtle)",
  color: "var(--text)",
  cursor: "pointer"
};

const btnDetailStyle: React.CSSProperties = {
  padding: "6px 12px",
  fontSize: 12,
  fontWeight: 600,
  borderRadius: 6,
  border: "1px solid var(--border)",
  background: "var(--subtle)",
  color: "var(--primary)",
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
  background: "var(--surface)",
  borderRadius: 12,
  maxWidth: 820,
  width: "100%",
  boxShadow: "0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)",
  overflow: "hidden"
};

const btnCloseModalStyle: React.CSSProperties = {
  background: "transparent",
  border: "none",
  fontSize: 18,
  color: "var(--muted)",
  cursor: "pointer",
  padding: "4px 8px",
  borderRadius: 4
};
