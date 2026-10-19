"use client";

import React, { useEffect, useRef, useState } from "react";
import { sanitizeApiError } from "../lib/security";

interface AuthenticatedAudioPlayerProps {
  apiBase: string;
  audioPath: string;
  authHeader: { name: string; value: string };
  style?: React.CSSProperties;
}

export function AuthenticatedAudioPlayer({
  apiBase,
  audioPath,
  authHeader,
  style
}: AuthenticatedAudioPlayerProps) {
  const [objectUrl, setObjectUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const currentUrlRef = useRef<string | null>(null);

  useEffect(() => {
    let isCancelled = false;

    // Revoke previous object URL
    if (currentUrlRef.current) {
      URL.revokeObjectURL(currentUrlRef.current);
      currentUrlRef.current = null;
    }
    setObjectUrl(null);
    setError(null);

    if (!audioPath || !authHeader.value) {
      return;
    }

    setLoading(true);

    const fullUrl = `${apiBase}${audioPath}`;
    fetch(fullUrl, {
      method: "GET",
      headers: {
        [authHeader.name]: authHeader.value
      }
    })
      .then(async (res) => {
        if (!res.ok) {
          let msg = `Không thể tải tệp âm thanh (Mã phản hồi ${res.status})`;
          try {
            const data = await res.json();
            if (data?.detail) {
              msg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
            }
          } catch {
            // Not json
          }
          throw new Error(msg);
        }
        return res.blob();
      })
      .then((blob) => {
        if (isCancelled) return;
        const url = URL.createObjectURL(blob);
        currentUrlRef.current = url;
        setObjectUrl(url);
        setLoading(false);
      })
      .catch((err) => {
        if (isCancelled) return;
        setError(sanitizeApiError(err));
        setLoading(false);
      });

    return () => {
      isCancelled = true;
      if (currentUrlRef.current) {
        URL.revokeObjectURL(currentUrlRef.current);
        currentUrlRef.current = null;
      }
    };
  }, [apiBase, audioPath, authHeader.name, authHeader.value]);

  if (loading) {
    return (
      <div
        style={{
          fontSize: 13,
          color: "var(--muted)",
          padding: "8px 12px",
          background: "var(--subtle)",
          borderRadius: 6,
          ...style
        }}
      >
        Đang tải âm thanh bảo mật...
      </div>
    );
  }

  if (error) {
    return (
      <div
        style={{
          fontSize: 12,
          color: "var(--danger)",
          padding: "6px 10px",
          background: "var(--danger-bg)",
          border: "1px solid var(--danger-bg)",
          borderRadius: 6,
          ...style
        }}
      >
        Lỗi phát âm thanh: {error}
      </div>
    );
  }

  if (!objectUrl) {
    return (
      <div style={{ fontSize: 13, color: "var(--muted)", ...style }}>
        Không có dữ liệu âm thanh
      </div>
    );
  }

  return (
    <audio
      controls
      src={objectUrl}
      style={{
        width: "100%",
        height: 36,
        ...style
      }}
    />
  );
}
