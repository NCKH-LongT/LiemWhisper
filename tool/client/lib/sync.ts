export type DriveSyncStatus = "pending" | "synced" | "error" | string | null | undefined;

export interface DriveSyncInfo {
  label: string;
  badgeStyle: "synced" | "pending" | "error" | "local";
  isSynced: boolean;
  description: string;
}

export function isBothSaved(status?: DriveSyncStatus): boolean {
  return status === "synced";
}

export function getDriveSyncStatusInfo(
  status?: DriveSyncStatus,
  message?: string | null
): DriveSyncInfo {
  if (status === "synced") {
    return {
      label: "Đã đồng bộ Google Drive",
      badgeStyle: "synced",
      isSynced: true,
      description: "Đã lưu vào cơ sở dữ liệu và Google Drive."
    };
  }

  if (status === "pending") {
    return {
      label: "Đang đồng bộ Drive",
      badgeStyle: "pending",
      isSynced: false,
      description: message
        ? `Đã lưu máy chủ; đang đồng bộ Google Drive (${message})`
        : "Đã lưu vào máy chủ; đang đồng bộ Google Drive..."
    };
  }

  if (status === "error") {
    return {
      label: "Lỗi đồng bộ Drive",
      badgeStyle: "error",
      isSynced: false,
      description: message
        ? `Lưu máy chủ thành công; lỗi đồng bộ Google Drive: ${message}`
        : "Lưu máy chủ thành công; lỗi khi đồng bộ Google Drive."
    };
  }

  return {
    label: "Đã lưu trên máy chủ",
    badgeStyle: "local",
    isSynced: false,
    description: "Đã lưu vào cơ sở dữ liệu máy chủ."
  };
}
