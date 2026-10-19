import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

const page = readFileSync(new URL("../app/page.tsx", import.meta.url), "utf8");

test("student upload notification uses friendly message without drive sync text", () => {
  // Check uploadRecording notification
  assert.ok(
    page.includes("Đã lưu bản ghi âm câu ${currentIndex + 1} thành công!"),
    "Expected student-friendly upload success notification"
  );
  // Ensure setNotice(syncInfo.description) is NOT called in uploadRecording
  const uploadFnMatch = page.match(/async function uploadRecording\([^)]*\)[\s\S]*?finally \{/);
  assert.ok(uploadFnMatch, "uploadRecording function found");
  assert.ok(
    !uploadFnMatch[0].includes("setNotice(syncInfo.description)"),
    "Student upload notice must not show raw Google Drive sync description"
  );
});

test("student studio interface includes complete session button and celebration dialog", () => {
  assert.ok(
    page.includes("Hoàn thành bài thu âm"),
    "Page must include 'Hoàn thành bài thu âm' button"
  );
  assert.ok(
    page.includes("/api/v1/participants/complete"),
    "Page must call participant completion endpoint"
  );
  assert.ok(
    page.includes("handleCompleteSession"),
    "Page must define handleCompleteSession handler"
  );
  assert.ok(
    page.includes("Xem lại các câu đã thu âm"),
    "Page must allow student to review recordings even after completion"
  );
});

test("completion prevents re-submitting and locks recording into read-only mode", () => {
  assert.ok(
    page.includes("isParticipantCompleted"),
    "Page must compute isParticipantCompleted status"
  );
  assert.ok(
    page.includes("Đã hoàn thành bài thu âm"),
    "Page must display finished badge once completed instead of re-submit button"
  );
  assert.ok(
    page.includes("Chế độ xem lại"),
    "Page must indicate read-only review mode"
  );
  // Ensure startRecording and uploadRecording check isParticipantCompleted
  assert.ok(
    page.includes("if (isParticipantCompleted)"),
    "Must check isParticipantCompleted before allowing startRecording or handleCompleteSession"
  );
});

