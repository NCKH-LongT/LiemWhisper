import test from "node:test";
import assert from "node:assert/strict";
import { openDrivePopup } from "../lib/drive-popup.ts";

test("opens synchronously, keeps admin tab, refreshes after popup closes", async () => {
  const events: string[] = [];
  const popup = { closed: false, opener: {} as unknown, location: { replace(url: string) { events.push(url); } }, close() { this.closed = true; } };
  let tick = () => {};
  const host = {
    open() { events.push("open"); return popup; },
    setInterval(fn: () => void) { tick = fn; return 1; },
    clearInterval() { events.push("cleanup"); }
  };
  const flow = openDrivePopup(host, () => events.push("refresh"));
  assert.deepEqual(events, ["open"]);
  assert.equal(popup.opener, null);
  flow.navigate("https://api.test/start#ticket");
  assert.equal(events[1], "https://api.test/start#ticket");
  tick();
  assert.ok(!events.includes("refresh"));
  popup.closed = true;
  tick();
  assert.deepEqual(events.slice(-2), ["cleanup", "refresh"]);
});

test("blocked popup does not navigate the admin tab", () => {
  assert.throws(() => openDrivePopup({ open: () => null, setInterval: () => 1, clearInterval() {} }, () => {}), /cửa sổ/);
});

test("cancel cleans timer and window without a success callback", () => {
  let refreshed = false;
  let cleared = false;
  const popup = { closed: false, opener: null, location: { replace() {} }, close() { this.closed = true; } };
  const flow = openDrivePopup({ open: () => popup, setInterval: () => 1, clearInterval() { cleared = true; } }, () => { refreshed = true; });
  flow.cancel();
  assert.equal(popup.closed, true);
  assert.equal(cleared, true);
  assert.equal(refreshed, false);
});
