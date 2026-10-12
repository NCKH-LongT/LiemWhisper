const SENSITIVE_QUERY_KEYS = new Set([
  "key",
  "admin_key",
  "x-admin-key",
  "token",
  "participant_token",
  "secret",
  "password"
]);

export function validateNoSecretInUrl(url: string): { valid: boolean; forbiddenParam?: string } {
  try {
    const parsed = new URL(url, "http://localhost");
    for (const [key] of parsed.searchParams.entries()) {
      const lower = key.toLowerCase();
      if (SENSITIVE_QUERY_KEYS.has(lower) || lower.includes("key") || lower.includes("token") || lower.includes("secret")) {
        return { valid: false, forbiddenParam: key };
      }
    }
    return { valid: true };
  } catch {
    // If not a full URL, fallback check
    for (const forbidden of SENSITIVE_QUERY_KEYS) {
      if (url.includes(`?${forbidden}=`) || url.includes(`&${forbidden}=`)) {
        return { valid: false, forbiddenParam: forbidden };
      }
    }
    return { valid: true };
  }
}

export function sanitizeApiError(error: unknown): string {
  if (!error) return "Đã xảy ra lỗi không xác định.";
  const raw = error instanceof Error ? error.message : String(error);

  // If it's a raw python traceback or operational error, conceal system internals
  if (raw.includes("Traceback") || raw.includes("sqlite3.") || raw.includes("OperationalError")) {
    return "Lỗi máy chủ trong quá trình xử lý yêu cầu. Vui lòng thử lại sau.";
  }

  // Scrub any sensitive query keys or tokens from string
  let sanitized = raw
    .replace(/(?:key|token|x-admin-key|secret)=([a-zA-Z0-9_\-]+)/gi, "$1=[REDACTED]")
    .replace(/token_hash=[a-zA-Z0-9_\-]+/gi, "token_hash=[REDACTED]");

  // Strip trailing system URLs or paths
  sanitized = sanitized.replace(/at\s+\/[^\s]+/g, "");

  return sanitized.trim() || "Đã xảy ra lỗi khi kết nối máy chủ.";
}

export function sanitizeNotice(message: string, secretsToHide: string[] = []): string {
  let result = message;
  for (const secret of secretsToHide) {
    if (secret && secret.trim().length > 0) {
      result = result.split(secret).join("[mã bảo mật]");
    }
  }
  return result;
}

export function maskSecretToken(token: string, reveal: boolean = false): string {
  if (!token) return "";
  if (reveal) return token;
  return "••••••••••••••••";
}

/**
 * Remove legacy unencrypted admin key storage from localStorage.
 * Admin tokens must reside strictly in React memory to prevent persistent exposure.
 */
export function cleanLegacyAdminStorage(): void {
  if (typeof window === "undefined" || !window.localStorage) return;
  try {
    window.localStorage.removeItem("liemwhisper_admin_key");
    if (window.localStorage.getItem("liemwhisper_role") === "admin") {
      window.localStorage.removeItem("liemwhisper_role");
    }
  } catch {
    // localStorage may be disabled/restricted
  }
}
