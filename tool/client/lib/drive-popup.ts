export interface PopupHost {
  open: (url?: string, target?: string, features?: string) => {
    closed: boolean;
    opener: unknown;
    location?: { replace: (url: string) => void };
    close: () => void;
  } | null;
  setInterval: (handler: () => void, timeout: number) => any;
  clearInterval: (id: any) => void;
}

export interface DrivePopupFlow {
  navigate: (url: string) => void;
  cancel: () => void;
}

export function openDrivePopup(host: PopupHost, onFinished: () => void): DrivePopupFlow {
  const width = 600;
  const height = 700;
  const features = `width=${width},height=${height},menubar=no,toolbar=no,location=no,status=no,resizable=yes,scrollbars=yes`;
  const popup = host.open("about:blank", "liemwhisper_google_oauth", features);
  if (!popup) {
    throw new Error("Trình duyệt đã chặn cửa sổ bật lên (popup). Vui lòng cấp quyền mở popup để kết nối Google Drive.");
  }
  try {
    popup.opener = null;
  } catch {
    // Cross-origin or restricted window environment
  }

  let timer: unknown = null;
  let finished = false;

  const cleanup = () => {
    if (timer !== null) {
      host.clearInterval(timer);
      timer = null;
    }
  };

  timer = host.setInterval(() => {
    try {
      if (popup.closed) {
        cleanup();
        if (!finished) {
          finished = true;
          onFinished();
        }
      }
    } catch {
      // In case checking popup.closed throws during cross-origin navigation
    }
  }, 600);

  return {
    navigate: (url: string) => {
      try {
        if (popup.location && typeof popup.location.replace === "function") {
          popup.location.replace(url);
        } else {
          popup.close();
          throw new Error("Không thể điều hướng cửa sổ kết nối Google Drive.");
        }
      } catch (err) {
        cleanup();
        throw err;
      }
    },
    cancel: () => {
      finished = true;
      cleanup();
      try {
        if (!popup.closed) {
          popup.close();
        }
      } catch {
        // ignore close error
      }
    }
  };
}
