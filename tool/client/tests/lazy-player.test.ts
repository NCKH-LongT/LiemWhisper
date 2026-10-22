import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const source = readFileSync(new URL("../components/AuthenticatedAudioPlayer.tsx", import.meta.url), "utf8");

// Execute the real component with a small hook host, without a browser or network.
function mount(fetchImpl: typeof fetch) {
  const state: any[] = [];
  let cursor = 0;
  let previousDeps: any[] = [];
  let pendingEffect: (() => any) | undefined;
  let cleanup: (() => void) | undefined;
  const revoked: string[] = [];
  const react = {
    createElement: (type: any, props: any, ...children: any[]) => ({ type, props: { ...props, children } }),
    useState(initial: any) {
      const index = cursor++;
      if (!(index in state)) state[index] = initial;
      return [state[index], (value: any) => { state[index] = typeof value === "function" ? value(state[index]) : value; }];
    },
    useRef(initial: any) {
      const index = cursor++;
      return state[index] ?? (state[index] = { current: initial });
    },
    useEffect(effect: () => any, deps: any[]) {
      if (deps.some((value, index) => value !== previousDeps[index])) {
        pendingEffect = effect;
        previousDeps = deps;
      }
    }
  };
  const context: any = {
    exports: {}, AbortController, fetch: fetchImpl,
    URL: { createObjectURL: () => "blob:audio", revokeObjectURL: (url: string) => revoked.push(url) },
    require: (name: string) => name === "react" ? react : { sanitizeApiError: (error: Error) => error.message }
  };
  runInNewContext(ts.transpileModule(source + "\nexports.Player = LazyAudioPlayer;", {
    compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.React, target: ts.ScriptTarget.ES2022, esModuleInterop: true }
  }).outputText, context);
  return {
    render() {
      cursor = 0;
      const tree = context.exports.Player({ apiBase: "https://api.example", audioPath: "/recordings/1/audio", authHeader: { name: "x-admin-key", value: "secret" } });
      if (pendingEffect) { cleanup?.(); cleanup = pendingEffect(); pendingEffect = undefined; }
      return tree;
    },
    unmount() { cleanup?.(); },
    revoked
  };
}

const settle = () => new Promise(resolve => setImmediate(resolve));

test("no media request until Play; authenticated load is reused and released on unmount", async () => {
  const calls: any[] = [];
  const player = mount(async (url, options) => {
    calls.push({ url, options });
    return ({ ok: true, blob: async () => new Blob(["audio"]) } as Response);
  });
  let tree = player.render();
  player.render();
  assert.equal(calls.length, 0);
  assert.equal(tree.type, "button");
  tree.props.onClick();
  player.render();
  await settle();
  tree = player.render();
  assert.equal(calls.length, 1);
  assert.equal(calls[0].options.headers["x-admin-key"], "secret");
  assert.equal(tree.type, "audio");
  assert.equal(tree.props.src, "blob:audio");
  assert.equal(tree.props.autoPlay, true);
  assert.equal(tree.props.preload, "none");
  player.render();
  assert.equal(calls.length, 1);
  player.unmount();
  assert.equal(calls[0].options.signal.aborted, true);
  assert.deepEqual(player.revoked, ["blob:audio"]);
});

test("closing a player cancels pending download and ignores a late response", async () => {
  let resolve!: (value: Response) => void;
  let signal: AbortSignal | undefined;
  const player = mount((_url, options) => {
    signal = options?.signal as AbortSignal;
    return new Promise(done => { resolve = done; });
  });
  player.render().props.onClick();
  player.render();
  player.unmount();
  assert.equal(signal?.aborted, true);
  resolve(({ ok: true, blob: async () => new Blob(["audio"]) } as Response));
  await settle();
  assert.deepEqual(player.revoked, []);
});

test("failed download can be retried by clicking once", async () => {
  let attempts = 0;
  const player = mount(async () => ++attempts === 1
    ? ({ ok: false, status: 503, json: async () => ({ detail: "Unavailable" }) } as Response)
    : ({ ok: true, blob: async () => new Blob(["audio"]) } as Response));
  player.render().props.onClick();
  player.render();
  await settle();
  const error = player.render();
  const retry = error.props.children.find((child: any) => child?.type === "button");
  assert.ok(retry);
  retry.props.onClick();
  player.render();
  await settle();
  assert.equal(player.render().type, "audio");
  assert.equal(attempts, 2);
  player.unmount();
});

