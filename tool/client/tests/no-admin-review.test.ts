import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

test("admin interface removes review studio tab and auto-approves recordings", () => {
  // 1. Ensure "Kiểm duyệt âm thanh" is not in the navigation buttons
  assert.ok(
    !page.includes("Kiểm duyệt âm thanh"),
    "Admin navigation must not include 'Kiểm duyệt âm thanh' tab"
  );

  // 2. Ensure "Kiểm duyệt bản ghi âm" header is removed
  assert.ok(
    !page.includes("Kiểm duyệt bản ghi âm"),
    "Admin panel must not include audio review section"
  );

  // 3. Ensure adminSubTab no longer contains 'reviews'
  assert.ok(
    !page.includes('"reviews"'),
    "adminSubTab must not include 'reviews' state"
  );

  // 4. Ensure recordings default to approved in client state
  assert.ok(
    page.includes('status: res.status || "approved"'),
    "Recordings must fallback to 'approved'"
  );
});
