import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const React = require("react");
const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

// Exercise the actual page and event handlers without adding a DOM dependency.
// Hooks retain state across renders; network/Google SDK are boundary fixtures.
function onboardingHarness() {
  const state: unknown[] = [];
  const effects: Array<() => void> = [];
  const requests: Array<{ path: string; body: Record<string, unknown> }> = [];
  let cursor = 0;
  let callback: (response: { credential: string }) => void;
  const storage = new Map<string, string>();
  const sandbox = {
    exports: {} as { default: () => any },
    process: { env: {} },
    console,
    window: { google: { accounts: { id: {
      initialize: (config: { callback: typeof callback }) => { callback = config.callback; },
      renderButton: () => {}
    } } } },
    document: { getElementById: () => ({ innerHTML: "" }) },
    localStorage: { getItem: (key: string) => storage.get(key), setItem: (key: string, value: string) => storage.set(key, value) },
    fetch: async (url: string, options?: { body?: string }) => {
      const path = new URL(url).pathname;
      requests.push({ path, body: JSON.parse(options?.body || "{}") });
      const data = path === "/api/v1/auth/google"
        ? { needs_onboarding: true, temp_token: "test-temporary-token", email: "student@example.com", name: "Sinh viên" }
        : path === "/api/v1/auth/google/onboard" ? { participant_token: "test-session", participant_code: "anonymous" }
        : path === "/api/v1/participants/me" ? { participant_code: "anonymous", survey: {} } : [];
      return { ok: true, json: async () => data };
    },
    require: (name: string) => {
      if (name === "react") return { ...React,
        useState: (initial: unknown) => {
          const index = cursor++;
          if (!(index in state)) state[index] = initial;
          return [state[index], (value: unknown) => { state[index] = value; }];
        },
        useRef: (initial: unknown) => ({ current: initial }),
        useEffect: (effect: () => void) => { effects.push(effect); }
      };
      if (name === "react/jsx-runtime") return require(name);
      if (name === "../lib/security") return {
        validateNoSecretInUrl: () => ({ valid: true }),
        sanitizeApiError: String,
        sanitizeNotice: (value: string) => value,
        cleanLegacyAdminStorage: () => {},
        getAdminSession: () => null
      };
      if (name === "../lib/sync") return { getDriveSyncStatusInfo: () => ({}), isBothSaved: () => false };
      return {};
    }
  };
  runInNewContext(ts.transpileModule(page, { compilerOptions: {
    module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022
  } }).outputText, sandbox);
  const render = () => { cursor = 0; return sandbox.exports.default(); };
  const nodes = (node: any): any[] => {
    if (!node || typeof node !== "object") return [];
    if (Array.isArray(node)) return node.flatMap(nodes);
    return [node, ...nodes(node.props?.children)];
  };
  const find = (predicate: (node: any) => boolean) => nodes(render()).find(predicate);
  const field = (value: string) => find(node => node.props?.name === value);
  const submit = () => find(node => node.type === "button" && node.props?.onClick?.name === "handleCompleteGoogleOnboard");
  const start = async () => {
    render();
    effects.splice(0).forEach(effect => effect());
    callback!({ credential: "test-google-credential" });
    await new Promise(resolve => setImmediate(resolve));
  };
  return { start, render, find, field, submit, requests };
}

test("Google onboarding requires an explicit CEFR choice before submission", async () => {
  const ui = onboardingHarness();
  await ui.start();
  const english = ui.field("english_level");
  assert.ok(english, "English proficiency select must be present");
  assert.equal(english.type, "select");
  assert.equal(english.props.value, "");
  assert.equal(english.props.required, true);
  assert.ok(!/gridTemplateColumns: "1fr 1fr"/.test(page.slice(page.indexOf("GOOGLE ONBOARDING FORM"), page.indexOf("GOOGLE-ONLY PARTICIPANT LOGIN"))), "Onboarding field groups must collapse on narrow screens");
  assert.deepEqual(Array.from(english.props.children, (option: any) => option.props.value), ["", "A1", "A2", "B1", "B2", "C1", "C2", "Chưa rõ"]);
  ui.find(node => node.type === "input" && node.props.type === "checkbox").props.onChange({ target: { checked: true } });
  assert.equal(ui.submit().props.disabled, true);
  await ui.submit().props.onClick();
  assert.equal(ui.requests.filter(request => request.path.endsWith("/onboard")).length, 0);
  english.props.onChange({ target: { value: "Chưa rõ" } });
  assert.equal(ui.submit().props.disabled, false);
  ui.find(node => node.type === "button" && node.props.children === "Đổi tài khoản").props.onClick();
  await ui.start();
  assert.equal(ui.field("english_level").props.value, "", "A new Google onboarding session needs its own explicit choice");
});


test("Google onboarding sends optional student details and preserves survey fields", async () => {
  const ui = onboardingHarness();
  await ui.start();
  for (const [name, maxLength] of [["participant_code", 60], ["class_name", 100], ["referring_lecturer", 150]] as const) {
    const field = ui.field(name);
    assert.ok(field, `${name} input must be present`);
    assert.equal(field.props.required, undefined);
    assert.equal(field.props.maxLength, maxLength);
    assert.equal(field.props.value, "");
  }
  ui.field("english_level").props.onChange({ target: { value: "B2" } });
  ui.field("participant_code").props.onChange({ target: { value: "  SE194007  " } });
  ui.field("class_name").props.onChange({ target: { value: "  SE19  " } });
  ui.field("referring_lecturer").props.onChange({ target: { value: "  Nguyễn Văn An  " } });
  ui.find(node => node.type === "input" && node.props.type === "checkbox").props.onChange({ target: { checked: true } });
  await ui.submit().props.onClick();
  assert.deepEqual(ui.requests.find(request => request.path.endsWith("/onboard"))?.body, {
    temp_token: "test-temporary-token", consent: true, consent_version: "v1.0",
    participant_code: "SE194007", english_level: "B2", class_name: "SE19", referring_lecturer: "Nguyễn Văn An",
    accent_region: "Miền Bắc", birth_year: 2004, academic_year: "Năm 3",
    microphone: "Tai nghe có mic", environment: "Rất yên tĩnh (Phòng kín)"
  });
});

test("participant portal offers only Google authentication while retaining admin login", () => {
  assert.doesNotMatch(page, /studentAuthMode|studentIdentifierInput|handleStudentLogin|handleStudentSignup/);
  assert.doesNotMatch(page, /\/api\/v1\/auth\/student-login|Đăng ký không dùng Google|hoặc dùng mã truy cập bí mật/);
  assert.ok(!/showSecretToken|copiedToken|maskSecretToken/.test(page), "Google-only participants must not see secret-token controls");
  assert.match(page, /google-signin-btn-container/);
  assert.match(page, /\/api\/v1\/auth\/admin-login/);
  assert.match(page, /onClick=\{handleAdminLogin\}/);
});
