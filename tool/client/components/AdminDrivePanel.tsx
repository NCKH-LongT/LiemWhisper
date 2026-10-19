"use client";

import React, { useState, useEffect } from "react";
import {
  DriveStatusResponse,
  formatDriveStatusText,
  buildDriveConnectRequest,
  buildDriveStatusRequest,
  buildDriveSyncNowRequest
} from "../lib/drive";
import { openDrivePopup, DrivePopupFlow } from "../lib/drive-popup";
import { sanitizeApiError } from "../lib/security";

interface AdminDrivePanelProps {
  apiBase: string;
  adminToken: string;
  driveStatus: DriveStatusResponse | null;
  onStatusUpdated: (status: DriveStatusResponse) => void;
}

function CloudIcon({ size = 16 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17.5 19H9a7 7 0 1 1 6.71-9h1.79a4.5 4.5 0 1 1 0 9Z" />
    </svg>
  );
}

function RefreshIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
      <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
      <path d="M16 21h5v-5" />
    </svg>
  );
}

function ExternalLinkIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
      <polyline points="15 3 21 3 21 9" />
      <line x1="10" y1="14" x2="21" y2="3" />
    </svg>
  );
}

export function AdminDrivePanel({
  apiBase,
  adminToken,
  driveStatus,
  onStatusUpdated
}: AdminDrivePanelProps) {
  const [loading, setLoading] = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const [cleaning, setCleaning] = useState(false);
  const [syncNotice, setSyncNotice] = useState<string | null>(null);
  const [cleanNotice, setCleanNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const statusText = formatDriveStatusText(driveStatus);

  async function handleCleanupDuplicates() {
    if (!adminToken) return;
    const confirmed = window.confirm(
      "Hệ thống sẽ quét Google Drive và CSDL để:\n" +
      "1. Gộp các thư mục trùng lặp của cùng một sinh viên thành 1 thư mục duy nhất.\n" +
      "2. Xóa các bản sao audio cũ/thừa, chỉ giữ lại đúng 1 bản thu âm hoàn chỉnh nhất cho mỗi câu.\n" +
      "3. Xóa các thư mục rỗng và cập nhật lại danh sách mã file.\n\n" +
      "Bạn có chắc chắn muốn tiến hành dọn dẹp?"
    );
    if (!confirmed) return;

    setCleaning(true);
    setError(null);
    setCleanNotice(null);
    setSyncNotice(null);
    try {
      const res = await fetch(`${apiBase}/api/v1/admin/drive/cleanup-duplicates`, {
        method: "POST",
        headers: {
          "x-admin-key": adminToken
        }
      });
      if (!res.ok) {
        let msg = `Dọn dẹp thất bại (${res.status})`;
        try {
          const body = await res.json();
          if (body?.detail) msg = body.detail;
        } catch {}
        throw new Error(msg);
      }
      const data = await res.json();
      setCleanNotice(data.message || "Đã dọn dẹp bản sao trùng lặp thành công!");
      refreshStatus();
    } catch (err) {
      setError(sanitizeApiError(err));
    } finally {
      setCleaning(false);
    }
  }

  async function handleSyncNow() {
    if (!adminToken) return;
    setSyncing(true);
    setError(null);
    setSyncNotice(null);
    try {
      const { url, init } = buildDriveSyncNowRequest(adminToken);
      const res = await fetch(`${apiBase}${url}`, init);
      if (!res.ok) {
        throw new Error(`Đồng bộ thất bại (${res.status})`);
      }
      const data = await res.json();
      setSyncNotice(data.message || `Đã đồng bộ ${data.processed ?? 0} bản ghi lên Google Drive.`);
      refreshStatus();
    } catch (err) {
      setError(sanitizeApiError(err));
    } finally {
      setSyncing(false);
    }
  }

  useEffect(() => {
    function handleMessage(event: MessageEvent) {
      if (event.data?.type === "DRIVE_CONNECTED") {
        setConnecting(false);
        refreshStatus();
      }
    }
    window.addEventListener("message", handleMessage);
    return () => window.removeEventListener("message", handleMessage);
  }, [adminToken]);

  async function refreshStatus() {
    if (!adminToken) return;
    setLoading(true);
    setError(null);
    try {
      const { url, init } = buildDriveStatusRequest(adminToken);
      const res = await fetch(`${apiBase}${url}`, init);
      if (!res.ok) {
        throw new Error(`Kiểm tra trạng thái thất bại (${res.status})`);
      }
      const data: DriveStatusResponse = await res.json();
      onStatusUpdated(data);
    } catch (err) {
      setError(sanitizeApiError(err));
    } finally {
      setLoading(false);
    }
  }

  async function handleConnect() {
    if (!adminToken) return;
    setConnecting(true);
    setError(null);
    let popupFlow: DrivePopupFlow | null = null;
    try {
      if (typeof window !== "undefined") {
        try {
          popupFlow = openDrivePopup(window, () => {
            setConnecting(false);
            refreshStatus();
          });
        } catch {
          // If popup is blocked by browser, proceed and fall back to top-level navigation
        }
      }

      const { url, init } = buildDriveConnectRequest(adminToken);
      const res = await fetch(`${apiBase}${url}`, init);
      if (!res.ok) {
        let msg = `Không thể tạo phiên xác thực OAuth (${res.status})`;
        try {
          const body = await res.json();
          if (body?.detail) msg = body.detail;
        } catch {
          // not json
        }
        if (popupFlow) popupFlow.cancel();
        throw new Error(msg);
      }
      const data = await res.json();
      if (!data?.authorization_url) {
        if (popupFlow) popupFlow.cancel();
        throw new Error("Máy chủ không trả về URL xác thực Google.");
      }

      if (popupFlow) {
        popupFlow.navigate(data.authorization_url);
      } else {
        // Fallback if popup was blocked: navigate current tab
        window.location.assign(data.authorization_url);
      }
    } catch (err) {
      if (popupFlow) popupFlow.cancel();
      setError(sanitizeApiError(err));
      setConnecting(false);
    }
  }

  return (
    <div
      style={{
        background: "#ffffff",
        border: "1px solid #e4e4e7",
        borderRadius: 12,
        padding: "20px 24px",
        marginBottom: 20
      }}
    >
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "flex-start",
          flexWrap: "wrap",
          gap: 16
        }}
      >
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
            <CloudIcon size={18} />
            <h3 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: "#09090b" }}>
              Lưu trữ đám mây Google Drive (Dual SQL + Drive)
            </h3>
            <span
              style={{
                fontSize: 11,
                padding: "2px 8px",
                borderRadius: 4,
                fontWeight: 600,
                textTransform: "uppercase",
                background:
                  statusText.state === "connected"
                    ? "#dcfce7"
                    : statusText.state === "configured"
                    ? "#fef3c7"
                    : "#f4f4f5",
                color:
                  statusText.state === "connected"
                    ? "#166534"
                    : statusText.state === "configured"
                    ? "#92400e"
                    : "#71717a"
              }}
            >
              {statusText.state === "connected"
                ? "Đã liên kết"
                : statusText.state === "configured"
                ? "Sẵn sàng kết nối"
                : "Chưa cấu hình"}
            </span>
          </div>
          <p style={{ fontSize: 13, color: "#52525b", margin: "4px 0 0", lineHeight: 1.5 }}>
            {statusText.subtitle}
          </p>
          {driveStatus?.folder_id && (
            <div style={{ marginTop: 8, fontSize: 12, color: "#71717a" }}>
              Mã thư mục đích:{" "}
              <code
                style={{
                  fontFamily: "ui-monospace, monospace",
                  background: "#f1f5f9",
                  padding: "2px 6px",
                  borderRadius: 4,
                  border: "1px solid #cbd5e1",
                  color: "#0f172a"
                }}
              >
                {driveStatus.folder_id}
              </code>
            </div>
          )}
          {driveStatus?.connected && (
            <div style={{ marginTop: 10, display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
              <div style={{ display: "inline-flex", gap: 6, fontSize: 12, background: "#f8fafc", padding: "4px 10px", borderRadius: 6, border: "1px solid #e2e8f0", alignItems: "center" }}>
                <span>Đã lưu Drive:</span>
                <strong style={{ color: "#16a34a" }}>{driveStatus.synced_count ?? 0}</strong>
                <span style={{ color: "#94a3b8" }}>/</span>
                <span>Tổng:</span>
                <strong>{driveStatus.total_recordings ?? 0} bản ghi</strong>
                {(driveStatus.pending_count ?? 0) > 0 && (
                  <span style={{ color: "#d97706", fontWeight: 600, marginLeft: 4 }}>
                    ({driveStatus.pending_count} đang chờ đẩy)
                  </span>
                )}
                {(driveStatus.failed_count ?? 0) > 0 && (
                  <span style={{ color: "#dc2626", fontWeight: 600, marginLeft: 4 }}>
                    ({driveStatus.failed_count} lỗi)
                  </span>
                )}
              </div>
            </div>
          )}
        </div>

        <div style={{ display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          {driveStatus?.connected && (
            <>
              <button
                onClick={handleSyncNow}
                disabled={syncing || loading || cleaning}
                style={{
                  padding: "8px 14px",
                  background: "#16a34a",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: 8,
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  boxShadow: "0 2px 4px rgba(22, 163, 74, 0.2)"
                }}
              >
                <RefreshIcon size={13} />
                <span>{syncing ? "Đang đẩy lên Drive..." : "Đồng bộ Drive ngay"}</span>
              </button>

              <button
                onClick={handleCleanupDuplicates}
                disabled={cleaning || syncing || loading}
                title="Quét gộp folder học viên bị trùng và xóa các bản thu thừa"
                style={{
                  padding: "8px 14px",
                  background: "#0284c7",
                  color: "#ffffff",
                  border: "none",
                  borderRadius: 8,
                  fontWeight: 600,
                  fontSize: 13,
                  cursor: "pointer",
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 6,
                  boxShadow: "0 2px 4px rgba(2, 132, 199, 0.2)"
                }}
              >
                <span>{cleaning ? "Đang dọn dẹp..." : "🧹 Dọn dẹp bản sao trùng lặp"}</span>
              </button>
            </>
          )}

          <button
            onClick={refreshStatus}
            disabled={loading || connecting || syncing || cleaning}
            style={{
              padding: "8px 14px",
              background: "#ffffff",
              color: "#27272a",
              border: "1px solid #d4d4d8",
              borderRadius: 8,
              fontWeight: 500,
              fontSize: 13,
              cursor: "pointer",
              display: "inline-flex",
              alignItems: "center",
              gap: 6
            }}
          >
            <RefreshIcon size={13} />
            <span>{loading ? "Đang kiểm tra..." : "Kiểm tra kết nối"}</span>
          </button>

          <button
            onClick={handleConnect}
            disabled={connecting || loading || syncing || cleaning || Boolean(driveStatus && !driveStatus.configured)}
            title={driveStatus && !driveStatus.configured ? "Chưa cấu hình Client ID / Secret trên máy chủ" : ""}
            style={{
              padding: "8px 14px",
              background: driveStatus?.connected ? "#27272a" : "#09090b",
              color: "#ffffff",
              border: "none",
              borderRadius: 8,
              fontWeight: 600,
              fontSize: 13,
              cursor: driveStatus && !driveStatus.configured ? "not-allowed" : "pointer",
              opacity: driveStatus && !driveStatus.configured ? 0.6 : 1,
              display: "inline-flex",
              alignItems: "center",
              gap: 6
            }}
          >
            <ExternalLinkIcon size={13} />
            <span>
              {connecting
                ? "Đang chuyển tiếp..."
                : driveStatus?.connected
                ? "Liên kết lại Google Drive"
                : "Liên kết Google Drive"}
            </span>
          </button>
        </div>
      </div>

      {syncNotice && (
        <div
          style={{
            marginTop: 12,
            padding: "8px 12px",
            background: "#f0fdf4",
            border: "1px solid #bbf7d0",
            color: "#166534",
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500
          }}
        >
          ✓ {syncNotice}
        </div>
      )}

      {cleanNotice && (
        <div
          style={{
            marginTop: 12,
            padding: "8px 12px",
            background: "#f0f9ff",
            border: "1px solid #bae6fd",
            color: "#0369a1",
            borderRadius: 6,
            fontSize: 12,
            fontWeight: 500
          }}
        >
          ✓ {cleanNotice}
        </div>
      )}

      {error && (
        <div
          style={{
            marginTop: 12,
            padding: "8px 12px",
            background: "#fef2f2",
            border: "1px solid #fee2e2",
            color: "#991b1b",
            borderRadius: 6,
            fontSize: 12
          }}
        >
          {error}
        </div>
      )}
    </div>
  );
}
