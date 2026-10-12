export interface DriveStatusResponse {
  connected: boolean;
  folder_id: string | null;
  configured: boolean;
}

export type DriveConnectionState = "connected" | "configured" | "unconfigured" | "unknown";

export interface DriveStatusText {
  title: string;
  subtitle: string;
  state: DriveConnectionState;
}

export function formatDriveStatusText(status: DriveStatusResponse | null): DriveStatusText {
  if (!status) {
    return {
      title: "Đang kiểm tra kết nối Google Drive",
      subtitle: "Vui lòng đợi trong giây lát...",
      state: "unknown"
    };
  }

  if (status.connected) {
    return {
      title: "Đã kết nối Google Drive",
      subtitle: status.folder_id
        ? `Thư mục lưu trữ: ${status.folder_id}`
        : "Đã liên kết OAuth thành công với Google Drive.",
      state: "connected"
    };
  }

  if (status.configured) {
    return {
      title: "Chưa liên kết tài khoản Google Drive",
      subtitle: "Máy chủ đã sẵn sàng với phạm vi drive.file. Nhấn để ủy quyền.",
      state: "configured"
    };
  }

  return {
    title: "Chưa cấu hình Google Drive",
    subtitle: "Máy chủ chưa cài đặt OAuth Client ID hoặc khóa mã hóa.",
    state: "unconfigured"
  };
}

export function buildDriveConnectRequest(adminToken: string): { url: string; init: RequestInit } {
  return {
    url: "/api/v1/admin/drive/connect",
    init: {
      method: "POST",
      headers: {
        "x-admin-key": adminToken
      },
      credentials: "include"
    }
  };
}

export function buildDriveStatusRequest(adminToken: string): { url: string; init: RequestInit } {
  return {
    url: "/api/v1/admin/drive/status",
    init: {
      method: "GET",
      headers: {
        "x-admin-key": adminToken
      }
    }
  };
}
