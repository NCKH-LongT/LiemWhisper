"use client";

import React, { useState, useMemo, useEffect } from "react";

export interface PromptDurationStat {
  prompt_id: string;
  prompt_text: string;
  course_id: string;
  course_title: string;
  question_number?: number;
  published?: number;
  recordings_count: number;
  total_duration_seconds: number;
  avg_duration_seconds: number;
  min_duration_seconds: number;
  max_duration_seconds: number;
}

export interface DurationStatsData {
  total_seconds: number;
  avg_seconds: number;
  min_seconds: number;
  max_seconds: number;
}

interface AdminDashboardDurationProps {
  durationStats?: DurationStatsData;
  promptStats?: PromptDurationStat[];
  courses?: Array<{ id: string; title: string }>;
}

export function AdminDashboardDuration({
  durationStats,
  promptStats = [],
  courses = []
}: AdminDashboardDurationProps) {
  const [selectedCourse, setSelectedCourse] = useState<string>("all");
  const [search, setSearch] = useState<string>("");
  const [sortBy, setSortBy] = useState<"default" | "count_desc" | "avg_desc" | "max_desc">("default");

  const [visibleCount, setVisibleCount] = useState(20);
  const [expanded, setExpanded] = useState<string[]>([]);
  useEffect(() => setVisibleCount(20), [selectedCourse, search, sortBy]);

  // Format seconds to readable mm:ss or hh:mm:ss
  const formatDuration = (totalSec: number) => {
    if (!totalSec || totalSec <= 0) return "0s";
    if (totalSec < 60) return `${totalSec.toFixed(1)}s`;
    const mins = Math.floor(totalSec / 60);
    const secs = Math.round(totalSec % 60);
    if (mins < 60) return `${mins}p ${secs}s`;
    const hours = Math.floor(mins / 60);
    const remMins = mins % 60;
    return `${hours}h ${remMins}p ${secs}s`;
  };

  // Filter and sort prompts
  const filteredPrompts = useMemo(() => {
    let list = [...promptStats];

    if (selectedCourse !== "all") {
      list = list.filter((p) => p.course_id === selectedCourse);
    }

    if (search.trim()) {
      const q = search.toLowerCase().trim();
      list = list.filter((p) => p.prompt_text && p.prompt_text.toLowerCase().includes(q));
    }

    if (sortBy === "count_desc") {
      list.sort((a, b) => b.recordings_count - a.recordings_count);
    } else if (sortBy === "avg_desc") {
      list.sort((a, b) => b.avg_duration_seconds - a.avg_duration_seconds);
    } else if (sortBy === "max_desc") {
      list.sort((a, b) => b.max_duration_seconds - a.max_duration_seconds);
    }

    return list;
  }, [promptStats, selectedCourse, search, sortBy]);

  const totalSec = durationStats?.total_seconds || 0;
  const avgSec = durationStats?.avg_seconds || 0;
  const minSec = durationStats?.min_seconds || 0;
  const maxSec = durationStats?.max_seconds || 0;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 18 }}>
      {/* 1. Global Duration KPI Cards */}
      <div className="duration-kpis">
        <div style={kpiCardStyle}>
          <div style={{ fontSize: 12, color: "var(--primary)", fontWeight: 700, textTransform: "uppercase" }}>
            Tổng thời lượng thu âm
          </div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "var(--primary)", marginTop: 4 }}>
            {formatDuration(totalSec)}
          </div>
          <div style={{ fontSize: 11, color: "var(--muted)", marginTop: 2 }}>
            Tổng cộng {totalSec.toFixed(1)} giây
          </div>
        </div>

        <div style={kpiCardStyle}>
          <div style={{ fontSize: 12, color: "var(--primary)", fontWeight: 700, textTransform: "uppercase" }}>
            Thời lượng trung bình / câu
          </div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "var(--primary)", marginTop: 4 }}>
            {avgSec.toFixed(1)}s
          </div>
          <div style={{ fontSize: 11, color: "var(--border)", marginTop: 2 }}>
            Tính trên tất cả câu đã thu
          </div>
        </div>

        <div style={kpiCardStyle}>
          <div style={{ fontSize: 12, color: "var(--success)", fontWeight: 700, textTransform: "uppercase" }}>
            Thời lượng ngắn nhất (Min)
          </div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "var(--success)", marginTop: 4 }}>
            {minSec.toFixed(1)}s
          </div>
          <div style={{ fontSize: 11, color: "var(--success-bg)", marginTop: 2 }}>
            Bản thu ngắn nhất trong hệ thống
          </div>
        </div>

        <div style={kpiCardStyle}>
          <div style={{ fontSize: 12, color: "var(--primary)", fontWeight: 700, textTransform: "uppercase" }}>
            Thời lượng dài nhất (Max)
          </div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "var(--primary)", marginTop: 4 }}>
            {maxSec.toFixed(1)}s
          </div>
          <div style={{ fontSize: 11, color: "#fdba74", marginTop: 2 }}>
            Giới hạn tối đa là 45.0s
          </div>
        </div>
      </div>

      {/* 2. Detailed Per-Prompt Duration Table Card */}
      <section style={panelCardStyle}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
          <div>
            <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: "var(--text)" }}>
              Thống kê Thời lượng Từng Câu Hỏi (Min / Avg / Max)
            </h3>
            <div style={{ fontSize: 12, color: "var(--muted)", marginTop: 2 }}>
              Phân tích số lượng bản thu, thời lượng trung bình, ngắn nhất và dài nhất của từng câu
            </div>
          </div>

          {/* Filter Bar */}
          <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
            <select
              value={selectedCourse}
              onChange={(e) => setSelectedCourse(e.target.value)}
              style={selectStyle}
            >
              <option value="all">Tất cả môn học</option>
              {courses.map((c) => (
                <option key={c.id} value={c.id}>
                  {c.title}
                </option>
              ))}
            </select>

            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              style={selectStyle}
            >
              <option value="default">Sắp xếp: Mặc định</option>
              <option value="count_desc">Số bản thu: Nhiều nhất</option>
              <option value="avg_desc">Trung bình: Dài nhất</option>
              <option value="max_desc">Thời lượng Max: Cao nhất</option>
            </select>

            <input
              type="text"
              placeholder="Tìm nội dung câu..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={searchInputStyle}
            />
          </div>
        </div>

        {filteredPrompts.length === 0 ? (
          <div style={{ padding: "32px 0", textAlign: "center", color: "var(--muted)", fontSize: 13, background: "var(--subtle)", borderRadius: 8 }}>
            Không tìm thấy câu hỏi nào phù hợp với bộ lọc.
          </div>
        ) : (
          <div className="duration-table">
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "var(--subtle)", borderBottom: "1px solid var(--border)", textAlign: "left", color: "var(--muted)" }}>
                  <th style={{ padding: "11px 12px", fontWeight: 600, width: 50 }}>STT</th>
                  <th style={{ padding: "11px 14px", fontWeight: 600 }}>Nội dung câu hỏi</th>
                  <th style={{ padding: "11px 12px", fontWeight: 600, width: 140 }}>Môn học</th>
                  <th style={{ padding: "11px 12px", fontWeight: 600, textAlign: "center", width: 95 }}>Số bản thu</th>
                  <th style={{ padding: "11px 12px", fontWeight: 600, textAlign: "center", width: 105 }}>Tổng thời lượng</th>
                  <th style={{ padding: "11px 12px", fontWeight: 600, textAlign: "center", width: 100 }}>Trung bình (Avg)</th>
                  <th style={{ padding: "11px 12px", fontWeight: 600, textAlign: "center", width: 85 }}>Ngắn nhất (Min)</th>
                  <th style={{ padding: "11px 12px", fontWeight: 600, textAlign: "center", width: 85 }}>Dài nhất (Max)</th>
                  <th style={{ padding: "11px 14px", fontWeight: 600, width: 150 }}>Dải thời lượng (0-45s)</th>
                </tr>
              </thead>
              <tbody>
                {filteredPrompts.slice(0, visibleCount).map((p, idx) => {
                  const hasRecs = p.recordings_count > 0;
                  const minPct = Math.min(100, Math.max(0, (p.min_duration_seconds / 45) * 100));
                  const maxPct = Math.min(100, Math.max(0, (p.max_duration_seconds / 45) * 100));
                  const avgPct = Math.min(100, Math.max(0, (p.avg_duration_seconds / 45) * 100));

                  return (
                    <tr
                      key={p.prompt_id}
                      style={{
                        borderBottom: "1px solid var(--subtle)",
                        transition: "background 0.15s"
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "var(--subtle)")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      <td data-label="STT" style={{ padding: "11px 12px", color: "var(--muted)", fontWeight: 700, whiteSpace: "nowrap" }}>
                        {p.question_number ? `Câu ${String(p.question_number).padStart(2, "0")}` : `#${idx + 1}`}
                      </td>
                      <td data-label="" style={{ padding: "11px 14px" }}>
                        <div className={expanded.includes(p.prompt_id) ? "question-expanded" : "question-preview"} style={{ fontWeight: 500, color: "var(--text)", lineHeight: 1.6 }}>
                          {p.prompt_text}
                        </div>
                        <button className="text-button" aria-expanded={expanded.includes(p.prompt_id)} onClick={() => setExpanded(ids => ids.includes(p.prompt_id) ? ids.filter(id => id !== p.prompt_id) : [...ids, p.prompt_id])}>{expanded.includes(p.prompt_id) ? "Thu gọn" : "Xem thêm"}</button>
                      </td>
                      <td data-label="Môn học" style={{ padding: "11px 12px", color: "var(--muted)", fontSize: 12 }}>
                        {p.course_title}
                      </td>
                      <td data-label="Số bản thu" style={{ padding: "11px 12px", textAlign: "center" }}>
                        <span
                          style={{
                            display: "inline-block",
                            background: hasRecs ? "var(--subtle)" : "var(--subtle)",
                            color: hasRecs ? "var(--primary)" : "var(--muted)",
                            padding: "2px 8px",
                            borderRadius: 12,
                            fontWeight: 700,
                            fontSize: 12
                          }}
                        >
                          {p.recordings_count} bài
                        </span>
                      </td>
                      <td data-label="Tổng thời lượng" style={{ padding: "11px 12px", textAlign: "center", color: hasRecs ? "var(--text)" : "var(--muted)", fontWeight: 600 }}>
                        {hasRecs ? `${p.total_duration_seconds.toFixed(1)}s` : "-"}
                      </td>
                      <td data-label="Trung bình" style={{ padding: "11px 12px", textAlign: "center" }}>
                        {hasRecs ? (
                          <span style={{ fontWeight: 700, color: "var(--primary)", background: "var(--subtle)", padding: "2px 7px", borderRadius: 4 }}>
                            {p.avg_duration_seconds.toFixed(1)}s
                          </span>
                        ) : (
                          <span style={{ color: "var(--muted)" }}>-</span>
                        )}
                      </td>
                      <td data-label="Ngắn nhất" style={{ padding: "11px 12px", textAlign: "center" }}>
                        {hasRecs ? (
                          <span style={{ fontWeight: 600, color: "var(--success)", background: "var(--success-bg)", padding: "2px 6px", borderRadius: 4, fontSize: 12 }}>
                            {p.min_duration_seconds.toFixed(1)}s
                          </span>
                        ) : (
                          <span style={{ color: "var(--muted)" }}>-</span>
                        )}
                      </td>
                      <td data-label="Dài nhất" style={{ padding: "11px 12px", textAlign: "center" }}>
                        {hasRecs ? (
                          <span style={{ fontWeight: 600, color: "var(--primary)", background: "var(--subtle)", padding: "2px 6px", borderRadius: 4, fontSize: 12 }}>
                            {p.max_duration_seconds.toFixed(1)}s
                          </span>
                        ) : (
                          <span style={{ color: "var(--muted)" }}>-</span>
                        )}
                      </td>
                      <td data-label="" style={{ padding: "11px 14px" }}>
                        {hasRecs ? (
                          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                            <div
                              style={{
                                width: "100%",
                                height: 7,
                                background: "var(--border)",
                                borderRadius: 4,
                                position: "relative",
                                overflow: "hidden"
                              }}
                              title={`Min: ${p.min_duration_seconds}s | Avg: ${p.avg_duration_seconds}s | Max: ${p.max_duration_seconds}s`}
                            >
                              <div
                                style={{
                                  position: "absolute",
                                  left: `${minPct}%`,
                                  width: `${Math.max(4, maxPct - minPct)}%`,
                                  height: "100%",
                                  background: "var(--border)",
                                  borderRadius: 4
                                }}
                              />
                              <div
                                style={{
                                  position: "absolute",
                                  left: `${Math.max(0, avgPct - 1)}%`,
                                  width: 3,
                                  height: "100%",
                                  background: "var(--primary)",
                                  borderRadius: 2
                                }}
                              />
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "var(--muted)" }}>
                              <span>{p.min_duration_seconds.toFixed(0)}s</span>
                              <span style={{ color: "var(--primary)", fontWeight: 700 }}>{p.avg_duration_seconds.toFixed(1)}s</span>
                              <span>{p.max_duration_seconds.toFixed(0)}s</span>
                            </div>
                          </div>
                        ) : (
                          <span style={{ color: "var(--border)", fontSize: 11 }}>Chưa có bài thu</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        <div className="table-footer"><span>Hiển thị {Math.min(visibleCount, filteredPrompts.length)} / {filteredPrompts.length} câu hỏi</span>{visibleCount < filteredPrompts.length && <button className="ui-button" onClick={() => setVisibleCount(n => n + 20)}>Tải thêm</button>}</div>
      </section>
    </div>
  );
}

const kpiCardStyle: React.CSSProperties = {
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

const selectStyle: React.CSSProperties = {
  padding: "8px 12px",
  fontSize: 13,
  borderRadius: 6,
  border: "1px solid var(--border)",
  outline: "none",
  background: "var(--surface)"
};

const searchInputStyle: React.CSSProperties = {
  padding: "8px 14px",
  fontSize: 13,
  borderRadius: 6,
  border: "1px solid var(--border)",
  outline: "none",
  minWidth: 200
};
