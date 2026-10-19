"use client";

import React, { useState, useMemo } from "react";

export interface PromptDurationStat {
  prompt_id: string;
  prompt_text: string;
  course_id: string;
  course_title: string;
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
      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", gap: 12 }}>
        <div style={kpiCardStyle}>
          <div style={{ fontSize: 12, color: "#854d0e", fontWeight: 700, textTransform: "uppercase" }}>
            Tổng thời lượng thu âm
          </div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#a16207", marginTop: 4 }}>
            {formatDuration(totalSec)}
          </div>
          <div style={{ fontSize: 11, color: "#a1a1aa", marginTop: 2 }}>
            Tổng cộng {totalSec.toFixed(1)} giây
          </div>
        </div>

        <div style={kpiCardStyle}>
          <div style={{ fontSize: 12, color: "#1d4ed8", fontWeight: 700, textTransform: "uppercase" }}>
            Thời lượng trung bình / câu
          </div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#2563eb", marginTop: 4 }}>
            {avgSec.toFixed(1)}s
          </div>
          <div style={{ fontSize: 11, color: "#93c5fd", marginTop: 2 }}>
            Tính trên tất cả câu đã thu
          </div>
        </div>

        <div style={kpiCardStyle}>
          <div style={{ fontSize: 12, color: "#166534", fontWeight: 700, textTransform: "uppercase" }}>
            Thời lượng ngắn nhất (Min)
          </div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#16a34a", marginTop: 4 }}>
            {minSec.toFixed(1)}s
          </div>
          <div style={{ fontSize: 11, color: "#86efac", marginTop: 2 }}>
            Bản thu ngắn nhất trong hệ thống
          </div>
        </div>

        <div style={kpiCardStyle}>
          <div style={{ fontSize: 12, color: "#7c2d12", fontWeight: 700, textTransform: "uppercase" }}>
            Thời lượng dài nhất (Max)
          </div>
          <div style={{ fontSize: 24, fontWeight: 700, color: "#ea580c", marginTop: 4 }}>
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
            <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: "#09090b" }}>
              Thống kê Thời lượng Từng Câu Hỏi (Min / Avg / Max)
            </h3>
            <div style={{ fontSize: 12, color: "#71717a", marginTop: 2 }}>
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
          <div style={{ padding: "32px 0", textAlign: "center", color: "#71717a", fontSize: 13, background: "#f8fafc", borderRadius: 8 }}>
            Không tìm thấy câu hỏi nào phù hợp với bộ lọc.
          </div>
        ) : (
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
              <thead>
                <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", textAlign: "left", color: "#475569" }}>
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
                {filteredPrompts.map((p, idx) => {
                  const hasRecs = p.recordings_count > 0;
                  const minPct = Math.min(100, Math.max(0, (p.min_duration_seconds / 45) * 100));
                  const maxPct = Math.min(100, Math.max(0, (p.max_duration_seconds / 45) * 100));
                  const avgPct = Math.min(100, Math.max(0, (p.avg_duration_seconds / 45) * 100));

                  return (
                    <tr
                      key={p.prompt_id}
                      style={{
                        borderBottom: "1px solid #f1f5f9",
                        transition: "background 0.15s"
                      }}
                      onMouseEnter={(e) => (e.currentTarget.style.background = "#f8fafc")}
                      onMouseLeave={(e) => (e.currentTarget.style.background = "transparent")}
                    >
                      <td style={{ padding: "11px 12px", color: "#64748b", fontWeight: 600 }}>
                        #{idx + 1}
                      </td>
                      <td style={{ padding: "11px 14px" }}>
                        <div style={{ fontWeight: 600, color: "#09090b", lineHeight: 1.45 }}>
                          {p.prompt_text}
                        </div>
                      </td>
                      <td style={{ padding: "11px 12px", color: "#64748b", fontSize: 12 }}>
                        {p.course_title}
                      </td>
                      <td style={{ padding: "11px 12px", textAlign: "center" }}>
                        <span
                          style={{
                            display: "inline-block",
                            background: hasRecs ? "#eff6ff" : "#f1f5f9",
                            color: hasRecs ? "#1d4ed8" : "#94a3b8",
                            padding: "2px 8px",
                            borderRadius: 12,
                            fontWeight: 700,
                            fontSize: 12
                          }}
                        >
                          {p.recordings_count} bài
                        </span>
                      </td>
                      <td style={{ padding: "11px 12px", textAlign: "center", color: hasRecs ? "#09090b" : "#94a3b8", fontWeight: 600 }}>
                        {hasRecs ? `${p.total_duration_seconds.toFixed(1)}s` : "-"}
                      </td>
                      <td style={{ padding: "11px 12px", textAlign: "center" }}>
                        {hasRecs ? (
                          <span style={{ fontWeight: 700, color: "#2563eb", background: "#eff6ff", padding: "2px 7px", borderRadius: 4 }}>
                            {p.avg_duration_seconds.toFixed(1)}s
                          </span>
                        ) : (
                          <span style={{ color: "#94a3b8" }}>-</span>
                        )}
                      </td>
                      <td style={{ padding: "11px 12px", textAlign: "center" }}>
                        {hasRecs ? (
                          <span style={{ fontWeight: 600, color: "#166534", background: "#f0fdf4", padding: "2px 6px", borderRadius: 4, fontSize: 12 }}>
                            {p.min_duration_seconds.toFixed(1)}s
                          </span>
                        ) : (
                          <span style={{ color: "#94a3b8" }}>-</span>
                        )}
                      </td>
                      <td style={{ padding: "11px 12px", textAlign: "center" }}>
                        {hasRecs ? (
                          <span style={{ fontWeight: 600, color: "#c2410c", background: "#fff7ed", padding: "2px 6px", borderRadius: 4, fontSize: 12 }}>
                            {p.max_duration_seconds.toFixed(1)}s
                          </span>
                        ) : (
                          <span style={{ color: "#94a3b8" }}>-</span>
                        )}
                      </td>
                      <td style={{ padding: "11px 14px" }}>
                        {hasRecs ? (
                          <div style={{ display: "flex", flexDirection: "column", gap: 3 }}>
                            <div
                              style={{
                                width: "100%",
                                height: 7,
                                background: "#e2e8f0",
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
                                  background: "#93c5fd",
                                  borderRadius: 4
                                }}
                              />
                              <div
                                style={{
                                  position: "absolute",
                                  left: `${Math.max(0, avgPct - 1)}%`,
                                  width: 3,
                                  height: "100%",
                                  background: "#1d4ed8",
                                  borderRadius: 2
                                }}
                              />
                            </div>
                            <div style={{ display: "flex", justifyContent: "space-between", fontSize: 10, color: "#94a3b8" }}>
                              <span>{p.min_duration_seconds.toFixed(0)}s</span>
                              <span style={{ color: "#2563eb", fontWeight: 700 }}>{p.avg_duration_seconds.toFixed(1)}s</span>
                              <span>{p.max_duration_seconds.toFixed(0)}s</span>
                            </div>
                          </div>
                        ) : (
                          <span style={{ color: "#cbd5e1", fontSize: 11 }}>Chưa có bài thu</span>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

const kpiCardStyle: React.CSSProperties = {
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
  minWidth: 200
};
