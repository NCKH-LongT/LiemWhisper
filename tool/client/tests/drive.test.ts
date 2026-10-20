import test from "node:test";
import assert from "node:assert";
import {
  formatDriveStatusText,
  buildDriveConnectRequest,
  buildDriveStatusRequest,
  buildDriveCleanupDuplicatesRequest
} from "../lib/drive.ts";

test("formatDriveStatusText handles all drive connection states with neutral typography", () => {
  const connected = formatDriveStatusText({
    connected: true,
    folder_id: "folder_abc_123",
    configured: true
  });
  assert.strictEqual(connected.state, "connected");
  assert.ok(connected.title.includes("Đã kết nối"));
  assert.ok(connected.subtitle.includes("folder_abc_123"));

  const configuredOnly = formatDriveStatusText({
    connected: false,
    folder_id: null,
    configured: true
  });
  assert.strictEqual(configuredOnly.state, "configured");
  assert.ok(configuredOnly.title.includes("Chưa liên kết"));
  assert.ok(configuredOnly.subtitle.includes("drive.file"));

  const unconfigured = formatDriveStatusText({
    connected: false,
    folder_id: null,
    configured: false
  });
  assert.strictEqual(unconfigured.state, "unconfigured");
  assert.ok(unconfigured.title.includes("Chưa cấu hình"));
});

test("buildDriveConnectRequest mandates x-admin-key header and no cross-site cookie dependency", () => {
  const req = buildDriveConnectRequest("session_token_xyz");
  assert.strictEqual(req.url, "/api/v1/admin/drive/connect");
  assert.strictEqual(req.init.method, "POST");
  assert.strictEqual(req.init.credentials, "omit");
  const headers = req.init.headers as Record<string, string>;
  assert.strictEqual(headers["x-admin-key"], "session_token_xyz");
  // Ensure no query string with key
  assert.ok(!req.url.includes("key="));
});

test("buildDriveStatusRequest uses header and avoids query credentials", () => {
  const req = buildDriveStatusRequest("session_token_xyz");
  assert.strictEqual(req.url, "/api/v1/admin/drive/status?counts=1");
  assert.strictEqual(req.init.method, "GET");
  const headers = req.init.headers as Record<string, string>;
  assert.strictEqual(headers["x-admin-key"], "session_token_xyz");
  assert.ok(!req.url.includes("key="));
});

test("buildDriveCleanupDuplicatesRequest uses header and correct POST endpoint", () => {
  const req = buildDriveCleanupDuplicatesRequest("session_token_xyz");
  assert.strictEqual(req.url, "/api/v1/admin/drive/cleanup-duplicates");
  assert.strictEqual(req.init.method, "POST");
  const headers = req.init.headers as Record<string, string>;
  assert.strictEqual(headers["x-admin-key"], "session_token_xyz");
  assert.ok(!req.url.includes("key="));
});
