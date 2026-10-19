import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { runInNewContext } from "node:vm";

const require = createRequire(import.meta.url);
const ts = require("typescript");
const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

test("legacy prompt punctuation is cleaned before question and answer display", () => {
  const statement = page.match(/const text = .*currentTask\.text.*;/)?.[0];
  assert.ok(statement);
  const context: any = { currentTask: { text: "Câu hỏi: A; B\n\nTrả lời: C; D" } };
  runInNewContext(`${statement} globalThis.result = text;`, context);
  assert.equal(context.result, "Câu hỏi: A, B\n\nTrả lời: C, D");
});

test("stopping recording keeps preview URL alive until explicitly discarded", async () => {
  const revoked: string[] = [];
  let preview = "";
  let recorder: any;
  const stopped: string[] = [];
  const refs: Record<string, { current: any }> = Object.fromEntries(["timerRef", "animFrameRef", "streamRef", "audioContextRef", "analyserRef", "recorderRef", "urlRef", "chunksRef"].map(name => [name, { current: null }]));
  refs.urlRef.current = "";
  const source = [
    page.slice(page.indexOf("  function cleanupMedia("), page.indexOf("  function alertError(")),
    page.slice(page.indexOf("  async function startRecording("), page.indexOf("  async function uploadRecording(")),
    "globalThis.start = startRecording; globalThis.discard = clearRecordedAudio;"
  ].join("\n");
  const noop = () => {};
  class Recorder {
    static isTypeSupported() { return true; }
    mimeType = "audio/webm";
    state = "recording";
    ondataavailable: any;
    onstop: any;
    constructor() { recorder = this; }
    start() {}
    stop() {
      this.ondataavailable({ data: new Blob(["recorded audio"]) });
      this.state = "inactive";
      this.onstop();
    }
  }
  class AudioContext {
    state = "running";
    createMediaStreamSource() { return { connect: noop }; }
    createAnalyser() { return {}; }
    close() { stopped.push("context"); return Promise.resolve(); }
  }
  const sandbox: any = {
    ...refs, Blob, Date, navigator: { mediaDevices: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => stopped.push("mic") }] }) } },
    window: { AudioContext }, MediaRecorder: Recorder,
    URL: { createObjectURL: () => "blob:preview", revokeObjectURL: (url: string) => revoked.push(url) },
    setAudioUrl: (url: string) => { preview = url; },
    setRecordedBlob: noop, setRecordedFor: noop, setRecordedDuration: noop,
    setError: noop, setNotice: noop, setIsRecording: noop, setRecordingSeconds: noop,
    getBestMimeType: () => "audio/webm", drawWaveform: noop, alertError: (error: unknown) => { throw error; },
    clearInterval: noop, cancelAnimationFrame: noop, setInterval: () => 1
  };
  runInNewContext(ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022 } }).outputText, sandbox);
  await sandbox.start("prompt-1");
  recorder.stop();
  assert.equal(preview, "blob:preview");
  assert.deepEqual(revoked, [], "preview must not be revoked by microphone cleanup");
  assert.ok(stopped.includes("mic"));
  sandbox.discard();
  assert.deepEqual(revoked, ["blob:preview"]);
  assert.equal(preview, "");
});

test("recorded student task provides playback for existing recording and preview duration fix", () => {
  assert.ok(
    page.includes("audioPath={`/api/v1/recordings/${currentTask.recording_id}/audio`}"),
    "Must offer playback route for already-saved task recording"
  );
  assert.ok(
    page.includes('authHeader={{ name: "x-participant-token", value: token }}'),
    "Must authenticate student playback with x-participant-token"
  );
  assert.ok(
    page.includes("key={audioUrl}"),
    "Preview audio tag must set key={audioUrl} to avoid DOM recycling bug"
  );
  assert.ok(
    page.includes("el.currentTime = 1e101"),
    "Preview audio tag must include duration fix for Chromium WebM duration bug"
  );
});

