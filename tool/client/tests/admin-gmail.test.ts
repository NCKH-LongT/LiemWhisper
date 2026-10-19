import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

test("admin interface includes Cấp quyền Admin (Gmail) tab and admin management", () => {
  // 1. Ensure adminSubTab includes "admins"
  assert.match(
    page,
    /"admins"/,
    "adminSubTab must support 'admins' state"
  );

  // 2. Ensure tab button exists with correct label
  assert.match(
    page,
    /Cấp quyền Admin \(Gmail\)/,
    "Navigation must include 'Cấp quyền Admin (Gmail)'"
  );

  // 3. Ensure API handlers are defined
  assert.match(page, /loadAdminAdmins/);
  assert.match(page, /handleAddAdmin/);
  assert.match(page, /handleRemoveAdmin/);
  assert.match(page, /\/api\/v1\/admin\/admins/);
  assert.match(page, /\/api\/v1\/admin\/participants/);

  // 4. Ensure admin email input exists
  assert.match(page, /newAdminEmailInput/);
  assert.match(page, /placeholder="Nhập địa chỉ Gmail/);

  // 5. Ensure Google auth handler detects is_admin and stores session
  assert.match(page, /if \(res\.is_admin && res\.admin_token\)/);
  assert.match(page, /setIsGoogleAdmin\(true\)/);
});
