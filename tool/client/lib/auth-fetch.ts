import { sanitizeApiError } from "./security.ts";

export interface AuthHeader {
  name: string;
  value: string;
}

export async function fetchAuthenticatedAudioBlob(
  audioUrl: string,
  authHeader: AuthHeader,
  fetchFn: typeof fetch = fetch,
  createObjectURLFn: (blob: Blob) => string = (b) => URL.createObjectURL(b)
): Promise<{ blob: Blob; objectUrl: string }> {
  const headers: Record<string, string> = {};
  if (authHeader && authHeader.name && authHeader.value) {
    headers[authHeader.name] = authHeader.value;
  }

  let res: Response;
  try {
    res = await fetchFn(audioUrl, {
      method: "GET",
      headers
    });
  } catch (err) {
    throw new Error(sanitizeApiError(err));
  }

  if (!res.ok) {
    let detail = `Lỗi tải âm thanh (${res.status})`;
    try {
      const data = await res.json();
      if (data && data.detail) {
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // not json
    }
    throw new Error(sanitizeApiError(detail));
  }

  const blob = await res.blob();
  const objectUrl = createObjectURLFn(blob);
  return { blob, objectUrl };
}

export function triggerBlobDownload(
  blob: Blob,
  filename: string,
  doc: Document = typeof document !== "undefined" ? document : (null as any),
  urlApi: typeof URL = typeof URL !== "undefined" ? URL : (null as any)
): void {
  if (!doc || !urlApi) return;
  const objectUrl = urlApi.createObjectURL(blob);
  try {
    const a = doc.createElement("a");
    a.href = objectUrl;
    a.download = filename;
    if (a.style) {
      a.style.display = "none";
    }
    doc.body.appendChild(a);
    a.click();
    doc.body.removeChild(a);
  } finally {
    // Revoke after triggering download
    urlApi.revokeObjectURL(objectUrl);
  }
}

export async function downloadAuthenticatedExport(
  apiUrl: string,
  endpoint: string,
  filename: string,
  adminToken: string,
  fetchFn: typeof fetch = fetch,
  doc: Document = typeof document !== "undefined" ? document : (null as any),
  urlApi: typeof URL = typeof URL !== "undefined" ? URL : (null as any)
): Promise<void> {
  const fullUrl = `${apiUrl}${endpoint}`;
  let res: Response;
  try {
    res = await fetchFn(fullUrl, {
      method: "GET",
      headers: {
        "x-admin-key": adminToken
      }
    });
  } catch (err) {
    throw new Error(sanitizeApiError(err));
  }

  if (!res.ok) {
    let detail = `Lỗi tải tệp xuất (${res.status})`;
    try {
      const data = await res.json();
      if (data && data.detail) {
        detail = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
      }
    } catch {
      // not json
    }
    throw new Error(sanitizeApiError(detail));
  }

  const blob = await res.blob();
  triggerBlobDownload(blob, filename, doc, urlApi);
}
