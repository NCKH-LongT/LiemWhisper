"use client";

import { useEffect, useRef, useState } from "react";
import { getDriveSyncStatusInfo, isBothSaved } from "../lib/sync";
import {
  validateNoSecretInUrl,
  sanitizeApiError,
  sanitizeNotice,
  maskSecretToken,
  cleanLegacyAdminStorage,
  getAdminSession,
  saveAdminSession,
  clearAdminSession
} from "../lib/security";
import { DriveStatusResponse } from "../lib/drive";
import { downloadAuthenticatedExport } from "../lib/auth-fetch";
import { AdminDrivePanel } from "../components/AdminDrivePanel";
import { AuthenticatedAudioPlayer } from "../components/AuthenticatedAudioPlayer";

const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type Course = {
  id: string;
  title: string;
  description?: string;
  prompt_count?: number;
};

type Task = {
  id: string;
  text: string;
  language: string;
  target_terms?: string[];
  difficulty?: string;
  category?: string;
  recording_id: string | null;
  status: string | null;
  duration_seconds?: number;
  drive_sync_status?: string | null;
  drive_sync_message?: string | null;
};

type ParticipantMe = {
  participant_id: string;
  participant_code: string;
  consent_version: string;
  total_recordings: number;
  survey: Record<string, string>;
};

type AdminStats = {
  total_courses: number;
  total_prompts: number;
  published_prompts: number;
  total_participants: number;
  total_recordings: number;
  approved_recordings: number;
  rejected_recordings: number;
  rerecord_recordings: number;
  pending_recordings: number;
  approved_duration_minutes: number;
  total_duration_minutes: number;
  courses: Array<{
    id: string;
    title: string;
    prompts_count: number;
    recordings_count: number;
    approved_count: number;
  }>;
};

type ReviewItem = {
  id: string;
  prompt_id: string;
  text: string;
  target_terms?: string[];
  course_title: string;
  participant_code: string;
  status: string;
  transcript: string | null;
  reviewer_notes: string | null;
  duration_seconds: number;
  bytes: number;
  format: string;
  created_at: number;
};

// --- Clean SVG Icons (Replacing all emojis) ---

function MicIcon({ size = 16, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3Z" />
      <path d="M19 10v2a7 7 0 0 1-14 0v-2" />
      <line x1="12" y1="19" x2="12" y2="22" />
    </svg>
  );
}

function StopIcon({ size = 14, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill={color} stroke={color} strokeWidth="1">
      <rect x="5" y="5" width="14" height="14" rx="2" />
    </svg>
  );
}

function RefreshIcon({ size = 14, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
      <path d="M3 3v5h5" />
      <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
      <path d="M16 21h5v-5" />
    </svg>
  );
}

function CheckIcon({ size = 14, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="20 6 9 17 4 12" />
    </svg>
  );
}

function CrossIcon({ size = 14, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="6" x2="6" y2="18" />
      <line x1="6" y1="6" x2="18" y2="18" />
    </svg>
  );
}

function ChevronLeftIcon({ size = 15 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="15 18 9 12 15 6" />
    </svg>
  );
}

function ChevronRightIcon({ size = 15 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="9 18 15 12 9 6" />
    </svg>
  );
}

function DownloadIcon({ size = 15, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
      <polyline points="7 10 12 15 17 10" />
      <line x1="12" y1="15" x2="12" y2="3" />
    </svg>
  );
}

function LogoutIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  );
}

function UserIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2" />
      <circle cx="12" cy="7" r="4" />
    </svg>
  );
}

function ShieldIcon({ size = 14 }: { size?: number }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

async function request(path: string, opts: RequestInit = {}) {
  const check = validateNoSecretInUrl(path);
  if (!check.valid) {
    throw new Error(`Bảo mật: Không được chuyển thông tin bí mật (${check.forbiddenParam}) qua URL query.`);
  }

  const res = await fetch(API + path, opts);
  const data = await res.json().catch(() => ({ detail: "Phản hồi không hợp lệ từ máy chủ." }));
  if (!res.ok) {
    const rawMsg = typeof data.detail === "string" ? data.detail : JSON.stringify(data.detail);
    throw new Error(sanitizeApiError(rawMsg));
  }
  return data;
}

function getBestMimeType(): string {
  if (typeof window === "undefined" || !window.MediaRecorder) return "";
  const types = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/aac",
    "audio/ogg;codecs=opus",
    "audio/wav"
  ];
  for (const t of types) {
    if (MediaRecorder.isTypeSupported(t)) return t;
  }
  return "";
}

export default function Home() {
  // Session & Role management: "guest" | "student" | "admin"
  const [role, setRole] = useState<"guest" | "student" | "admin">("guest");
  const [authRoleTab, setAuthRoleTab] = useState<"student" | "admin">("student");
  const [studentAuthMode, setStudentAuthMode] = useState<"login" | "signup">("login");
  const [studentIdentifierInput, setStudentIdentifierInput] = useState("");
  const [adminKeyInput, setAdminKeyInput] = useState("");

  // Student session data
  const [token, setToken] = useState("");
  const [participantInfo, setParticipantInfo] = useState<ParticipantMe | null>(null);
  const [showSecretToken, setShowSecretToken] = useState(false);
  const [copiedToken, setCopiedToken] = useState(false);

  // Signup form state
  const [consent, setConsent] = useState(false);
  const [participantCode, setParticipantCode] = useState("");
  const [familiarity, setFamiliarity] = useState("Đang học");
  const [english, setEnglish] = useState("Bình thường");
  const [mic, setMic] = useState("Điện thoại");
  const [environment, setEnvironment] = useState("Phòng yên tĩnh");

  // Courses & tasks
  const [courses, setCourses] = useState<Course[]>([]);
  const [selectedCourse, setSelectedCourse] = useState("");
  const [tasks, setTasks] = useState<Task[]>([]);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [syncRefreshing, setSyncRefreshing] = useState(false);

  // Recording studio state
  const [isRecording, setIsRecording] = useState(false);
  const [recordingSeconds, setRecordingSeconds] = useState(0);
  const [audioUrl, setAudioUrl] = useState("");
  const [recordedBlob, setRecordedBlob] = useState<Blob | null>(null);
  const [recordedFor, setRecordedFor] = useState<string | null>(null);
  const [recordedDuration, setRecordedDuration] = useState(0);

  // Status & loading
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Admin state (Memory only, never persisted to localStorage)
  const [adminKey, setAdminKey] = useState("");
  const [adminSubTab, setAdminSubTab] = useState<"stats" | "prompts" | "reviews" | "export">("stats");
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [driveStatus, setDriveStatus] = useState<DriveStatusResponse | null>(null);
  const [adminCourses, setAdminCourses] = useState<any[]>([]);
  const [newCourseTitle, setNewCourseTitle] = useState("");
  const [newCourseDesc, setNewCourseDesc] = useState("");
  const [bulkCourseId, setBulkCourseId] = useState("");
  const [bulkText, setBulkText] = useState("");
  const [bulkPublish, setBulkPublish] = useState(true);
  const [reviewList, setReviewList] = useState<ReviewItem[]>([]);
  const [reviewFilterStatus, setReviewFilterStatus] = useState("pending_review");
  const [reviewTranscripts, setReviewTranscripts] = useState<Record<string, string>>({});
  const [reviewNotes, setReviewNotes] = useState<Record<string, string>>({});

  // MediaRecorder & AudioContext refs
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<BlobPart[]>([]);
  const streamRef = useRef<MediaStream | null>(null);
  const timerRef = useRef<any>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameRef = useRef<number | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const urlRef = useRef("");

  // Initialize and restore saved sessions
  useEffect(() => {
    // Clear any legacy persistent entries in localStorage
    cleanLegacyAdminStorage();

    const savedRole = localStorage.getItem("liemwhisper_role");
    const savedToken = localStorage.getItem("liemwhisper_token");
    const savedAdminSession = getAdminSession();

    loadCourses();

    if (savedAdminSession) {
      setAdminKey(savedAdminSession);
      setRole("admin");
      loadAdminStats(savedAdminSession).catch(() => {
        clearAdminSession();
        setAdminKey("");
        setRole("guest");
      });
      loadAdminCourses(savedAdminSession);
      loadDriveStatus(savedAdminSession);
    } else if (savedRole === "student" && savedToken) {
      setToken(savedToken);
      setRole("student");
      loadParticipantMe(savedToken);
    } else {
      setRole("guest");
    }

    return () => {
      cleanupMedia();
    };
  }, []);

  // Reload tasks when selected course or token changes in student mode
  useEffect(() => {
    if (role === "student" && token && selectedCourse) {
      loadTasks(selectedCourse, token);
    }
  }, [selectedCourse, token, role]);

  function cleanupMedia() {
    if (timerRef.current) clearInterval(timerRef.current);
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    streamRef.current?.getTracks().forEach((x) => x.stop());
    streamRef.current = null;
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = "";
    }
  }

  function clearRecordedAudio() {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current);
      urlRef.current = "";
    }
    setAudioUrl("");
    setRecordedBlob(null);
    setRecordedFor(null);
    setRecordedDuration(0);
  }

  function alertError(e: unknown) {
    const msg = sanitizeApiError(e);
    setError(msg);
    setNotice("");
  }

  async function loadCourses(): Promise<Course[]> {
    try {
      const data: Course[] = await request("/api/v1/courses");
      setCourses(data);
      if (data.length > 0 && !selectedCourse) {
        setSelectedCourse(data[0].id);
      }
      return data;
    } catch {
      return [];
    }
  }

  async function loadParticipantMe(activeToken: string) {
    try {
      const data: ParticipantMe = await request("/api/v1/participants/me", {
        headers: { "x-participant-token": activeToken }
      });
      setParticipantInfo(data);
      if (selectedCourse) {
        loadTasks(selectedCourse, activeToken);
      }
    } catch {
      setParticipantInfo(null);
    }
  }

  async function loadTasks(courseId: string, customToken?: string) {
    const activeToken = customToken || token;
    if (!activeToken || !courseId) return;
    setBusy(true);
    setError("");
    try {
      const data: Task[] = await request("/api/v1/tasks?course_id=" + encodeURIComponent(courseId), {
        headers: { "x-participant-token": activeToken }
      });
      setTasks(data);
      clearRecordedAudio();
      const firstUnrecorded = data.findIndex((t) => !t.recording_id);
      setCurrentIndex(firstUnrecorded >= 0 ? firstUnrecorded : 0);
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  // Refresh sync status manually while strictly avoiding resetting active recording or audio
  async function refreshTasksSyncStatus() {
    if (!token || !selectedCourse) return;
    setSyncRefreshing(true);
    try {
      const data: Task[] = await request("/api/v1/tasks?course_id=" + encodeURIComponent(selectedCourse), {
        headers: { "x-participant-token": token }
      });
      setTasks(data);
      setNotice("Đã cập nhật trạng thái đồng bộ mới nhất từ hệ thống.");
    } catch (e) {
      alertError(e);
    } finally {
      setSyncRefreshing(false);
    }
  }

  // ---------------- AUTHENTICATION HANDLERS ----------------

  async function handleStudentLogin() {
    const secretToken = studentIdentifierInput.trim();
    if (!secretToken) {
      setError("Vui lòng nhập Mã truy cập bí mật của bạn.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await request("/api/v1/auth/student-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ identifier: secretToken })
      });
      const activeTok = res.token || secretToken;
      setToken(activeTok);
      // Retained in localStorage for convenience with documented limitation (no HttpOnly claim)
      localStorage.setItem("liemwhisper_token", activeTok);
      localStorage.setItem("liemwhisper_role", "student");
      setRole("student");

      // Never echo secret access token in user notice
      const displayName = res.participant_code || "Người tham gia";
      setNotice(`Đăng nhập thành công. Tài khoản: ${displayName}`);

      await loadParticipantMe(activeTok);
      const cList = await loadCourses();
      const cid = selectedCourse || (cList.length > 0 ? cList[0].id : "");
      if (cid) {
        setSelectedCourse(cid);
        loadTasks(cid, activeTok);
      }
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  async function handleStudentSignup() {
    if (!consent) {
      setError("Vui lòng xác nhận sự đồng ý tham gia nghiên cứu.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await request("/api/v1/participants", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          consent: true,
          consent_version: "v1.0",
          participant_code: participantCode.trim(),
          familiarity,
          english_level: english,
          microphone: mic,
          environment
        })
      });
      setToken(res.participant_token);
      localStorage.setItem("liemwhisper_token", res.participant_token);
      localStorage.setItem("liemwhisper_role", "student");
      setRole("student");

      // Only display pseudonymous code, never echo raw secret token
      setNotice(`Đăng ký thành công. Mã định danh: ${res.participant_code || "Mới"}`);

      await loadParticipantMe(res.participant_token);
      const cList = await loadCourses();
      const cid = selectedCourse || (cList.length > 0 ? cList[0].id : "");
      if (cid) {
        setSelectedCourse(cid);
        loadTasks(cid, res.participant_token);
      }
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  async function handleAdminLogin() {
    const key = adminKeyInput.trim();
    if (!key) {
      setError("Vui lòng nhập Mật khẩu Quản trị (Admin API Key).");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await request("/api/v1/auth/admin-login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key })
      });
      // Issued opaque session token (8h TTL)
      const sessionToken = res.token || key;
      setAdminKey(sessionToken);
      saveAdminSession(sessionToken);

      // Clean any legacy persistent entry from localStorage
      cleanLegacyAdminStorage();

      setRole("admin");
      setNotice("Đăng nhập quyền quản trị viên thành công.");
      await loadAdminStats(sessionToken);
      await loadAdminCourses(sessionToken);
      await loadDriveStatus(sessionToken);
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  async function handleLogout() {
    cleanupMedia();
    if (role === "admin" && adminKey) {
      try {
        await request("/api/v1/auth/admin-logout", {
          method: "POST",
          headers: { "x-admin-key": adminKey }
        });
      } catch {
        // Backend may expire or route separately; proceed to clear local memory
      }
    }

    cleanLegacyAdminStorage();
    clearAdminSession();
    localStorage.removeItem("liemwhisper_role");
    localStorage.removeItem("liemwhisper_token");
    setRole("guest");
    setToken("");
    setAdminKey("");
    setParticipantInfo(null);
    setDriveStatus(null);
    setTasks([]);
    clearRecordedAudio();
    setNotice("Đã kết thúc phiên làm việc.");
  }

  async function handleWithdraw() {
    if (!confirm("Bạn có chắc chắn muốn rút lại sự đồng ý và xóa toàn bộ dữ liệu ghi âm của mình khỏi máy chủ?")) return;
    setBusy(true);
    try {
      await request("/api/v1/participants/withdraw", {
        method: "POST",
        headers: { "x-participant-token": token }
      });
      handleLogout();
      alert("Đã rút lại sự đồng ý và xóa toàn bộ dữ liệu.");
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  // ---------------- RECORDING & WAVEFORM ----------------

  function drawWaveform() {
    if (!analyserRef.current || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const analyser = analyserRef.current;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    analyser.getByteFrequencyData(dataArray);

    ctx.clearRect(0, 0, canvas.width, canvas.height);
    const barWidth = canvas.width / 24;
    let x = 0;

    for (let i = 0; i < 24; i++) {
      const idx = Math.floor((i * bufferLength) / 24);
      const val = dataArray[idx] || 0;
      const barHeight = Math.max(3, (val / 255) * canvas.height);
      const y = (canvas.height - barHeight) / 2;

      ctx.fillStyle = isRecording ? "#dc2626" : "#2563eb";
      ctx.beginPath();
      ctx.roundRect(x, y, barWidth - 3, barHeight, 2);
      ctx.fill();

      x += barWidth;
    }

    animFrameRef.current = requestAnimationFrame(drawWaveform);
  }

  async function startRecording(taskId: string) {
    clearRecordedAudio();
    setError("");
    setNotice("");

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true }
      });
      streamRef.current = stream;
      chunksRef.current = [];

      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AudioCtx();
      audioContextRef.current = audioCtx;
      const source = audioCtx.createMediaStreamSource(stream);
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      source.connect(analyser);
      analyserRef.current = analyser;

      const mimeType = getBestMimeType();
      const options: MediaRecorderOptions = mimeType ? { mimeType } : {};
      const recorder = new MediaRecorder(stream, options);

      recorder.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data);
      };

      const startTime = Date.now();
      recorder.onstop = () => {
        const durationSec = Math.max(0.5, (Date.now() - startTime) / 1000);
        const usedMime = recorder.mimeType || mimeType || "audio/webm";
        const blob = new Blob(chunksRef.current, { type: usedMime });
        setRecordedBlob(blob);
        setRecordedFor(taskId);
        setRecordedDuration(durationSec);

        const url = URL.createObjectURL(blob);
        urlRef.current = url;
        setAudioUrl(url);

        cleanupMedia();
        setIsRecording(false);
      };

      recorder.start(100);
      recorderRef.current = recorder;
      setIsRecording(true);
      setRecordingSeconds(0);

      timerRef.current = setInterval(() => {
        setRecordingSeconds((prev) => {
          if (prev >= 45) {
            stopRecording();
            return 45;
          }
          return prev + 1;
        });
      }, 1000);

      drawWaveform();
    } catch (e: any) {
      alertError(
        e.name === "NotAllowedError" || e.name === "PermissionDeniedError"
          ? "Trình duyệt chưa được cấp quyền micro. Vui lòng bật lại micro trong cài đặt trình duyệt để tiếp tục."
          : `Không thể khởi tạo ghi âm: ${e.message}`
      );
    }
  }

  function stopRecording() {
    if (recorderRef.current && recorderRef.current.state !== "inactive") {
      recorderRef.current.stop();
    }
    if (timerRef.current) clearInterval(timerRef.current);
  }

  async function uploadRecording(taskId: string) {
    if (!recordedBlob || recordedFor !== taskId) {
      setError("Bản ghi âm không khớp với câu hiện tại.");
      return;
    }
    if (recordedDuration < 0.8) {
      setError("Bản ghi âm quá ngắn (dưới 1 giây). Vui lòng thu lại cả câu.");
      return;
    }

    setBusy(true);
    setError("");
    try {
      const ext = recordedBlob.type.includes("mp4") ? "mp4" : recordedBlob.type.includes("wav") ? "wav" : "webm";
      const form = new FormData();
      form.append("prompt_id", taskId);
      form.append("audio", recordedBlob, `recording.${ext}`);
      form.append("duration", recordedDuration.toFixed(2));

      const res = await request("/api/v1/recordings", {
        method: "POST",
        headers: { "x-participant-token": token },
        body: form
      });

      // Use returned recording_id (not placeholder "uploaded")
      const returnedRecId = res.recording_id || taskId;
      const driveSyncStatus = res.drive_sync_status || null;
      const driveSyncMsg = res.drive_sync_message || null;
      const syncInfo = getDriveSyncStatusInfo(driveSyncStatus, driveSyncMsg);

      clearRecordedAudio();

      setTasks((prev) =>
        prev.map((t) =>
          t.id === taskId
            ? {
                ...t,
                recording_id: returnedRecId,
                status: res.status || "pending_review",
                drive_sync_status: driveSyncStatus,
                drive_sync_message: driveSyncMsg
              }
            : t
        )
      );

      // Do not claim both saved until synced
      setNotice(syncInfo.description);

      if (currentIndex < tasks.length - 1) {
        setCurrentIndex((i) => i + 1);
      }
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  // ---------------- ADMIN ACTIONS ----------------

  async function loadDriveStatus(keyOverride?: string) {
    const k = keyOverride || adminKey;
    if (!k) return;
    try {
      const data: DriveStatusResponse = await request("/api/v1/admin/drive/status", {
        headers: { "x-admin-key": k }
      });
      setDriveStatus(data);
    } catch {
      setDriveStatus(null);
    }
  }

  async function loadAdminStats(keyOverride?: string) {
    const k = keyOverride || adminKey;
    if (!k) return;
    try {
      const data = await request("/api/v1/admin/stats", {
        headers: { "x-admin-key": k }
      });
      setStats(data);
    } catch (e) {
      alertError(e);
    }
  }

  async function loadAdminCourses(keyOverride?: string) {
    const k = keyOverride || adminKey;
    if (!k) return;
    try {
      const data = await request("/api/v1/admin/courses", {
        headers: { "x-admin-key": k }
      });
      setAdminCourses(data);
      if (data.length > 0 && !bulkCourseId) {
        setBulkCourseId(data[0].id);
      }
    } catch (e) {
      alertError(e);
    }
  }

  async function createCourse() {
    if (!newCourseTitle.trim()) return;
    setBusy(true);
    try {
      await request("/api/v1/admin/courses", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-admin-key": adminKey
        },
        body: JSON.stringify({ title: newCourseTitle.trim(), description: newCourseDesc.trim() })
      });
      setNewCourseTitle("");
      setNewCourseDesc("");
      setNotice("Đã khởi tạo môn học mới.");
      await loadAdminCourses();
      await loadCourses();
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  async function bulkImportPrompts() {
    if (!bulkCourseId || !bulkText.trim()) {
      setError("Vui lòng chọn môn học và nhập nội dung câu hỏi.");
      return;
    }
    setBusy(true);
    try {
      const res = await request(`/api/v1/admin/courses/${bulkCourseId}/prompts/bulk`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-admin-key": adminKey
        },
        body: JSON.stringify({
          raw_text: bulkText,
          language: "vi-en",
          publish_immediately: bulkPublish
        })
      });
      setBulkText("");
      setNotice(`Đã nạp thành công ${res.created_count} câu hỏi vào hệ thống.`);
      await loadAdminCourses();
      await loadCourses();
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  async function loadReviews() {
    if (!adminKey) return;
    setBusy(true);
    try {
      const url = `/api/v1/admin/recordings?status=${encodeURIComponent(reviewFilterStatus)}`;
      const data = await request(url, {
        headers: { "x-admin-key": adminKey }
      });
      setReviewList(data);
      const draftMap: Record<string, string> = {};
      data.forEach((item: ReviewItem) => {
        draftMap[item.id] = item.transcript || item.text;
      });
      setReviewTranscripts(draftMap);
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  async function submitReview(recordingId: string, status: "approved" | "rejected" | "rerecord") {
    try {
      await request(`/api/v1/admin/recordings/${recordingId}/review`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-admin-key": adminKey
        },
        body: JSON.stringify({
          status,
          transcript: reviewTranscripts[recordingId] || "",
          notes: reviewNotes[recordingId] || ""
        })
      });
      setNotice(`Đã lưu trạng thái bản ghi: ${status}`);
      await loadReviews();
    } catch (e) {
      alertError(e);
    }
  }

  async function handleExportDownload(endpoint: string, filename: string) {
    if (!adminKey) {
      setError("Vui lòng đăng nhập lại để xuất dữ liệu.");
      return;
    }
    setBusy(true);
    try {
      await downloadAuthenticatedExport(API, endpoint, filename, adminKey);
      setNotice(`Đã tải xuống thành công ${filename}.`);
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  // Highlight English Target Terms in clean code badge style
  function renderHighlightedText(text: string, terms: string[] = []) {
    if (!terms || terms.length === 0) return <span>{text}</span>;
    const escaped = terms.map((t) => t.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|");
    if (!escaped) return <span>{text}</span>;
    const regex = new RegExp(`(${escaped})`, "gi");
    const parts = text.split(regex);
    return (
      <span>
        {parts.map((p, idx) => {
          const isTerm = terms.some((t) => t.toLowerCase() === p.toLowerCase());
          return isTerm ? (
            <code
              key={idx}
              style={{
                fontFamily: "ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace",
                background: "#f1f5f9",
                color: "#0f172a",
                border: "1px solid #cbd5e1",
                padding: "2px 6px",
                borderRadius: "4px",
                fontWeight: 600,
                fontSize: "0.92em"
              }}
            >
              {p}
            </code>
          ) : (
            <span key={idx}>{p}</span>
          );
        })}
      </span>
    );
  }

  const currentTask = tasks[currentIndex];
  const completedCount = tasks.filter((t) => !!t.recording_id).length;
  const progressPercent = tasks.length > 0 ? Math.round((completedCount / tasks.length) * 100) : 0;

  // Modern Clean Styles — Human/Engineering Standard
  const styles = {
    container: { maxWidth: 900, margin: "0 auto", padding: "28px 20px" },
    header: {
      display: "flex",
      justifyContent: "space-between",
      alignItems: "center",
      paddingBottom: 20,
      marginBottom: 24,
      borderBottom: "1px solid #e5e7eb",
      flexWrap: "wrap" as const,
      gap: 16
    },
    title: { fontSize: 20, fontWeight: 700, color: "#09090b", margin: "2px 0 0", letterSpacing: "-0.02em" },
    subtitle: { fontSize: 12, fontWeight: 600, color: "#64748b", textTransform: "uppercase" as const, letterSpacing: "0.06em" },
    card: {
      background: "#ffffff",
      border: "1px solid #e4e4e7",
      borderRadius: 12,
      padding: "24px",
      marginBottom: 20,
      boxShadow: "0 1px 3px rgba(0,0,0,0.02)"
    },
    field: {
      display: "block",
      width: "100%",
      padding: "10px 14px",
      border: "1px solid #d4d4d8",
      borderRadius: 8,
      fontSize: 14,
      color: "#09090b",
      background: "#ffffff",
      boxSizing: "border-box" as const,
      marginTop: 6,
      marginBottom: 16,
      outline: "none"
    },
    btnPrimary: {
      padding: "10px 18px",
      background: "#09090b",
      color: "#ffffff",
      border: "none",
      borderRadius: 8,
      fontWeight: 600,
      fontSize: 14,
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      gap: 8,
      transition: "background 0.15s ease"
    },
    btnSecondary: {
      padding: "9px 15px",
      background: "#ffffff",
      color: "#27272a",
      border: "1px solid #d4d4d8",
      borderRadius: 8,
      fontWeight: 500,
      fontSize: 13,
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      gap: 6
    },
    btnDanger: {
      padding: "9px 15px",
      background: "#ffffff",
      color: "#dc2626",
      border: "1px solid #fecaca",
      borderRadius: 8,
      fontWeight: 600,
      fontSize: 13,
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      gap: 6
    },
    btnSuccess: {
      padding: "10px 18px",
      background: "#16a34a",
      color: "#ffffff",
      border: "none",
      borderRadius: 8,
      fontWeight: 600,
      fontSize: 14,
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      gap: 8
    },
    btnRecord: {
      padding: "12px 24px",
      background: "#dc2626",
      color: "#ffffff",
      border: "none",
      borderRadius: 8,
      fontWeight: 600,
      fontSize: 15,
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      gap: 8
    },
    btnStop: {
      padding: "12px 24px",
      background: "#09090b",
      color: "#ffffff",
      border: "none",
      borderRadius: 8,
      fontWeight: 600,
      fontSize: 15,
      cursor: "pointer",
      display: "inline-flex",
      alignItems: "center",
      gap: 8
    },
    alertError: {
      padding: "12px 16px",
      background: "#fef2f2",
      border: "1px solid #fee2e2",
      color: "#991b1b",
      borderRadius: 8,
      marginBottom: 16,
      fontSize: 13
    },
    alertNotice: {
      padding: "12px 16px",
      background: "#f0fdf4",
      border: "1px solid #dcfce7",
      color: "#166534",
      borderRadius: 8,
      marginBottom: 16,
      fontSize: 13
    }
  };

  return (
    <main style={styles.container}>
      {/* Top Application Header */}
      <header style={styles.header}>
        <div>
          <div style={styles.subtitle}>Đề tài Nghiên cứu Khoa học · LiemWhisper</div>
          <h1 style={styles.title}>Hệ thống Thu thập Ngữ liệu Giọng nói Kỹ thuật</h1>
        </div>

        {/* User Session Status & Logout when logged in */}
        {role !== "guest" && (
          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <div
              style={{
                display: "inline-flex",
                alignItems: "center",
                gap: 6,
                padding: "6px 12px",
                borderRadius: 6,
                background: role === "admin" ? "#f4f4f5" : "#eff6ff",
                color: role === "admin" ? "#18181b" : "#1e40af",
                border: role === "admin" ? "1px solid #e4e4e7" : "1px solid #dbeafe",
                fontSize: 13,
                fontWeight: 600
              }}
            >
              {role === "admin" ? <ShieldIcon size={14} /> : <UserIcon size={14} />}
              <span>{role === "admin" ? "Quản trị viên" : `Sinh viên: ${participantInfo?.participant_code || "Người tham gia"}`}</span>
            </div>

            <button onClick={handleLogout} style={styles.btnSecondary}>
              <LogoutIcon size={13} />
              <span>Đăng xuất</span>
            </button>
          </div>
        )}
      </header>

      {/* Global Alerts */}
      {error && <div style={styles.alertError} role="alert">{error}</div>}
      {notice && <div style={styles.alertNotice} role="status">{notice}</div>}

      {/* ========================================================================= */}
      {/* 1. GUEST VIEW: ROLE SELECTION & AUTHENTICATION PORTAL */}
      {/* ========================================================================= */}
      {role === "guest" && (
        <section style={{ maxWidth: 520, margin: "32px auto" }}>
          {/* Role Chooser Tabs */}
          <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 4, background: "#f4f4f5", padding: 4, borderRadius: 8, marginBottom: 20 }}>
            <button
              onClick={() => { setAuthRoleTab("student"); setError(""); }}
              style={{
                padding: "10px 16px",
                borderRadius: 6,
                border: "none",
                fontWeight: 600,
                fontSize: 14,
                cursor: "pointer",
                background: authRoleTab === "student" ? "#ffffff" : "transparent",
                color: authRoleTab === "student" ? "#09090b" : "#71717a",
                boxShadow: authRoleTab === "student" ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
                transition: "all 0.15s ease"
              }}
            >
              Sinh viên / Người tham gia
            </button>
            <button
              onClick={() => { setAuthRoleTab("admin"); setError(""); }}
              style={{
                padding: "10px 16px",
                borderRadius: 6,
                border: "none",
                fontWeight: 600,
                fontSize: 14,
                cursor: "pointer",
                background: authRoleTab === "admin" ? "#ffffff" : "transparent",
                color: authRoleTab === "admin" ? "#09090b" : "#71717a",
                boxShadow: authRoleTab === "admin" ? "0 1px 3px rgba(0,0,0,0.06)" : "none",
                transition: "all 0.15s ease"
              }}
            >
              Quản trị viên
            </button>
          </div>

          {/* STUDENT AUTH CARD */}
          {authRoleTab === "student" && (
            <div style={styles.card}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #f4f4f5", paddingBottom: 14, marginBottom: 20 }}>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: "#09090b" }}>
                  {studentAuthMode === "login" ? "Đăng nhập phòng thu" : "Đăng ký tham gia thu âm"}
                </h2>
                <div style={{ display: "flex", gap: 4, background: "#f4f4f5", padding: 3, borderRadius: 6 }}>
                  <button
                    onClick={() => { setStudentAuthMode("login"); setError(""); }}
                    style={{
                      padding: "5px 10px",
                      borderRadius: 4,
                      border: "none",
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: "pointer",
                      background: studentAuthMode === "login" ? "#ffffff" : "transparent",
                      color: studentAuthMode === "login" ? "#09090b" : "#71717a",
                      boxShadow: studentAuthMode === "login" ? "0 1px 2px rgba(0,0,0,0.05)" : "none"
                    }}
                  >
                    Đã có mã truy cập
                  </button>
                  <button
                    onClick={() => { setStudentAuthMode("signup"); setError(""); }}
                    style={{
                      padding: "5px 10px",
                      borderRadius: 4,
                      border: "none",
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: "pointer",
                      background: studentAuthMode === "signup" ? "#ffffff" : "transparent",
                      color: studentAuthMode === "signup" ? "#09090b" : "#71717a",
                      boxShadow: studentAuthMode === "signup" ? "0 1px 2px rgba(0,0,0,0.05)" : "none"
                    }}
                  >
                    Đăng ký mới
                  </button>
                </div>
              </div>

              {/* MODE A: EXISTING LOGIN */}
              {studentAuthMode === "login" && (
                <div>
                  <p style={{ color: "#52525b", fontSize: 13, lineHeight: 1.5, marginBottom: 16 }}>
                    Nhập mã truy cập bí mật đã được cấp để tiếp tục tiến độ thu âm của bạn.
                  </p>
                  <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                    Mã truy cập bí mật:
                    <input
                      style={styles.field}
                      placeholder="Nhập mã truy cập bí mật (Access Token)"
                      value={studentIdentifierInput}
                      onChange={(e) => setStudentIdentifierInput(e.target.value)}
                      onKeyDown={(e) => { if (e.key === "Enter") handleStudentLogin(); }}
                    />
                  </label>
                  <button
                    style={{ ...styles.btnPrimary, width: "100%", justifyContent: "center", marginTop: 4 }}
                    disabled={busy}
                    onClick={handleStudentLogin}
                  >
                    Vào phòng thu âm
                  </button>
                </div>
              )}

              {/* MODE B: NEW REGISTRATION */}
              {studentAuthMode === "signup" && (
                <div>
                  <p style={{ color: "#52525b", fontSize: 13, lineHeight: 1.5, marginBottom: 16 }}>
                    Đề tài nghiên cứu LiemWhisper thu thập ngữ liệu phát âm tiếng Việt có chêm xen thuật ngữ CNTT. Dữ liệu được mã hóa ẩn danh phục vụ mục đích học thuật.
                  </p>

                  <div style={{ background: "#f8fafc", padding: 12, borderRadius: 8, border: "1px solid #e2e8f0", marginBottom: 16 }}>
                    <label style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer", fontSize: 13, color: "#1e293b", lineHeight: 1.4 }}>
                      <input
                        type="checkbox"
                        checked={consent}
                        onChange={(e) => setConsent(e.target.checked)}
                        style={{ marginTop: 2 }}
                      />
                      <span>Tôi xác nhận tự nguyện tham gia thử nghiệm thu âm cho nghiên cứu học thuật LiemWhisper (Consent v1.0).</span>
                    </label>
                  </div>

                  <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                    Mã sinh viên hoặc Biệt danh:
                    <input
                      style={styles.field}
                      placeholder="Ví dụ: SE194007"
                      value={participantCode}
                      onChange={(e) => setParticipantCode(e.target.value)}
                    />
                  </label>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                      Mức độ hiểu môn học:
                      <select style={styles.field} value={familiarity} onChange={(e) => setFamiliarity(e.target.value)}>
                        <option>Đang học</option>
                        <option>Đã hoàn thành</option>
                        <option>Chưa học</option>
                        <option>Đã đi làm</option>
                      </select>
                    </label>

                    <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                      Tự đánh giá tiếng Anh:
                      <select style={styles.field} value={english} onChange={(e) => setEnglish(e.target.value)}>
                        <option>Bình thường</option>
                        <option>Tự tin</option>
                        <option>Rất tự tin</option>
                        <option>Hơi ngại</option>
                      </select>
                    </label>
                  </div>

                  <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12 }}>
                    <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                      Microphone sử dụng:
                      <select style={styles.field} value={mic} onChange={(e) => setMic(e.target.value)}>
                        <option>Điện thoại</option>
                        <option>Laptop</option>
                        <option>Tai nghe có mic</option>
                        <option>Micro rời</option>
                      </select>
                    </label>

                    <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                      Môi trường xung quanh:
                      <select style={styles.field} value={environment} onChange={(e) => setEnvironment(e.target.value)}>
                        <option>Phòng yên tĩnh</option>
                        <option>Có tiếng ồn nhẹ</option>
                      </select>
                    </label>
                  </div>

                  <button
                    style={{ ...styles.btnPrimary, width: "100%", justifyContent: "center", marginTop: 4 }}
                    disabled={!consent || busy}
                    onClick={handleStudentSignup}
                  >
                    Xác nhận & Bắt đầu thu âm
                  </button>
                </div>
              )}
            </div>
          )}

          {/* ADMIN AUTH CARD */}
          {authRoleTab === "admin" && (
            <div style={styles.card}>
              <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 8px", color: "#09090b" }}>Đăng nhập Quản trị viên</h2>
              <p style={{ color: "#52525b", fontSize: 13, lineHeight: 1.5, marginBottom: 16 }}>
                Dành cho giảng viên và nhóm nghiên cứu để quản lý danh sách câu hỏi, kiểm duyệt âm thanh và xuất bộ dữ liệu.
              </p>

              <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                Khóa quản trị (Admin API Key):
                <input
                  style={styles.field}
                  type="password"
                  placeholder="Nhập ADMIN_API_KEY"
                  value={adminKeyInput}
                  onChange={(e) => setAdminKeyInput(e.target.value)}
                  onKeyDown={(e) => { if (e.key === "Enter") handleAdminLogin(); }}
                />
              </label>

              <button
                style={{ ...styles.btnPrimary, width: "100%", justifyContent: "center", marginTop: 4 }}
                disabled={busy}
                onClick={handleAdminLogin}
              >
                Đăng nhập quản trị
              </button>
            </div>
          )}
        </section>
      )}

      {/* ========================================================================= */}
      {/* 2. STUDENT ROLE VIEW: STUDIO RECORDING ONLY */}
      {/* ========================================================================= */}
      {role === "student" && (
        <>
          {/* Student Account & Secret Access Token Card */}
          <section style={styles.card}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 14 }}>
              <div>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                  Khu vực tài khoản sinh viên
                </div>
                <div style={{ fontSize: 15, fontWeight: 700, color: "#09090b", marginTop: 2 }}>
                  Mã định danh: {participantInfo?.participant_code || "Học viên"}
                </div>
                <div style={{ fontSize: 12, color: "#71717a", marginTop: 4 }}>
                  Phiên đăng nhập lưu tạm trong localStorage (không sử dụng HttpOnly cookie).
                </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 8, background: "#f8fafc", padding: "8px 12px", borderRadius: 8, border: "1px solid #e2e8f0" }}>
                <span style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>Mã truy cập bí mật:</span>
                <code
                  style={{
                    fontFamily: "ui-monospace, monospace",
                    fontSize: 13,
                    fontWeight: 600,
                    background: "#ffffff",
                    border: "1px solid #cbd5e1",
                    padding: "3px 8px",
                    borderRadius: 4,
                    color: "#0f172a"
                  }}
                >
                  {maskSecretToken(token, showSecretToken)}
                </code>
                <button
                  type="button"
                  onClick={() => setShowSecretToken(!showSecretToken)}
                  style={{ ...styles.btnSecondary, padding: "4px 8px", fontSize: 12 }}
                >
                  {showSecretToken ? "Ẩn" : "Hiện"}
                </button>
                <button
                  type="button"
                  onClick={() => {
                    if (token && typeof navigator !== "undefined" && navigator.clipboard) {
                      navigator.clipboard.writeText(token).then(() => {
                        setCopiedToken(true);
                        setTimeout(() => setCopiedToken(false), 2000);
                      });
                    }
                  }}
                  style={{ ...styles.btnSecondary, padding: "4px 8px", fontSize: 12 }}
                >
                  {copiedToken ? "Đã chép" : "Sao chép"}
                </button>
              </div>
            </div>
          </section>

          {/* Course Selector & Progress Banner */}
          <section style={styles.card}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 14 }}>
              <div>
                <label style={{ fontSize: 12, fontWeight: 600, color: "#52525b", textTransform: "uppercase", letterSpacing: "0.04em" }}>
                  Môn học / Gói câu hỏi:
                </label>
                <div style={{ display: "flex", gap: 8, alignItems: "center", marginTop: 6, flexWrap: "wrap" }}>
                  <select
                    style={{ ...styles.field, marginTop: 0, marginBottom: 0, minWidth: 260 }}
                    value={selectedCourse}
                    onChange={(e) => {
                      const cid = e.target.value;
                      setSelectedCourse(cid);
                      if (token && cid) loadTasks(cid, token);
                    }}
                  >
                    {courses.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title} ({c.prompt_count || 0} câu)
                      </option>
                    ))}
                  </select>
                  <button
                    style={styles.btnSecondary}
                    onClick={() => loadTasks(selectedCourse, token)}
                    title="Tải lại danh sách câu hỏi"
                  >
                    <RefreshIcon size={13} />
                    <span>Làm mới câu hỏi</span>
                  </button>
                  <button
                    style={styles.btnSecondary}
                    onClick={refreshTasksSyncStatus}
                    disabled={syncRefreshing || isRecording}
                    title="Làm mới trạng thái đồng bộ mà không hủy bản thu âm đang ghi"
                  >
                    <RefreshIcon size={13} />
                    <span>{syncRefreshing ? "Đang đồng bộ..." : "Cập nhật đồng bộ Drive"}</span>
                  </button>
                </div>
              </div>

              <div style={{ textAlign: "right" }}>
                <div style={{ fontSize: 13, color: "#52525b" }}>
                  Tiến độ: <strong style={{ color: "#09090b" }}>{completedCount} / {tasks.length}</strong> câu ({progressPercent}%)
                </div>
                <div style={{ width: 180, height: 6, background: "#e4e4e7", borderRadius: 999, overflow: "hidden", marginTop: 6 }}>
                  <div style={{ width: `${progressPercent}%`, height: "100%", background: "#16a34a", transition: "width 0.3s ease" }} />
                </div>
              </div>
            </div>
          </section>

          {/* FOCUS RECORDING CARD */}
          {tasks.length === 0 ? (
            <div style={{ ...styles.card, textAlign: "center", padding: "40px 20px" }}>
              <p style={{ color: "#71717a", fontSize: 14 }}>Chưa có câu hỏi nào trong chủ đề này.</p>
            </div>
          ) : currentTask ? (
            <section style={{ ...styles.card, border: "1px solid #d4d4d8", boxShadow: "0 2px 8px rgba(0,0,0,0.04)" }}>
              {/* Header: Question Index & Status */}
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #f4f4f5", paddingBottom: 14, marginBottom: 20 }}>
                <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
                  <span style={{ fontSize: 16, fontWeight: 700, color: "#09090b" }}>
                    Câu {currentIndex + 1} trên {tasks.length}
                  </span>
                  {currentTask.recording_id ? (
                    <>
                      <span style={{ fontSize: 12, background: "#dcfce7", color: "#166534", padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>
                        Đã ghi âm
                      </span>
                      {(() => {
                        const syncInfo = getDriveSyncStatusInfo(currentTask.drive_sync_status, currentTask.drive_sync_message);
                        return (
                          <span
                            title={syncInfo.description}
                            style={{
                              fontSize: 12,
                              padding: "2px 8px",
                              borderRadius: 4,
                              fontWeight: 600,
                              background:
                                syncInfo.badgeStyle === "synced"
                                  ? "#dcfce7"
                                  : syncInfo.badgeStyle === "pending"
                                  ? "#fef3c7"
                                  : syncInfo.badgeStyle === "error"
                                  ? "#fee2e2"
                                  : "#f4f4f5",
                              color:
                                syncInfo.badgeStyle === "synced"
                                  ? "#166534"
                                  : syncInfo.badgeStyle === "pending"
                                  ? "#92400e"
                                  : syncInfo.badgeStyle === "error"
                                  ? "#991b1b"
                                  : "#71717a"
                            }}
                          >
                            {syncInfo.label}
                          </span>
                        );
                      })()}
                    </>
                  ) : (
                    <span style={{ fontSize: 12, background: "#f4f4f5", color: "#71717a", padding: "2px 8px", borderRadius: 4, fontWeight: 500 }}>
                      Chưa ghi âm
                    </span>
                  )}
                </div>

                <div style={{ display: "flex", gap: 6 }}>
                  <button
                    style={styles.btnSecondary}
                    disabled={currentIndex === 0 || isRecording}
                    onClick={() => {
                      clearRecordedAudio();
                      setCurrentIndex((i) => Math.max(0, i - 1));
                    }}
                  >
                    <ChevronLeftIcon size={14} />
                    <span>Trước</span>
                  </button>
                  <button
                    style={styles.btnSecondary}
                    disabled={currentIndex === tasks.length - 1 || isRecording}
                    onClick={() => {
                      clearRecordedAudio();
                      setCurrentIndex((i) => Math.min(tasks.length - 1, i + 1));
                    }}
                  >
                    <span>Tiếp</span>
                    <ChevronRightIcon size={14} />
                  </button>
                </div>
              </div>

              {/* PROMPT TEXT DISPLAY */}
              <div style={{ background: "#f8fafc", padding: "24px 20px", borderRadius: 8, border: "1px solid #f1f5f9", marginBottom: 24, textAlign: "center" }}>
                <div style={{ fontSize: 11, fontWeight: 700, color: "#64748b", textTransform: "uppercase", letterSpacing: "0.05em", marginBottom: 10 }}>
                  Văn bản cần đọc
                </div>
                <p style={{ fontSize: 20, fontWeight: 600, color: "#09090b", lineHeight: 1.7, margin: "8px 0 12px" }}>
                  {renderHighlightedText(currentTask.text, currentTask.target_terms)}
                </p>
                <p style={{ fontSize: 13, color: "#64748b", margin: 0, lineHeight: 1.5 }}>
                  Hướng dẫn: Đọc to, rõ ràng theo tốc độ tự nhiên. Phát âm thuật ngữ tiếng Anh theo thói quen giao tiếp kỹ thuật của bạn.
                </p>
              </div>

              {/* LIVE WAVEFORM VISUALIZER & TIMER */}
              <div style={{ display: "flex", flexDirection: "column", alignItems: "center", marginBottom: 20 }}>
                <canvas
                  ref={canvasRef}
                  width={280}
                  height={44}
                  style={{ background: "#f4f4f5", borderRadius: 6, marginBottom: 10, display: isRecording ? "block" : "none" }}
                />

                {isRecording && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8, color: "#dc2626", fontWeight: 700, fontSize: 16, fontFamily: "ui-monospace, monospace" }}>
                    <span style={{ width: 8, height: 8, borderRadius: "50%", background: "#dc2626" }} />
                    {Math.floor(recordingSeconds / 60).toString().padStart(2, "0")}:
                    {(recordingSeconds % 60).toString().padStart(2, "0")} / 00:45
                  </div>
                )}
              </div>

              {/* RECORDING CONTROLS */}
              <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                {!isRecording && !audioUrl && (
                  <button
                    style={styles.btnRecord}
                    disabled={busy}
                    onClick={() => startRecording(currentTask.id)}
                  >
                    <MicIcon size={16} />
                    <span>{currentTask.recording_id ? "Ghi âm lại" : "Bắt đầu ghi âm"}</span>
                  </button>
                )}

                {isRecording && (
                  <button style={styles.btnStop} onClick={stopRecording}>
                    <StopIcon size={14} color="#ffffff" />
                    <span>Dừng ghi âm</span>
                  </button>
                )}

                {audioUrl && !isRecording && (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, width: "100%" }}>
                    <audio controls src={audioUrl} style={{ width: "100%", maxWidth: 400 }} />
                    <div style={{ display: "flex", gap: 10 }}>
                      <button style={styles.btnSecondary} onClick={clearRecordedAudio}>
                        <RefreshIcon size={13} />
                        <span>Ghi lại</span>
                      </button>
                      <button
                        style={styles.btnSuccess}
                        disabled={busy}
                        onClick={() => uploadRecording(currentTask.id)}
                      >
                        <CheckIcon size={14} />
                        <span>Nộp bản ghi & Tiếp tục</span>
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* QUESTION PAGINATION STRIP */}
              <div style={{ marginTop: 28, borderTop: "1px solid #f4f4f5", paddingTop: 16 }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: "#71717a", marginBottom: 8 }}>
                  Danh sách câu:
                </div>
                <div style={{ display: "flex", gap: 5, flexWrap: "wrap" }}>
                  {tasks.map((t, idx) => (
                    <button
                      key={t.id}
                      disabled={isRecording}
                      onClick={() => {
                        clearRecordedAudio();
                        setCurrentIndex(idx);
                      }}
                      style={{
                        width: 30,
                        height: 30,
                        borderRadius: 6,
                        border: idx === currentIndex ? "1.5px solid #09090b" : "1px solid #e4e4e7",
                        background: t.recording_id ? "#16a34a" : idx === currentIndex ? "#f4f4f5" : "#ffffff",
                        color: t.recording_id ? "#ffffff" : idx === currentIndex ? "#09090b" : "#52525b",
                        fontWeight: 600,
                        fontSize: 12,
                        cursor: "pointer"
                      }}
                    >
                      {idx + 1}
                    </button>
                  ))}
                </div>
              </div>
            </section>
          ) : null}

          {/* CELEBRATION CARD WHEN ALL COMPLETED */}
          {tasks.length > 0 && completedCount === tasks.length && (
            <div style={{ ...styles.card, background: "#f0fdf4", border: "1px solid #bbf7d0", textAlign: "center", padding: "28px 20px" }}>
              <h3 style={{ color: "#166534", fontSize: 17, margin: "0 0 8px" }}>Hoàn thành phần thu âm</h3>
              <p style={{ color: "#15803d", fontSize: 13, margin: 0, lineHeight: 1.5 }}>
                Bạn đã nộp đủ bản ghi âm cho gói câu hỏi này. Dữ liệu đã được lưu trữ an toàn trên hệ thống phục vụ công tác nghiên cứu khoa học.
              </p>
              <div style={{ marginTop: 14 }}>
                <span style={{ fontSize: 12, padding: "4px 10px", background: "#dcfce7", color: "#166534", borderRadius: 4, fontWeight: 600 }}>
                  Mã định danh: {participantInfo?.participant_code}
                </span>
              </div>
            </div>
          )}

          {/* Account withdrawal option */}
          <div style={{ textAlign: "center", marginTop: 16 }}>
            <button
              onClick={handleWithdraw}
              style={{ background: "none", border: "none", color: "#71717a", fontSize: 12, cursor: "pointer", textDecoration: "underline" }}
            >
              Rút lại sự đồng ý và xóa các bản ghi âm của tôi
            </button>
          </div>
        </>
      )}

      {/* ========================================================================= */}
      {/* 3. ADMIN ROLE VIEW: CONTROL PANEL & REVIEWS ONLY */}
      {/* ========================================================================= */}
      {role === "admin" && (
        <>
          {/* Google Drive Status & Connection Panel */}
          <AdminDrivePanel
            apiBase={API}
            adminToken={adminKey}
            driveStatus={driveStatus}
            onStatusUpdated={(s) => setDriveStatus(s)}
          />

          {/* Admin Navigation Bar */}
          <section style={styles.card}>
            <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
              <div style={{ display: "flex", gap: 4, background: "#f4f4f5", padding: 3, borderRadius: 8, flexWrap: "wrap" }}>
                <button
                  style={{
                    padding: "7px 14px",
                    borderRadius: 6,
                    border: "none",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontSize: 13,
                    background: adminSubTab === "stats" ? "#ffffff" : "transparent",
                    color: adminSubTab === "stats" ? "#09090b" : "#71717a",
                    boxShadow: adminSubTab === "stats" ? "0 1px 2px rgba(0,0,0,0.06)" : "none"
                  }}
                  onClick={() => { setAdminSubTab("stats"); loadAdminStats(); }}
                >
                  Thống kê
                </button>
                <button
                  style={{
                    padding: "7px 14px",
                    borderRadius: 6,
                    border: "none",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontSize: 13,
                    background: adminSubTab === "prompts" ? "#ffffff" : "transparent",
                    color: adminSubTab === "prompts" ? "#09090b" : "#71717a",
                    boxShadow: adminSubTab === "prompts" ? "0 1px 2px rgba(0,0,0,0.06)" : "none"
                  }}
                  onClick={() => { setAdminSubTab("prompts"); loadAdminCourses(); }}
                >
                  Quản lý câu hỏi
                </button>
                <button
                  style={{
                    padding: "7px 14px",
                    borderRadius: 6,
                    border: "none",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontSize: 13,
                    background: adminSubTab === "reviews" ? "#ffffff" : "transparent",
                    color: adminSubTab === "reviews" ? "#09090b" : "#71717a",
                    boxShadow: adminSubTab === "reviews" ? "0 1px 2px rgba(0,0,0,0.06)" : "none"
                  }}
                  onClick={() => { setAdminSubTab("reviews"); loadReviews(); }}
                >
                  Kiểm duyệt âm thanh
                </button>
                <button
                  style={{
                    padding: "7px 14px",
                    borderRadius: 6,
                    border: "none",
                    fontWeight: 600,
                    cursor: "pointer",
                    fontSize: 13,
                    background: adminSubTab === "export" ? "#ffffff" : "transparent",
                    color: adminSubTab === "export" ? "#09090b" : "#71717a",
                    boxShadow: adminSubTab === "export" ? "0 1px 2px rgba(0,0,0,0.06)" : "none"
                  }}
                  onClick={() => setAdminSubTab("export")}
                >
                  Xuất dữ liệu
                </button>
              </div>

              <button
                style={styles.btnSecondary}
                onClick={() => {
                  loadAdminStats();
                  loadAdminCourses();
                  loadDriveStatus();
                  if (adminSubTab === "reviews") loadReviews();
                }}
              >
                <RefreshIcon size={13} />
                <span>Đồng bộ</span>
              </button>
            </div>
          </section>

          {/* SUBTAB 1: STATS */}
          {adminSubTab === "stats" && stats && (
            <section style={styles.card}>
              <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 16px" }}>Tổng quan tiến độ thu thập</h2>
              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(160px, 1fr))", gap: 12, marginBottom: 24 }}>
                <div style={{ background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
                  <div style={{ fontSize: 12, color: "#64748b" }}>Môn học</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#09090b", marginTop: 4 }}>{stats.total_courses}</div>
                </div>
                <div style={{ background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
                  <div style={{ fontSize: 12, color: "#64748b" }}>Câu hỏi xuất bản</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#09090b", marginTop: 4 }}>{stats.published_prompts}</div>
                </div>
                <div style={{ background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
                  <div style={{ fontSize: 12, color: "#64748b" }}>Người tham gia</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#09090b", marginTop: 4 }}>{stats.total_participants}</div>
                </div>
                <div style={{ background: "#f8fafc", padding: 14, borderRadius: 8, border: "1px solid #e2e8f0" }}>
                  <div style={{ fontSize: 12, color: "#64748b" }}>Bản ghi đã nộp</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#09090b", marginTop: 4 }}>{stats.total_recordings}</div>
                </div>
                <div style={{ background: "#f0fdf4", padding: 14, borderRadius: 8, border: "1px solid #bbf7d0" }}>
                  <div style={{ fontSize: 12, color: "#166534" }}>Đã chấp thuận</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#15803d", marginTop: 4 }}>{stats.approved_recordings}</div>
                </div>
                <div style={{ background: "#fefce8", padding: 14, borderRadius: 8, border: "1px solid #fef08a" }}>
                  <div style={{ fontSize: 12, color: "#854d0e" }}>Thời lượng duyệt (phút)</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#a16207", marginTop: 4 }}>{stats.approved_duration_minutes}m</div>
                </div>
              </div>

              <h3 style={{ fontSize: 14, fontWeight: 600, color: "#27272a", marginBottom: 12 }}>Tiến độ từng môn học:</h3>
              <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
                {stats.courses.map((c) => (
                  <div key={c.id} style={{ display: "flex", justifyContent: "space-between", padding: 12, background: "#f8fafc", borderRadius: 6, border: "1px solid #f1f5f9", alignItems: "center" }}>
                    <div>
                      <strong style={{ fontSize: 14, color: "#09090b" }}>{c.title}</strong>
                      <span style={{ fontSize: 12, color: "#71717a", marginLeft: 8 }}>({c.prompts_count} câu)</span>
                    </div>
                    <div style={{ fontSize: 13 }}>
                      <span style={{ color: "#16a34a", fontWeight: 600 }}>{c.approved_count} đã duyệt</span> /{" "}
                      <span style={{ color: "#71717a" }}>{c.recordings_count} đã nộp</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* SUBTAB 2: PROMPTS & COURSES MANAGEMENT */}
          {adminSubTab === "prompts" && (
            <>
              {/* Create Course */}
              <section style={styles.card}>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 14px" }}>1. Thêm môn học mới</h2>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 2fr auto", gap: 12, alignItems: "flex-end" }}>
                  <label style={{ fontSize: 13, fontWeight: 600 }}>
                    Tên môn học
                    <input
                      style={styles.field}
                      placeholder="Ví dụ: Software Testing (Kiểm thử phần mềm)"
                      value={newCourseTitle}
                      onChange={(e) => setNewCourseTitle(e.target.value)}
                    />
                  </label>
                  <label style={{ fontSize: 13, fontWeight: 600 }}>
                    Mô tả ngắn
                    <input
                      style={styles.field}
                      placeholder="Ví dụ: Thu thập thuật ngữ ISTQB & Code-switched Speech"
                      value={newCourseDesc}
                      onChange={(e) => setNewCourseDesc(e.target.value)}
                    />
                  </label>
                  <button style={{ ...styles.btnPrimary, marginBottom: 16 }} onClick={createCourse}>
                    Thêm môn
                  </button>
                </div>
              </section>

              {/* Bulk Import Prompts */}
              <section style={styles.card}>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 8px" }}>2. Nhập câu hỏi hàng loạt (Bulk Import)</h2>
                <p style={{ color: "#52525b", fontSize: 13, margin: "0 0 14px" }}>
                  Dán danh sách các câu tiếng Việt có chêm thuật ngữ kỹ thuật tiếng Anh (mỗi dòng một câu). Hệ thống tự động bóc tách các từ khóa kỹ thuật.
                </p>

                <label style={{ fontSize: 13, fontWeight: 600 }}>
                  Chọn môn học:
                  <select
                    style={styles.field}
                    value={bulkCourseId}
                    onChange={(e) => setBulkCourseId(e.target.value)}
                  >
                    {adminCourses.map((c) => (
                      <option key={c.id} value={c.id}>
                        {c.title}
                      </option>
                    ))}
                  </select>
                </label>

                <label style={{ fontSize: 13, fontWeight: 600 }}>
                  Danh sách câu (Mỗi dòng 1 câu):
                  <textarea
                    style={{ ...styles.field, minHeight: 120, fontFamily: "ui-monospace, monospace", fontSize: 13 }}
                    placeholder={"Giải thích khái niệm regression testing trong dự án.\nThực hiện boundary value analysis cho input tuổi từ 18 đến 60.\nUnit test là bước kiểm thử cơ bản nhất của lập trình viên."}
                    value={bulkText}
                    onChange={(e) => setBulkText(e.target.value)}
                  />
                </label>

                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12 }}>
                  <label style={{ display: "flex", alignItems: "center", gap: 8, fontSize: 13, cursor: "pointer", color: "#27272a" }}>
                    <input
                      type="checkbox"
                      checked={bulkPublish}
                      onChange={(e) => setBulkPublish(e.target.checked)}
                    />
                    <span>Xuất bản ngay cho người tham gia thu âm</span>
                  </label>
                  <button style={styles.btnPrimary} onClick={bulkImportPrompts}>
                    Nạp câu hỏi
                  </button>
                </div>
              </section>
            </>
          )}

          {/* SUBTAB 3: REVIEWS STUDIO */}
          {adminSubTab === "reviews" && (
            <section style={styles.card}>
              <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: 12, marginBottom: 16 }}>
                <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Kiểm duyệt bản ghi âm</h2>
                <div style={{ display: "flex", gap: 8 }}>
                  <select
                    style={{ ...styles.field, margin: 0, padding: "7px 12px", width: "auto" }}
                    value={reviewFilterStatus}
                    onChange={(e) => {
                      setReviewFilterStatus(e.target.value);
                      setTimeout(() => loadReviews(), 50);
                    }}
                  >
                    <option value="pending_review">Chờ duyệt (Pending)</option>
                    <option value="approved">Đã chấp thuận (Approved)</option>
                    <option value="rejected">Đã từ chối (Rejected)</option>
                    <option value="all">Tất cả</option>
                  </select>
                  <button style={styles.btnSecondary} onClick={loadReviews}>
                    <RefreshIcon size={13} />
                    <span>Làm mới</span>
                  </button>
                </div>
              </div>

              {reviewList.length === 0 ? (
                <p style={{ color: "#71717a", textAlign: "center", padding: "30px 0", fontSize: 14 }}>Không có bản ghi nào trong mục này.</p>
              ) : (
                <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
                  {reviewList.map((r) => (
                    <div
                      key={r.id}
                      style={{
                        padding: 16,
                        background: "#f8fafc",
                        border: "1px solid #e2e8f0",
                        borderRadius: 8
                      }}
                    >
                      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "flex-start", marginBottom: 6 }}>
                        <div>
                          <span style={{ fontSize: 13, fontWeight: 600, color: "#09090b" }}>{r.course_title}</span>
                          <span style={{ fontSize: 12, color: "#71717a", marginLeft: 8 }}>· Mã SV: {r.participant_code}</span>
                        </div>
                        <span
                          style={{
                            fontSize: 11,
                            padding: "2px 6px",
                            borderRadius: 4,
                            fontWeight: 600,
                            textTransform: "uppercase",
                            background: r.status === "approved" ? "#dcfce7" : r.status === "rejected" ? "#fee2e2" : "#fef3c7",
                            color: r.status === "approved" ? "#166534" : r.status === "rejected" ? "#991b1b" : "#92400e"
                          }}
                        >
                          {r.status === "approved" ? "Chấp thuận" : r.status === "rejected" ? "Từ chối" : "Chờ duyệt"}
                        </span>
                      </div>

                      <p style={{ fontSize: 15, fontWeight: 600, color: "#09090b", margin: "6px 0 10px", lineHeight: 1.5 }}>
                        {renderHighlightedText(r.text, r.target_terms)}
                      </p>

                      {/* Header-authenticated Blob Audio Stream Player */}
                      <div style={{ background: "#ffffff", padding: 10, borderRadius: 6, border: "1px solid #e2e8f0", marginBottom: 10, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
                        <AuthenticatedAudioPlayer
                          apiBase={API}
                          audioPath={`/api/v1/admin/recordings/${r.id}/audio`}
                          authHeader={{ name: "x-admin-key", value: adminKey }}
                          style={{ flex: 1, minWidth: 260 }}
                        />
                        <span style={{ fontSize: 12, color: "#71717a", fontFamily: "ui-monospace, monospace" }}>
                          {r.duration_seconds > 0 ? `${r.duration_seconds.toFixed(1)}s` : ""} · {r.format.toUpperCase()}
                        </span>
                      </div>

                      {/* Verbatim Transcript */}
                      <div style={{ marginBottom: 12 }}>
                        <div style={{ display: "flex", justifyContent: "space-between", marginBottom: 4 }}>
                          <label style={{ fontSize: 12, fontWeight: 600, color: "#475569" }}>
                            Bản chép lời thực tế (Verbatim Transcript):
                          </label>
                          <button
                            style={{ fontSize: 12, color: "#2563eb", background: "none", border: "none", cursor: "pointer", fontWeight: 500 }}
                            onClick={() => setReviewTranscripts((prev) => ({ ...prev, [r.id]: r.text }))}
                          >
                            Điền câu mẫu
                          </button>
                        </div>
                        <textarea
                          style={{ ...styles.field, minHeight: 50, margin: 0, fontSize: 13 }}
                          value={reviewTranscripts[r.id] ?? r.transcript ?? r.text}
                          onChange={(e) => setReviewTranscripts((prev) => ({ ...prev, [r.id]: e.target.value }))}
                        />
                      </div>

                      {/* Review Buttons */}
                      <div style={{ display: "flex", gap: 8, justifyContent: "flex-end" }}>
                        <button
                          style={styles.btnDanger}
                          onClick={() => submitReview(r.id, "rejected")}
                        >
                          <CrossIcon size={12} color="#dc2626" />
                          <span>Từ chối</span>
                        </button>
                        <button
                          style={styles.btnSecondary}
                          onClick={() => submitReview(r.id, "rerecord")}
                        >
                          <RefreshIcon size={12} />
                          <span>Yêu cầu thu lại</span>
                        </button>
                        <button
                          style={styles.btnSuccess}
                          onClick={() => submitReview(r.id, "approved")}
                        >
                          <CheckIcon size={13} />
                          <span>Chấp thuận</span>
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </section>
          )}

          {/* SUBTAB 4: DATASET EXPORT */}
          {adminSubTab === "export" && (
            <section style={styles.card}>
              <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 8px" }}>Xuất bộ dữ liệu nghiên cứu</h2>
              <p style={{ color: "#52525b", fontSize: 13, lineHeight: 1.5, margin: "0 0 20px" }}>
                Chỉ các bản ghi <strong>đã được chấp thuận (Approved)</strong> và có sự đồng ý của người tham gia mới được đưa vào bộ dữ liệu xuất bản.
                Dữ liệu bao gồm định danh ẩn danh, thời lượng, checksum SHA-256, từ khóa kỹ thuật và bản chép lời chuẩn xác.
              </p>

              <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))", gap: 14 }}>
                <button
                  type="button"
                  onClick={() => handleExportDownload("/api/v1/admin/export/manifest.json", "manifest.json")}
                  disabled={busy}
                  style={{
                    background: "#ffffff",
                    padding: 18,
                    borderRadius: 8,
                    border: "1px solid #e4e4e7",
                    textAlign: "left",
                    cursor: busy ? "wait" : "pointer",
                    width: "100%"
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <DownloadIcon size={15} />
                    <strong style={{ color: "#09090b", fontSize: 14 }}>Manifest JSON</strong>
                  </div>
                  <div style={{ fontSize: 12, color: "#71717a" }}>Metadata cấu trúc JSON (Header-auth)</div>
                </button>

                <button
                  type="button"
                  onClick={() => handleExportDownload("/api/v1/admin/export/manifest.csv", "manifest.csv")}
                  disabled={busy}
                  style={{
                    background: "#ffffff",
                    padding: 18,
                    borderRadius: 8,
                    border: "1px solid #e4e4e7",
                    textAlign: "left",
                    cursor: busy ? "wait" : "pointer",
                    width: "100%"
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <DownloadIcon size={15} />
                    <strong style={{ color: "#09090b", fontSize: 14 }}>Manifest CSV</strong>
                  </div>
                  <div style={{ fontSize: 12, color: "#71717a" }}>Bảng tính Excel / CSV (Header-auth)</div>
                </button>

                <button
                  type="button"
                  onClick={() => handleExportDownload("/api/v1/admin/export/archive.zip", "archive.zip")}
                  disabled={busy}
                  style={{
                    background: "#09090b",
                    padding: 18,
                    borderRadius: 8,
                    border: "1px solid #09090b",
                    textAlign: "left",
                    cursor: busy ? "wait" : "pointer",
                    width: "100%"
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 4 }}>
                    <DownloadIcon size={15} color="#ffffff" />
                    <strong style={{ color: "#ffffff", fontSize: 14 }}>Trọn gói ZIP</strong>
                  </div>
                  <div style={{ fontSize: 12, color: "#a1a1aa" }}>Tất cả audio và manifests (Header-auth)</div>
                </button>
              </div>
            </section>
          )}
        </>
      )}

      {/* Clean Academic Footer */}
      <footer style={{ marginTop: 40, borderTop: "1px solid #e5e7eb", paddingTop: 16, textAlign: "center", color: "#a1a1aa", fontSize: 12 }}>
        LiemWhisper Research Platform · Cross-Modal Contrastive Learning for Code-Switched Speech · Phục vụ NCKH
      </footer>
    </main>
  );
}
