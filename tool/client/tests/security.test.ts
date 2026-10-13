import test from "node:test";
import assert from "node:assert";
import {
  validateNoSecretInUrl,
  sanitizeApiError,
  sanitizeNotice,
  maskSecretToken,
  getAdminSession,
  saveAdminSession,
  clearAdminSession
} from "../lib/security.ts";

test("validateNoSecretInUrl rejects URLs with secret query parameters", () => {
  assert.strictEqual(validateNoSecretInUrl("/api/v1/admin/export/archive.zip?key=admin123").valid, false);
  assert.strictEqual(validateNoSecretInUrl("/api/v1/recordings/123/audio?token=secretTok").valid, false);
  assert.strictEqual(validateNoSecretInUrl("http://localhost:8000/api/v1/tasks?x-admin-key=secret").valid, false);
  assert.strictEqual(validateNoSecretInUrl("/api/v1/admin/export/manifest.json").valid, true);
  assert.strictEqual(validateNoSecretInUrl("/api/v1/courses?course_id=c1").valid, true);
});

test("sanitizeApiError scrubs token and internal secret leaks", () => {
  const errWithKey = new Error("Failed at /api/v1/auth?key=supersecret_key_123: 403 Forbidden");
  const cleaned = sanitizeApiError(errWithKey);
  assert.ok(!cleaned.includes("supersecret_key_123"));
  assert.ok(cleaned.length > 0);

  const rawTraceback = new Error("Traceback: /app/main.py sqlite3.OperationalError table locked at token_hash=abcdef1234567890");
  const cleanedTrace = sanitizeApiError(rawTraceback);
  assert.ok(!cleanedTrace.includes("abcdef1234567890"));
  assert.ok(cleanedTrace.includes("Lỗi máy chủ") || cleanedTrace.includes("yêu cầu"));
});

test("sanitizeNotice prevents echoing secret participant token or admin key", () => {
  const secret = "tok_secret_99887766";
  const notice = sanitizeNotice(`Đăng nhập thành công với mã ${secret}`, [secret]);
  assert.ok(!notice.includes(secret));
  assert.ok(notice.includes("Đăng nhập thành công"));
});

test("maskSecretToken only reveals secret when explicit reveal is true", () => {
  const secret = "secret_participant_token_abc";
  assert.strictEqual(maskSecretToken(secret, false), "••••••••••••••••");
  assert.strictEqual(maskSecretToken(secret, true), secret);
});

test("admin session helpers manage sessionStorage correctly", () => {
  const store = new Map<string, string>();
  (globalThis as any).window = {
    sessionStorage: {
      getItem: (k: string) => store.get(k) ?? null,
      setItem: (k: string, v: string) => { store.set(k, v); },
      removeItem: (k: string) => { store.delete(k); }
    }
  };

  saveAdminSession("admin_session_token_123");
  assert.strictEqual(getAdminSession(), "admin_session_token_123");

  clearAdminSession();
  assert.strictEqual(getAdminSession(), null);

  delete (globalThis as any).window;
});
