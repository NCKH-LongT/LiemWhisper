import test from "node:test";
import assert from "node:assert";
import {
  fetchAuthenticatedAudioBlob,
  triggerBlobDownload
} from "../lib/auth-fetch.ts";

test("fetchAuthenticatedAudioBlob sends headers and returns blob with object url", async () => {
  let capturedUrl = "";
  let capturedHeaders: Record<string, string> = {};

  const fakeFetch = async (url: string, init?: RequestInit) => {
    capturedUrl = url;
    capturedHeaders = (init?.headers as Record<string, string>) || {};
    return {
      ok: true,
      blob: async () => new Blob(["fake-audio-bytes"], { type: "audio/webm" })
    } as any;
  };

  const fakeCreateObjectURL = (b: Blob) => "blob:http://localhost/test-uuid";

  const res = await fetchAuthenticatedAudioBlob(
    "http://localhost:8000/api/v1/admin/recordings/rec123/audio",
    { name: "x-admin-key", value: "admin_token_xyz" },
    fakeFetch,
    fakeCreateObjectURL
  );

  assert.strictEqual(capturedUrl, "http://localhost:8000/api/v1/admin/recordings/rec123/audio");
  assert.strictEqual(capturedHeaders["x-admin-key"], "admin_token_xyz");
  assert.ok(!capturedUrl.includes("key="));
  assert.strictEqual(res.objectUrl, "blob:http://localhost/test-uuid");
});

test("fetchAuthenticatedAudioBlob throws on non-ok status with sanitized error", async () => {
  const fakeFetch = async () => ({
    ok: false,
    status: 403,
    json: async () => ({ detail: "Admin credential required" })
  } as any);

  await assert.rejects(
    async () => {
      await fetchAuthenticatedAudioBlob(
        "/api/v1/admin/recordings/rec123/audio",
        { name: "x-admin-key", value: "bad_token" },
        fakeFetch,
        () => ""
      );
    },
    /Admin credential required/
  );
});

test("triggerBlobDownload invokes click and revokes object url", () => {
  let clicked = false;
  let revokedUrl = "";

  const fakeBlob = new Blob(["data"], { type: "application/json" });
  const fakeUrl = "blob:http://localhost/download-uuid";

  const fakeDocument = {
    createElement: (tag: string) => ({
      href: "",
      download: "",
      click: () => { clicked = true; }
    }),
    body: {
      appendChild: () => {},
      removeChild: () => {}
    }
  };

  const fakeURL = {
    createObjectURL: () => fakeUrl,
    revokeObjectURL: (url: string) => { revokedUrl = url; }
  };

  triggerBlobDownload(fakeBlob, "manifest.json", fakeDocument as any, fakeURL as any);

  assert.strictEqual(clicked, true);
  assert.strictEqual(revokedUrl, fakeUrl);
});
