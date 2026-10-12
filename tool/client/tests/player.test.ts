import test from "node:test";
import assert from "node:assert";
import { validateNoSecretInUrl } from "../lib/security.ts";

test("authenticated audio player path never carries secret query strings", () => {
  const safePath = "/api/v1/admin/recordings/rec_12345/audio";
  const validation = validateNoSecretInUrl(safePath);
  assert.strictEqual(validation.valid, true);

  const unsafePath = "/api/v1/admin/recordings/rec_12345/audio?key=admin_key_999";
  const unsafeValidation = validateNoSecretInUrl(unsafePath);
  assert.strictEqual(unsafeValidation.valid, false);
});
