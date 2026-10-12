import test from "node:test";
import assert from "node:assert";
import { getDriveSyncStatusInfo, isBothSaved } from "../lib/sync.ts";

test("isBothSaved returns true ONLY when drive_sync_status is synced", () => {
  assert.strictEqual(isBothSaved("synced"), true);
  assert.strictEqual(isBothSaved("pending"), false);
  assert.strictEqual(isBothSaved("error"), false);
  assert.strictEqual(isBothSaved(null), false);
  assert.strictEqual(isBothSaved(undefined), false);
  assert.strictEqual(isBothSaved(""), false);
});

test("getDriveSyncStatusInfo handles synced status without premature claims", () => {
  const syncedInfo = getDriveSyncStatusInfo("synced");
  assert.strictEqual(syncedInfo.isSynced, true);
  assert.strictEqual(syncedInfo.badgeStyle, "synced");
  assert.ok(syncedInfo.label.includes("Google Drive"));
  assert.ok(syncedInfo.description.includes("cơ sở dữ liệu và Google Drive"));
});

test("getDriveSyncStatusInfo handles pending status explicitly without claiming both saved", () => {
  const pendingInfo = getDriveSyncStatusInfo("pending", "Đang chuyển tiếp tệp...");
  assert.strictEqual(pendingInfo.isSynced, false);
  assert.strictEqual(pendingInfo.badgeStyle, "pending");
  assert.ok(pendingInfo.description.includes("chờ đồng bộ Google Drive") || pendingInfo.description.includes("đang đồng bộ"));
  assert.ok(!pendingInfo.description.includes("Đã lưu cả hai"));
});

test("getDriveSyncStatusInfo handles error status with details and retry hint", () => {
  const errorInfo = getDriveSyncStatusInfo("error", "Drive quota exceeded");
  assert.strictEqual(errorInfo.isSynced, false);
  assert.strictEqual(errorInfo.badgeStyle, "error");
  assert.ok(errorInfo.description.includes("Drive quota exceeded"));
});
