"use client";

import { useEffect, useRef, useState } from "react";
import { getDriveSyncStatusInfo, isBothSaved } from "../lib/sync";
import {
  validateNoSecretInUrl,
  sanitizeApiError,
  sanitizeNotice,
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
  email?: string;
  name?: string;
  consent_version: string;
  total_recordings: number;
  completed_at?: number;
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

function ShieldIcon({ size = 14, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z" />
    </svg>
  );
}

function UsersIcon({ size = 14, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  );
}

function TrashIcon({ size = 14, color = "currentColor" }: { size?: number; color?: string }) {
  return (
    <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke={color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="3 6 5 6 21 6" />
      <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
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

  const [adminKeyInput, setAdminKeyInput] = useState("");

  // Student session data
  const [token, setToken] = useState("");
  const [participantInfo, setParticipantInfo] = useState<ParticipantMe | null>(null);

  // Google onboarding form state
  const [consent, setConsent] = useState(false);
  const [participantCode, setParticipantCode] = useState("");
  const [className, setClassName] = useState("");
  const [referringLecturer, setReferringLecturer] = useState("");
  const [english, setEnglish] = useState("");
  const [mic, setMic] = useState("Tai nghe có mic");
  const [environment, setEnvironment] = useState("Phòng yên tĩnh");
  const [birthYear, setBirthYear] = useState<number>(2004);
  const [academicYear, setAcademicYear] = useState("Năm 3");
  const [environmentNoise, setEnvironmentNoise] = useState("Rất yên tĩnh (Phòng kín)");
  const [accentRegion, setAccentRegion] = useState("Miền Bắc");

  // Google Auth & Onboarding state
  const [googleUser, setGoogleUser] = useState<{
    temp_token: string;
    email: string;
    name: string;
    picture?: string;
    suggested_code?: string;
  } | null>(null);
  const [googleOnboarding, setGoogleOnboarding] = useState(false);


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
  const [isCompletedSession, setIsCompletedSession] = useState(false);
  const [completionDetails, setCompletionDetails] = useState<{ total: number; email: string } | null>(null);
  const isParticipantCompleted = Boolean(
    (participantInfo?.completed_at && participantInfo.completed_at > 0) ||
    completionDetails
  );

  // Status & loading
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  // Admin state (Memory only, never persisted to localStorage)
  const [adminKey, setAdminKey] = useState("");
  const [adminSubTab, setAdminSubTab] = useState<"stats" | "prompts" | "admins" | "export">("stats");
  const [isGoogleAdmin, setIsGoogleAdmin] = useState(false);
  const [adminUsersList, setAdminUsersList] = useState<Array<{ email: string; created_at: number; created_by: string; linked: boolean; name: string; is_env: boolean }>>([]);
  const [adminParticipantsList, setAdminParticipantsList] = useState<Array<{ id: string; participant_code: string; email: string; name: string; is_admin?: number }>>([]);
  const [newAdminEmailInput, setNewAdminEmailInput] = useState("");
  const [addingAdmin, setAddingAdmin] = useState(false);
  const [loadingAdmins, setLoadingAdmins] = useState(false);
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [driveStatus, setDriveStatus] = useState<DriveStatusResponse | null>(null);
  const [adminCourses, setAdminCourses] = useState<any[]>([]);
  const [newCourseTitle, setNewCourseTitle] = useState("");
  const [newCourseDesc, setNewCourseDesc] = useState("");
  const [bulkCourseId, setBulkCourseId] = useState("");
  const [bulkText, setBulkText] = useState("");
  const [bulkPublish, setBulkPublish] = useState(true);

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
      loadAdminAdmins(savedAdminSession);
      loadAdminParticipants(savedAdminSession);
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

  // Initialize Google Identity Services
  useEffect(() => {
    if (typeof window === "undefined") return;
    const clientId = process.env.NEXT_PUBLIC_GOOGLE_CLIENT_ID || "";

    const setupGoogle = () => {
      const google = (window as any).google;
      if (!google?.accounts?.id) return;
      try {
        google.accounts.id.initialize({
          client_id: clientId || "1028775217424-demo.apps.googleusercontent.com",
          callback: (response: any) => {
            if (response?.credential) {
              handleGoogleCallback(response.credential);
            }
          }
        });
        const container = document.getElementById("google-signin-btn-container");
        if (container) {
          container.innerHTML = "";
          google.accounts.id.renderButton(container, {
            theme: "outline",
            size: "large",
            width: 320,
            text: "signin_with",
            shape: "rectangular",
            logo_alignment: "left"
          });
        }
      } catch (err) {
        console.warn("Google Sign-In init error:", err);
      }
    };

    if ((window as any).google?.accounts?.id) {
      setupGoogle();
    } else {
      const interval = setInterval(() => {
        if ((window as any).google?.accounts?.id) {
          clearInterval(interval);
          setupGoogle();
        }
      }, 300);
      return () => clearInterval(interval);
    }
  }, [authRoleTab, googleOnboarding]);

  function cleanupMedia(releasePreview = true) {
    if (timerRef.current) clearInterval(timerRef.current);
    if (animFrameRef.current) cancelAnimationFrame(animFrameRef.current);
    streamRef.current?.getTracks().forEach((x) => x.stop());
    streamRef.current = null;
    if (audioContextRef.current && audioContextRef.current.state !== "closed") {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (releasePreview && urlRef.current) {
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
      if (data.completed_at && data.completed_at > 0) {
        setIsCompletedSession(true);
        setCompletionDetails({
          total: data.total_recordings,
          email: data.email || data.survey?.email || ""
        });
      }
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

  async function handleGoogleCallback(credential: string) {
    if (!credential) return;
    setBusy(true);
    setError("");
    try {
      const res = await request("/api/v1/auth/google", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ credential })
      });

      if (res.is_admin && res.admin_token) {
        saveAdminSession(res.admin_token);
        setAdminKey(res.admin_token);
        setIsGoogleAdmin(true);
        cleanLegacyAdminStorage();
      }

      if (res.needs_onboarding) {
        setGoogleUser({
          temp_token: res.temp_token,
          email: res.email,
          name: res.name,
          picture: res.picture,
          suggested_code: res.suggested_code || ""
        });
        setParticipantCode(res.suggested_code || "");
        setEnglish("");
        setClassName("");
        setReferringLecturer("");
        setConsent(false);
        setGoogleOnboarding(true);
        if (res.is_admin) {
          setNotice(`Tài khoản Google (${res.email}) có quyền Quản trị viên. Bạn có thể vào ngay Bảng Quản trị hoặc hoàn thành khảo sát.`);
        }
      } else {
        setToken(res.participant_token);
        localStorage.setItem("liemwhisper_token", res.participant_token);
        if (res.is_admin) {
          localStorage.setItem("liemwhisper_role", "admin");
          setRole("admin");
          setNotice(`Đăng nhập Google thành công với quyền Quản trị viên! Xin chào ${res.name || res.email}!`);
          await loadAdminStats(res.admin_token);
          await loadAdminCourses(res.admin_token);
          await loadAdminAdmins(res.admin_token);
          await loadAdminParticipants(res.admin_token);
          await loadDriveStatus(res.admin_token);
        } else {
          localStorage.setItem("liemwhisper_role", "student");
          setRole("student");
          setNotice(`Đăng nhập Google thành công. Xin chào ${res.name || res.participant_code}!`);

          await loadParticipantMe(res.participant_token);
          const cList = await loadCourses();
          const cid = selectedCourse || (cList.length > 0 ? cList[0].id : "");
          if (cid) {
            setSelectedCourse(cid);
            loadTasks(cid, res.participant_token);
          }
        }
      }
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  async function handleCompleteGoogleOnboard() {
    if (!consent) {
      setError("Vui lòng xác nhận tự nguyện tham gia nghiên cứu (Consent v1.0).");
      return;
    }
    if (!english) {
      setError("Vui lòng chọn trình độ tiếng Anh của bạn (hoặc Chưa rõ).");
      return;
    }
    if (!googleUser?.temp_token) {
      setError("Phiên Google không hợp lệ hoặc đã hết hạn. Vui lòng đăng nhập lại Google.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await request("/api/v1/auth/google/onboard", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          temp_token: googleUser.temp_token,
          consent: true,
          consent_version: "v1.0",
          participant_code: participantCode.trim(),
          english_level: english,
          class_name: className.trim(),
          referring_lecturer: referringLecturer.trim(),
          accent_region: accentRegion,
          birth_year: Number(birthYear) || 2004,
          academic_year: academicYear,
          microphone: mic,
          environment: environmentNoise || environment
        })
      });

      setToken(res.participant_token);
      localStorage.setItem("liemwhisper_token", res.participant_token);
      if (res.is_admin && res.admin_token) {
        saveAdminSession(res.admin_token);
        setAdminKey(res.admin_token);
        setIsGoogleAdmin(true);
      }
      localStorage.setItem("liemwhisper_role", "student");
      setRole("student");
      setGoogleOnboarding(false);
      setNotice(`Đăng ký thành công! Mã định danh: ${res.participant_code}.`);

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
      await loadAdminAdmins(sessionToken);
      await loadAdminParticipants(sessionToken);
      await loadDriveStatus(sessionToken);
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
    }
  }

  async function handleCompleteSession() {
    if (isParticipantCompleted) {
      setIsCompletedSession(true);
      return;
    }

    const recordedCount = tasks.filter((t) => Boolean(t.recording_id)).length;
    if (recordedCount === 0) {
      alertError("Bạn chưa thu âm câu nào. Vui lòng ghi âm ít nhất một câu trước khi hoàn thành.");
      return;
    }

    const email = participantInfo?.email || participantInfo?.survey?.email || "";
    const confirmMsg =
      recordedCount < tasks.length
        ? `Bạn đã hoàn thành ${recordedCount}/${tasks.length} câu. Bạn có chắc chắn muốn kết thúc bài thi ngay bây giờ? Thư cảm ơn sẽ được gửi đến ${email || "email của bạn"}.`
        : `Bạn đã hoàn thành toàn bộ ${recordedCount}/${tasks.length} câu hỏi. Xác nhận kết thúc bài thi và nhận email cảm ơn từ ban nghiên cứu?`;

    if (!confirm(confirmMsg)) return;

    setBusy(true);
    setError("");
    setNotice("");
    try {
      const res = await request("/api/v1/participants/complete", {
        method: "POST",
        headers: { "x-participant-token": token }
      });
      setIsCompletedSession(true);
      setCompletionDetails({
        total: res.total_recordings || recordedCount,
        email: res.email || email
      });
      setParticipantInfo((prev) =>
        prev ? { ...prev, completed_at: res.completed_at || Math.floor(Date.now() / 1000) } : prev
      );
      setNotice("Chúc mừng bạn đã hoàn tất bài thi! Thư cảm ơn đã được gửi đến email của bạn.");
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
    setIsGoogleAdmin(false);
    setAdminUsersList([]);
    setAdminParticipantsList([]);
    setGoogleUser(null);
    setGoogleOnboarding(false);
    setParticipantInfo(null);
    setDriveStatus(null);
    setTasks([]);
    clearRecordedAudio();
    setIsCompletedSession(false);
    setCompletionDetails(null);
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
    if (typeof isParticipantCompleted !== "undefined" && isParticipantCompleted) {
      alertError("Bài thi đã hoàn thành. Bạn đang ở chế độ xem lại nên không thể ghi âm thêm.");
      return;
    }
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

        // Stop microphone resources without invalidating the playback preview.
        cleanupMedia(false);
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
    if (typeof isParticipantCompleted !== "undefined" && isParticipantCompleted) {
      setError("Bài thi đã hoàn thành. Bạn không thể nộp thêm hoặc sửa đổi bản ghi âm.");
      return;
    }
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
                status: res.status || "approved",
                drive_sync_status: driveSyncStatus,
                drive_sync_message: driveSyncMsg
              }
            : t
        )
      );

      setNotice(`Đã lưu bản ghi âm câu ${currentIndex + 1} thành công!`);

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

  async function loadAdminAdmins(keyOverride?: string) {
    const k = keyOverride || adminKey || getAdminSession();
    if (!k) return;
    setLoadingAdmins(true);
    try {
      const data = await request("/api/v1/admin/admins", {
        headers: { "x-admin-key": k }
      });
      setAdminUsersList(data.admins || []);
    } catch {
      // Non-blocking
    } finally {
      setLoadingAdmins(false);
    }
  }

  async function loadAdminParticipants(keyOverride?: string) {
    const k = keyOverride || adminKey || getAdminSession();
    if (!k) return;
    try {
      const data = await request("/api/v1/admin/participants", {
        headers: { "x-admin-key": k }
      });
      setAdminParticipantsList(data.participants || []);
    } catch {
      // Non-blocking
    }
  }

  async function handleAddAdmin(emailToAdd?: string) {
    const target = (emailToAdd || newAdminEmailInput).trim().toLowerCase();
    if (!target) {
      setError("Vui lòng nhập địa chỉ Gmail để cấp quyền Quản trị viên.");
      return;
    }
    const k = adminKey || getAdminSession();
    if (!k) {
      setError("Phiên Quản trị viên không hợp lệ. Vui lòng đăng nhập lại.");
      return;
    }
    setAddingAdmin(true);
    setError("");
    try {
      const res = await request("/api/v1/admin/admins", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "x-admin-key": k
        },
        body: JSON.stringify({ email: target })
      });
      setNotice(res.message || `Đã cấp quyền Quản trị viên thành công cho ${target}.`);
      setNewAdminEmailInput("");
      await loadAdminAdmins(k);
      await loadAdminParticipants(k);
    } catch (e) {
      alertError(e);
    } finally {
      setAddingAdmin(false);
    }
  }

  async function handleRemoveAdmin(email: string) {
    if (!confirm(`Bạn có chắc chắn muốn thu hồi quyền Quản trị viên của email "${email}"?`)) {
      return;
    }
    const k = adminKey || getAdminSession();
    if (!k) {
      setError("Phiên Quản trị viên không hợp lệ. Vui lòng đăng nhập lại.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      const res = await request(`/api/v1/admin/admins/${encodeURIComponent(email)}`, {
        method: "DELETE",
        headers: { "x-admin-key": k }
      });
      setNotice(res.message || `Đã thu hồi quyền Quản trị viên của ${email}.`);
      await loadAdminAdmins(k);
      await loadAdminParticipants(k);
    } catch (e) {
      alertError(e);
    } finally {
      setBusy(false);
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
          <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
            {(adminKey || isGoogleAdmin || getAdminSession()) && (
              <div style={{ display: "flex", gap: 6 }}>
                {role === "admin" && token && (
                  <button
                    type="button"
                    onClick={() => {
                      setRole("student");
                      const cid = selectedCourse || (courses.length > 0 ? courses[0].id : "");
                      if (cid && token) loadTasks(cid, token);
                    }}
                    style={{
                      ...styles.btnSecondary,
                      padding: "6px 12px",
                      fontSize: 13,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      background: "#f0fdf4",
                      color: "#166534",
                      borderColor: "#bbf7d0"
                    }}
                  >
                    <MicIcon size={13} color="#166534" />
                    <span>Chế độ Thu âm</span>
                  </button>
                )}
                {role === "student" && (
                  <button
                    type="button"
                    onClick={() => {
                      setRole("admin");
                      const k = adminKey || getAdminSession();
                      if (k) {
                        loadAdminStats(k);
                        loadAdminCourses(k);
                        loadAdminAdmins(k);
                        loadAdminParticipants(k);
                        loadDriveStatus(k);
                      }
                    }}
                    style={{
                      ...styles.btnSecondary,
                      padding: "6px 12px",
                      fontSize: 13,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6,
                      background: "#eff6ff",
                      color: "#1d4ed8",
                      borderColor: "#bfdbfe"
                    }}
                  >
                    <ShieldIcon size={13} color="#1d4ed8" />
                    <span>Trang Quản trị</span>
                  </button>
                )}
              </div>
            )}

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
              <span>{role === "admin" ? (isGoogleAdmin && googleUser?.name ? `Admin: ${googleUser.name}` : "Quản trị viên") : `Sinh viên: ${participantInfo?.participant_code || "Người tham gia"}`}</span>
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
              {googleOnboarding && googleUser ? (
                /* ================= GOOGLE ONBOARDING FORM ================= */
                <div>
                  <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", borderBottom: "1px solid #f4f4f5", paddingBottom: 14, marginBottom: 16 }}>
                    <div>
                      <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0, color: "#09090b" }}>
                        Hoàn tất thông tin đăng ký
                      </h2>
                      <p style={{ margin: "4px 0 0", fontSize: 12, color: "#71717a" }}>
                        Bổ sung thông tin người tham gia để bắt đầu thu âm
                      </p>
                    </div>
                    <button
                      onClick={() => { setGoogleOnboarding(false); setGoogleUser(null); setError(""); }}
                      style={{
                        padding: "5px 10px",
                        borderRadius: 6,
                        border: "1px solid #e4e4e7",
                        background: "#ffffff",
                        fontSize: 12,
                        color: "#71717a",
                        cursor: "pointer"
                      }}
                    >
                      Đổi tài khoản
                    </button>
                  </div>

                  {/* Google Profile Badge */}
                  <div style={{ display: "flex", alignItems: "center", gap: 12, background: "#f8fafc", border: "1px solid #e2e8f0", borderRadius: 8, padding: "10px 14px", marginBottom: 16 }}>
                    {googleUser.picture ? (
                      <img src={googleUser.picture} alt="" style={{ width: 36, height: 36, borderRadius: "50%" }} />
                    ) : (
                      <div style={{ width: 36, height: 36, borderRadius: "50%", background: "#4285F4", color: "#ffffff", display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 700, fontSize: 15 }}>
                        {(googleUser.name || googleUser.email)[0].toUpperCase()}
                      </div>
                    )}
                    <div style={{ flex: 1, minWidth: 0 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#0f172a", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {googleUser.name || "Tài khoản Google"}
                      </div>
                      <div style={{ fontSize: 12, color: "#64748b", whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>
                        {googleUser.email}
                      </div>
                    </div>
                    <span style={{ fontSize: 11, background: "#dcfce7", color: "#166534", padding: "3px 8px", borderRadius: 100, fontWeight: 600 }}>
                      Đã xác thực Google
                    </span>
                  </div>

                  {isGoogleAdmin && (
                    <div style={{
                      background: "#eff6ff",
                      border: "1px solid #bfdbfe",
                      borderRadius: 8,
                      padding: "12px 14px",
                      marginBottom: 16,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "space-between",
                      gap: 12,
                      flexWrap: "wrap"
                    }}>
                      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                        <ShieldIcon size={18} color="#2563eb" />
                        <div>
                          <div style={{ fontWeight: 600, color: "#1e40af", fontSize: 13 }}>
                            Tài khoản có quyền Quản trị viên (Admin)
                          </div>
                          <div style={{ color: "#3b82f6", fontSize: 12 }}>
                            Bạn có thể truy cập Bảng Quản trị ngay mà không cần hoàn tất khảo sát.
                          </div>
                        </div>
                      </div>
                      <button
                        type="button"
                        onClick={() => {
                          setGoogleOnboarding(false);
                          setRole("admin");
                          const k = adminKey || getAdminSession();
                          if (k) {
                            loadAdminStats(k);
                            loadAdminCourses(k);
                            loadAdminAdmins(k);
                            loadAdminParticipants(k);
                            loadDriveStatus(k);
                          }
                        }}
                        style={{
                          ...styles.btnPrimary,
                          padding: "6px 14px",
                          fontSize: 12,
                          background: "#2563eb",
                          whiteSpace: "nowrap"
                        }}
                      >
                        Vào Bảng Quản trị 👉
                      </button>
                    </div>
                  )}

                  <p style={{ color: "#52525b", fontSize: 13, lineHeight: 1.5, marginBottom: 16 }}>
                    Đề tài nghiên cứu LiemWhisper thu thập ngữ liệu phát âm tiếng Việt có chêm xen thuật ngữ CNTT. Dữ liệu được mã hóa ẩn danh phục vụ mục đích học thuật.
                  </p>

                  {/* Consent Checkbox */}
                  <div style={{ background: "#f0fdf4", border: "1px solid #bbf7d0", borderRadius: 8, padding: 12, marginBottom: 16 }}>
                    <label style={{ display: "flex", alignItems: "flex-start", gap: 10, cursor: "pointer", fontSize: 13, color: "#166534", lineHeight: 1.4 }}>
                      <input
                        type="checkbox"
                        checked={consent}
                        onChange={(e) => setConsent(e.target.checked)}
                        style={{ marginTop: 2 }}
                      />
                      <span>Tôi xác nhận tự nguyện tham gia thử nghiệm thu âm cho nghiên cứu học thuật LiemWhisper (Consent v1.0).</span>
                    </label>
                  </div>

                  <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a", display: "block", marginBottom: 14 }}>
                    Trình độ tiếng Anh (CEFR) <span style={{ fontWeight: 400, color: "#52525b" }}>(Bắt buộc):</span>
                    <select name="english_level" required style={styles.field} value={english} onChange={(e) => setEnglish(e.target.value)}>
                      <option value="" disabled>Chọn trình độ tiếng Anh</option>
                      <option value="A1">A1</option>
                      <option value="A2">A2</option>
                      <option value="B1">B1</option>
                      <option value="B2">B2</option>
                      <option value="C1">C1</option>
                      <option value="C2">C2</option>
                      <option value="Chưa rõ">Chưa rõ</option>
                    </select>
                  </label>

                  {/* Mã sinh viên (Không bắt buộc) */}
                  <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a", display: "block", marginBottom: 14 }}>
                    MSSV / Mã sinh viên <span style={{ fontWeight: 400, color: "#71717a" }}>(Không bắt buộc):</span>
                    <input
                      style={styles.field}
                      name="participant_code"
                      maxLength={60}
                      placeholder="Ví dụ: SE194007 (để trống hệ thống tự cấp mã ẩn danh)"
                      value={participantCode}
                      onChange={(e) => setParticipantCode(e.target.value)}
                    />
                  </label>

                  <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a", display: "block", marginBottom: 14 }}>
                    Lớp <span style={{ fontWeight: 400, color: "#71717a" }}>(Không bắt buộc):</span>
                    <input
                      name="class_name"
                      maxLength={100}
                      style={styles.field}
                      placeholder="Ví dụ: SE19"
                      value={className}
                      onChange={(e) => setClassName(e.target.value)}
                    />
                  </label>

                  <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a", display: "block", marginBottom: 14 }}>
                    Giảng viên giới thiệu <span style={{ fontWeight: 400, color: "#71717a" }}>(Không bắt buộc):</span>
                    <input
                      name="referring_lecturer"
                      maxLength={150}
                      style={styles.field}
                      placeholder="Họ tên giảng viên giới thiệu"
                      value={referringLecturer}
                      onChange={(e) => setReferringLecturer(e.target.value)}
                    />
                  </label>

                  {/* Giọng vùng miền & Năm sinh */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 200px), 1fr))", gap: 12, marginBottom: 14 }}>
                    <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                      Giọng vùng miền:
                      <select style={styles.field} value={accentRegion} onChange={(e) => setAccentRegion(e.target.value)}>
                        <option>Miền Bắc</option>
                        <option>Miền Trung</option>
                        <option>Miền Nam</option>
                      </select>
                    </label>

                    <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                      Năm sinh:
                      <select style={styles.field} value={birthYear} onChange={(e) => setBirthYear(Number(e.target.value))}>
                        <option value={2006}>2006 (18-19 tuổi)</option>
                        <option value={2005}>2005 (19-20 tuổi)</option>
                        <option value={2004}>2004 (20-21 tuổi)</option>
                        <option value={2003}>2003 (21-22 tuổi)</option>
                        <option value={2002}>2002 (22-23 tuổi)</option>
                        <option value={2001}>2001</option>
                        <option value={2000}>2000 trở về trước</option>
                      </select>
                    </label>
                  </div>

                  {/* Khóa / Năm học & Microphone */}
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(100%, 200px), 1fr))", gap: 12, marginBottom: 14 }}>
                    <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                      Khóa / Năm học:
                      <select style={styles.field} value={academicYear} onChange={(e) => setAcademicYear(e.target.value)}>
                        <option>Năm 1</option>
                        <option>Năm 2</option>
                        <option>Năm 3</option>
                        <option>Năm 4</option>
                        <option>Đã tốt nghiệp / Đi làm</option>
                      </select>
                    </label>

                    <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a" }}>
                      Microphone sử dụng:
                      <select style={styles.field} value={mic} onChange={(e) => setMic(e.target.value)}>
                        <option>Điện thoại</option>
                        <option>Laptop</option>
                        <option>Tai nghe có mic</option>
                        <option>Micro rời chuyên dụng</option>
                      </select>
                    </label>
                  </div>

                  {/* Môi trường xung quanh */}
                  <label style={{ fontSize: 13, fontWeight: 600, color: "#27272a", display: "block", marginBottom: 18 }}>
                    Môi trường xung quanh:
                    <select style={styles.field} value={environmentNoise} onChange={(e) => { setEnvironmentNoise(e.target.value); setEnvironment(e.target.value); }}>
                      <option>Phòng yên tĩnh</option>
                      <option>Có tiếng ồn nhẹ</option>
                      <option>Quán cafe / nhiều tạp âm</option>
                    </select>
                  </label>

                  <button
                    style={{ ...styles.btnPrimary, width: "100%", justifyContent: "center", height: 42 }}
                    disabled={!consent || !english || busy}
                    onClick={handleCompleteGoogleOnboard}
                  >
                    {busy ? "Đang xử lý..." : "Xác nhận & Bắt đầu thu âm"}
                  </button>
                </div>
              ) : (
                /* ================= GOOGLE-ONLY PARTICIPANT LOGIN ================= */
                <div>
                  <div style={{ textAlign: "center", marginBottom: 20 }}>
                    <h2 style={{ fontSize: 18, fontWeight: 700, margin: "0 0 6px", color: "#09090b" }}>
                      Đăng nhập tham gia thu âm
                    </h2>
                    <p style={{ margin: 0, fontSize: 13, color: "#71717a", lineHeight: 1.5 }}>
                      Sử dụng tài khoản Google cá nhân để bắt đầu và tự động lưu giữ tiến độ thu âm của bạn
                    </p>
                  </div>

                  {/* Google Login Section */}
                  <div style={{ marginBottom: 18, display: "flex", flexDirection: "column", alignItems: "center", gap: 10 }}>
                    <div id="google-signin-btn-container" style={{ width: "100%", minHeight: 44, display: "flex", justifyContent: "center" }} />


                  </div>

                </div>
              )}
            </div>
          )}

          {/* ADMIN AUTH CARD */}
          {authRoleTab === "admin" && (
            <div style={styles.card}>
              <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 8px", color: "#09090b" }}>Đăng nhập Quản trị viên</h2>
              <p style={{ color: "#52525b", fontSize: 13, lineHeight: 1.5, marginBottom: 16 }}>
                Dành cho giảng viên và nhóm nghiên cứu để quản lý danh sách câu hỏi, theo dõi tiến độ và xuất bộ dữ liệu.
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
          {/* Student Account Card */}
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
                  Tiến độ được lưu theo tài khoản Google. Đăng nhập lại bằng cùng tài khoản để tiếp tục.
                </div>
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
                    onClick={async () => {
                      const cList = await loadCourses();
                      const cid = selectedCourse || (cList.length > 0 ? cList[0].id : "");
                      if (cid) {
                        setSelectedCourse(cid);
                        loadTasks(cid, token);
                      }
                    }}
                    title="Tải lại danh sách câu hỏi"
                  >
                    <RefreshIcon size={13} />
                    <span>Làm mới câu hỏi</span>
                  </button>
                  </div>
              </div>

              <div style={{ display: "flex", alignItems: "center", gap: 14, flexWrap: "wrap", justifyContent: "flex-end" }}>
                <div style={{ textAlign: "right" }}>
                  <div style={{ fontSize: 13, color: "#52525b" }}>
                    Tiến độ: <strong style={{ color: "#09090b" }}>{completedCount} / {tasks.length}</strong> câu ({progressPercent}%)
                  </div>
                  <div style={{ width: 160, height: 6, background: "#e4e4e7", borderRadius: 999, overflow: "hidden", marginTop: 6 }}>
                    <div style={{ width: `${progressPercent}%`, height: "100%", background: "#16a34a", transition: "width 0.3s ease" }} />
                  </div>
                </div>

                {isParticipantCompleted ? (
                  isCompletedSession ? (
                    <div
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        padding: "8px 14px",
                        borderRadius: 8,
                        background: "#dcfce7",
                        color: "#166534",
                        fontSize: 13,
                        fontWeight: 700,
                        border: "1px solid #86efac"
                      }}
                    >
                      <CheckIcon size={14} color="#166534" />
                      <span>Đã hoàn thành bài thu âm</span>
                    </div>
                  ) : (
                    <button
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        padding: "8px 14px",
                        borderRadius: 8,
                        border: "none",
                        background: "#16a34a",
                        color: "#ffffff",
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: "pointer",
                        boxShadow: "0 2px 6px rgba(22, 163, 74, 0.3)",
                        transition: "all 0.15s ease"
                      }}
                      onClick={() => setIsCompletedSession(true)}
                      title="Xem lại thư cảm ơn và xác nhận hoàn thành"
                    >
                      <CheckIcon size={14} color="#ffffff" />
                      <span>Xem thư cảm ơn / Kết quả</span>
                    </button>
                  )
                ) : (
                  completedCount > 0 && (
                    <button
                      style={{
                        display: "inline-flex",
                        alignItems: "center",
                        gap: 6,
                        padding: "8px 14px",
                        borderRadius: 8,
                        border: "none",
                        background: completedCount === tasks.length ? "#16a34a" : "#0f172a",
                        color: "#ffffff",
                        fontSize: 13,
                        fontWeight: 600,
                        cursor: "pointer",
                        boxShadow: completedCount === tasks.length ? "0 2px 6px rgba(22, 163, 74, 0.3)" : "none",
                        transition: "all 0.15s ease"
                      }}
                      disabled={busy || isRecording}
                      onClick={handleCompleteSession}
                      title="Nộp và kết thúc bài thu âm để nhận thư cảm ơn"
                    >
                      <CheckIcon size={14} color="#ffffff" />
                      <span>Hoàn thành bài thu âm</span>
                    </button>
                  )
                )}
              </div>
            </div>
          </section>

          {isCompletedSession ? (
            <section style={{ ...styles.card, padding: "44px 24px", textAlign: "center", border: "1.5px solid #86efac", background: "#f0fdf4", boxShadow: "0 4px 14px rgba(22, 163, 74, 0.08)" }}>
              <div style={{ width: 64, height: 64, borderRadius: "50%", background: "#16a34a", color: "#ffffff", display: "inline-flex", alignItems: "center", justifyContent: "center", margin: "0 auto 20px" }}>
                <CheckIcon size={32} color="#ffffff" />
              </div>
              <h2 style={{ fontSize: 24, fontWeight: 800, color: "#14532d", margin: "0 0 10px" }}>
                Chúc mừng bạn đã hoàn thành bài thi!
              </h2>
              <p style={{ fontSize: 15, color: "#166534", maxWidth: 540, margin: "0 auto 24px", lineHeight: 1.6 }}>
                Thay mặt nhóm nghiên cứu đề tài <strong>LiemWhisper</strong>, xin chân thành cảm ơn bạn đã dành thời gian đóng góp giọng nói quý báu cho bộ ngữ liệu khoa học.
              </p>

              <div style={{ maxWidth: 460, margin: "0 auto 24px", background: "#ffffff", borderRadius: 10, padding: 20, border: "1px solid #dcfce7", textAlign: "left", boxShadow: "0 2px 4px rgba(0,0,0,0.03)" }}>
                <div style={{ fontSize: 12, fontWeight: 700, color: "#14532d", marginBottom: 12, textTransform: "uppercase", letterSpacing: "0.05em" }}>
                  Thông tin xác nhận đóng góp
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid #f0fdf4", fontSize: 13 }}>
                  <span style={{ color: "#64748b" }}>Mã sinh viên / Participant:</span>
                  <strong style={{ color: "#0f172a" }}>{participantInfo?.participant_code || "N/A"}</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", borderBottom: "1px solid #f0fdf4", fontSize: 13 }}>
                  <span style={{ color: "#64748b" }}>Số câu đã hoàn thành:</span>
                  <strong style={{ color: "#16a34a" }}>{completionDetails?.total ?? completedCount} / {tasks.length} câu</strong>
                </div>
                <div style={{ display: "flex", justifyContent: "space-between", padding: "7px 0", fontSize: 13 }}>
                  <span style={{ color: "#64748b" }}>Email nhận thư cảm ơn:</span>
                  <strong style={{ color: "#0f172a" }}>{completionDetails?.email || participantInfo?.email || participantInfo?.survey?.email || "Email Google của bạn"}</strong>
                </div>
              </div>

              <div style={{ background: "#dcfce7", color: "#14532d", padding: "12px 18px", borderRadius: 8, fontSize: 13, fontWeight: 500, maxWidth: 500, margin: "0 auto 28px" }}>
                ✉️ Thư cảm ơn chính thức đã được gửi đến hộp thư Gmail của bạn. Vui lòng kiểm tra hộp thư đến (hoặc hòm thư Spam/Promotions nếu chưa thấy).
              </div>

              <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap" }}>
                <button
                  style={styles.btnSecondary}
                  onClick={() => setIsCompletedSession(false)}
                >
                  <RefreshIcon size={14} />
                  <span>Xem lại các câu đã thu âm</span>
                </button>
                <button
                  style={{ ...styles.btnSecondary, color: "#b91c1c", borderColor: "#fca5a5" }}
                  onClick={handleLogout}
                >
                  <LogoutIcon size={14} />
                  <span>Đăng xuất & Thoát</span>
                </button>
              </div>
            </section>
          ) : (
            <>
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
                    <span style={{ fontSize: 12, background: "#dcfce7", color: "#166534", padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>
                      Đã ghi âm
                    </span>
                  ) : (
                    <span style={{ fontSize: 12, background: "#f4f4f5", color: "#71717a", padding: "2px 8px", borderRadius: 4, fontWeight: 500 }}>
                      Chưa ghi âm
                    </span>
                  )}
                  {isParticipantCompleted && (
                    <span style={{ fontSize: 12, background: "#eff6ff", color: "#1d4ed8", padding: "2px 8px", borderRadius: 4, fontWeight: 600, border: "1px solid #bfdbfe" }}>
                      🔒 Chế độ xem lại
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

              {/* Review Mode Banner when Session is Completed */}
              {isParticipantCompleted && (
                <div
                  style={{
                    background: "#f0fdf4",
                    border: "1px solid #bbf7d0",
                    borderRadius: 8,
                    padding: "10px 14px",
                    marginBottom: 16,
                    display: "flex",
                    alignItems: "center",
                    justifyContent: "space-between",
                    flexWrap: "wrap",
                    gap: 10,
                    fontSize: 13,
                    color: "#166534"
                  }}
                >
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <CheckIcon size={16} color="#16a34a" />
                    <span>
                      <strong>Bài thi đã hoàn thành:</strong> Bạn đang ở chế độ xem lại. Bạn có thể nghe lại các bản thu âm nhưng không thể ghi âm thêm hoặc nộp lại bài.
                    </span>
                  </div>
                  <button
                    type="button"
                    style={{
                      background: "#16a34a",
                      color: "#ffffff",
                      border: "none",
                      borderRadius: 6,
                      padding: "5px 12px",
                      fontSize: 12,
                      fontWeight: 600,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 4
                    }}
                    onClick={() => setIsCompletedSession(true)}
                  >
                    <span>Xem thư cảm ơn</span>
                  </button>
                </div>
              )}

              {/* PROMPT TEXT DISPLAY */}
              {(() => {
                const text = (currentTask.text || "").replace(/;/g, ",");
                let questionPart = "";
                let readingPart = text;

                if (text.includes("Câu hỏi:") && text.includes("Trả lời:")) {
                  const parts = text.split("Trả lời:");
                  questionPart = parts[0].replace("Câu hỏi:", "").trim();
                  readingPart = parts.slice(1).join("Trả lời:").trim();
                } else if (text.includes("Hỏi:") && text.includes("Đáp:")) {
                  const parts = text.split("Đáp:");
                  questionPart = parts[0].replace("Hỏi:", "").trim();
                  readingPart = parts.slice(1).join("Đáp:").trim();
                }

                return (
                  <div style={{ marginBottom: 24 }}>
                    {questionPart && (
                      <div
                        style={{
                          background: "#f8fafc",
                          border: "1px solid #e2e8f0",
                          borderRadius: 8,
                          padding: "14px 18px",
                          marginBottom: 14,
                          textAlign: "left"
                        }}
                      >
                        <div
                          style={{
                            fontSize: 11,
                            fontWeight: 700,
                            color: "#475569",
                            textTransform: "uppercase",
                            letterSpacing: "0.05em",
                            marginBottom: 6,
                            display: "flex",
                            alignItems: "center",
                            gap: 8
                          }}
                        >
                          <span style={{ background: "#e2e8f0", color: "#334155", padding: "2px 8px", borderRadius: 4, fontWeight: 700 }}>
                            CÂU HỎI
                          </span>
                          {currentTask.category && (
                            <span style={{ color: "#64748b", fontWeight: 500, fontSize: 11 }}>
                              Chủ đề: {currentTask.category}
                            </span>
                          )}
                        </div>
                        <div style={{ fontSize: 15, fontWeight: 600, color: "#0f172a", lineHeight: 1.5 }}>
                          {questionPart}
                        </div>
                      </div>
                    )}

                    <div
                      style={{
                        background: "#ffffff",
                        padding: "24px 20px",
                        borderRadius: 8,
                        border: "1px solid #e4e4e7",
                        textAlign: "center",
                        boxShadow: "0 1px 3px rgba(0,0,0,0.02)"
                      }}
                    >
                      <div
                        style={{
                          fontSize: 11,
                          fontWeight: 700,
                          color: "#166534",
                          textTransform: "uppercase",
                          letterSpacing: "0.05em",
                          marginBottom: 10
                        }}
                      >
                        🎙️ Văn bản đọc thu âm (Câu trả lời)
                      </div>
                      <p style={{ fontSize: 20, fontWeight: 600, color: "#09090b", lineHeight: 1.7, margin: "8px 0 12px" }}>
                        {renderHighlightedText(readingPart, currentTask.target_terms)}
                      </p>
                      <p style={{ fontSize: 13, color: "#64748b", margin: 0, lineHeight: 1.5 }}>
                        Hướng dẫn: Đọc to, rõ ràng theo tốc độ tự nhiên. Phát âm thuật ngữ tiếng Anh theo thói quen giao tiếp kỹ thuật của bạn.
                      </p>
                    </div>
                  </div>
                );
              })()}

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

              {/* RECORDING & PLAYBACK CONTROLS */}
              <div style={{ display: "flex", justifyContent: "center", gap: 12, flexWrap: "wrap", alignItems: "center" }}>
                {isParticipantCompleted ? (
                  currentTask.recording_id ? (
                    <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, width: "100%", maxWidth: 420 }}>
                      <div style={{ fontSize: 13, fontWeight: 600, color: "#166534", display: "flex", alignItems: "center", gap: 6 }}>
                        <CheckIcon size={14} color="#166534" />
                        <span>Bản ghi âm đã nộp của câu này</span>
                        {currentTask.duration_seconds ? (
                          <span style={{ fontSize: 12, color: "#71717a", fontWeight: 400 }}>
                            ({currentTask.duration_seconds.toFixed(1)}s)
                          </span>
                        ) : null}
                      </div>
                      <AuthenticatedAudioPlayer
                        apiBase={API}
                        audioPath={`/api/v1/recordings/${currentTask.recording_id}/audio`}
                        authHeader={{ name: "x-participant-token", value: token }}
                        style={{ width: "100%", maxWidth: 400 }}
                      />
                    </div>
                  ) : (
                    <div style={{ padding: "16px 20px", background: "#f8fafc", borderRadius: 8, border: "1px dashed #cbd5e1", color: "#64748b", fontSize: 13, textAlign: "center" }}>
                      Câu này chưa có bản ghi âm (bạn đã hoàn thành bài thi).
                    </div>
                  )
                ) : (
                  <>
                    {!isRecording && !audioUrl && currentTask.recording_id && (
                      <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 10, width: "100%", maxWidth: 420 }}>
                        <div style={{ fontSize: 13, fontWeight: 600, color: "#166534", display: "flex", alignItems: "center", gap: 6 }}>
                          <CheckIcon size={14} color="#166534" />
                          <span>Bản ghi âm đã lưu cho câu này</span>
                          {currentTask.duration_seconds ? (
                            <span style={{ fontSize: 12, color: "#71717a", fontWeight: 400 }}>
                              ({currentTask.duration_seconds.toFixed(1)}s)
                            </span>
                          ) : null}
                        </div>
                        <AuthenticatedAudioPlayer
                          apiBase={API}
                          audioPath={`/api/v1/recordings/${currentTask.recording_id}/audio`}
                          authHeader={{ name: "x-participant-token", value: token }}
                          style={{ width: "100%", maxWidth: 400 }}
                        />
                        <button
                          style={{ ...styles.btnSecondary, marginTop: 4 }}
                          disabled={busy}
                          onClick={() => startRecording(currentTask.id)}
                        >
                          <RefreshIcon size={13} />
                          <span>Thu âm lại câu này</span>
                        </button>
                      </div>
                    )}

                    {!isRecording && !audioUrl && !currentTask.recording_id && (
                      <button
                        style={styles.btnRecord}
                        disabled={busy}
                        onClick={() => startRecording(currentTask.id)}
                      >
                        <MicIcon size={16} />
                        <span>Bắt đầu ghi âm</span>
                      </button>
                    )}
                  </>
                )}

                {isRecording && (
                  <button style={styles.btnStop} onClick={stopRecording}>
                    <StopIcon size={14} color="#ffffff" />
                    <span>Dừng ghi âm</span>
                  </button>
                )}

                {audioUrl && !isRecording && (
                  <div style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 12, width: "100%", maxWidth: 420 }}>
                    <div style={{ fontSize: 13, color: "#09090b", fontWeight: 600, display: "flex", alignItems: "center", gap: 6 }}>
                      <span>Nghe lại bản thu thử ({recordedDuration.toFixed(1)}s):</span>
                    </div>
                    <audio
                      key={audioUrl}
                      controls
                      src={audioUrl}
                      preload="auto"
                      onLoadedMetadata={(e) => {
                        const el = e.currentTarget;
                        if (el.duration === Infinity || isNaN(el.duration) || el.duration === 0) {
                          el.currentTime = 1e101;
                          el.ontimeupdate = () => {
                            el.ontimeupdate = null;
                            el.currentTime = 0;
                          };
                        }
                      }}
                      style={{ width: "100%", maxWidth: 400 }}
                    />
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

              {/* PROMPT WHEN ALL COMPLETED */}
              {tasks.length > 0 && completedCount === tasks.length && (
                <div style={{ ...styles.card, background: "#f0fdf4", border: "1.5px solid #86efac", textAlign: "center", padding: "32px 20px", marginTop: 20 }}>
                  <div style={{ width: 48, height: 48, borderRadius: "50%", background: "#16a34a", color: "#ffffff", display: "inline-flex", alignItems: "center", justifyContent: "center", margin: "0 auto 12px" }}>
                    <CheckIcon size={24} color="#ffffff" />
                  </div>
                  <h3 style={{ color: "#14532d", fontSize: 18, margin: "0 0 8px", fontWeight: 700 }}>
                    Bạn đã hoàn thành đủ {tasks.length} / {tasks.length} câu hỏi!
                  </h3>
                  <p style={{ color: "#166534", fontSize: 14, margin: "0 auto 18px", maxWidth: 500, lineHeight: 1.5 }}>
                    Bấm nút bên dưới để kết thúc bài thi. Hệ thống sẽ chính thức ghi nhận và tự động gửi email cảm ơn đến bạn.
                  </p>
                  <button
                    style={{
                      padding: "11px 26px",
                      borderRadius: 8,
                      border: "none",
                      background: "#16a34a",
                      color: "#ffffff",
                      fontSize: 14,
                      fontWeight: 700,
                      cursor: "pointer",
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 8,
                      boxShadow: "0 4px 12px rgba(22, 163, 74, 0.3)"
                    }}
                    disabled={busy}
                    onClick={handleCompleteSession}
                  >
                    <CheckIcon size={16} color="#ffffff" />
                    <span>Hoàn thành bài thi & Nhận email cảm ơn</span>
                  </button>
                </div>
              )}
            </>
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
                    background: adminSubTab === "admins" ? "#ffffff" : "transparent",
                    color: adminSubTab === "admins" ? "#09090b" : "#71717a",
                    boxShadow: adminSubTab === "admins" ? "0 1px 2px rgba(0,0,0,0.06)" : "none"
                  }}
                  onClick={() => { setAdminSubTab("admins"); loadAdminAdmins(); loadAdminParticipants(); }}
                >
                  Cấp quyền Admin (Gmail)
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
                  loadAdminAdmins();
                  loadAdminParticipants();
                  loadDriveStatus();
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
                <div style={{ background: "#f5f3ff", padding: 14, borderRadius: 8, border: "1px solid #ddd6fe" }}>
                  <div style={{ fontSize: 12, color: "#6b21a8" }}>Quản trị viên (Gmail)</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#7c3aed", marginTop: 4 }}>{adminUsersList.length || 1}</div>
                </div>
                <div style={{ background: "#f0fdf4", padding: 14, borderRadius: 8, border: "1px solid #bbf7d0" }}>
                  <div style={{ fontSize: 12, color: "#166534" }}>Tổng bản ghi thu âm</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#15803d", marginTop: 4 }}>{stats.total_recordings}</div>
                </div>
                <div style={{ background: "#fefce8", padding: 14, borderRadius: 8, border: "1px solid #fef08a" }}>
                  <div style={{ fontSize: 12, color: "#854d0e" }}>Tổng thời lượng (phút)</div>
                  <div style={{ fontSize: 22, fontWeight: 700, color: "#a16207", marginTop: 4 }}>{stats.total_duration_minutes}m</div>
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
                      <span style={{ color: "#16a34a", fontWeight: 600 }}>{c.recordings_count} bản ghi đã nộp</span>
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

          {/* SUBTAB: ADMIN USERS MANAGEMENT (GMAIL) */}
          {adminSubTab === "admins" && (
            <div style={{ display: "flex", flexDirection: "column", gap: 20 }}>
              {/* Card 1: Add new admin by Gmail */}
              <section style={styles.card}>
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginBottom: 8 }}>
                  <ShieldIcon size={18} color="#2563eb" />
                  <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Cấp quyền Quản trị viên mới qua Google / Gmail</h2>
                </div>
                <p style={{ color: "#52525b", fontSize: 13, lineHeight: 1.5, margin: "0 0 16px" }}>
                  Người dùng sở hữu địa chỉ Gmail dưới đây sẽ được cấp quyền Quản trị viên (Admin). Khi đăng nhập bằng tài khoản Google tại trang chủ, hệ thống sẽ tự động nhận diện và chuyển sang bảng quản trị.
                </p>

                <div style={{ display: "flex", gap: 10, flexWrap: "wrap", alignItems: "center" }}>
                  <input
                    type="email"
                    style={{
                      ...styles.field,
                      maxWidth: 420,
                      flex: 1,
                      padding: "10px 14px",
                      fontSize: 14
                    }}
                    placeholder="Nhập địa chỉ Gmail (ví dụ: giangvien@gmail.com)"
                    value={newAdminEmailInput}
                    onChange={(e) => setNewAdminEmailInput(e.target.value)}
                    onKeyDown={(e) => { if (e.key === "Enter") handleAddAdmin(); }}
                    disabled={addingAdmin}
                  />
                  <button
                    type="button"
                    style={{
                      ...styles.btnPrimary,
                      padding: "10px 20px",
                      fontSize: 14,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 8,
                      opacity: addingAdmin ? 0.7 : 1
                    }}
                    onClick={() => handleAddAdmin()}
                    disabled={addingAdmin}
                  >
                    {addingAdmin ? <RefreshIcon size={14} /> : <CheckIcon size={14} />}
                    <span>{addingAdmin ? "Đang cấp..." : "Cấp quyền Admin"}</span>
                  </button>
                </div>
              </section>

              {/* Card 2: List of active Admins */}
              <section style={styles.card}>
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 16, flexWrap: "wrap", gap: 8 }}>
                  <div>
                    <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Danh sách Quản trị viên hiện tại</h2>
                    <div style={{ fontSize: 12, color: "#71717a", marginTop: 2 }}>
                      Tổng cộng {adminUsersList.length} tài khoản có quyền quản trị hệ thống
                    </div>
                  </div>
                  <button
                    type="button"
                    onClick={() => {
                      const k = adminKey || getAdminSession();
                      if (k) { loadAdminAdmins(k); loadAdminParticipants(k); }
                    }}
                    disabled={loadingAdmins}
                    style={{
                      ...styles.btnSecondary,
                      padding: "6px 12px",
                      fontSize: 12,
                      display: "inline-flex",
                      alignItems: "center",
                      gap: 6
                    }}
                  >
                    <RefreshIcon size={12} />
                    <span>Làm mới</span>
                  </button>
                </div>

                {loadingAdmins && adminUsersList.length === 0 ? (
                  <div style={{ padding: "24px 0", textAlign: "center", color: "#71717a", fontSize: 13 }}>
                    Đang tải danh sách quản trị viên...
                  </div>
                ) : adminUsersList.length === 0 ? (
                  <div style={{ padding: "24px 0", textAlign: "center", color: "#71717a", fontSize: 13, background: "#f8fafc", borderRadius: 8 }}>
                    Chưa có quản trị viên nào được cấp qua Gmail. Hãy nhập Gmail ở trên để cấp quyền quản trị đầu tiên.
                  </div>
                ) : (
                  <div style={{ overflowX: "auto" }}>
                    <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
                      <thead>
                        <tr style={{ background: "#f8fafc", borderBottom: "1px solid #e2e8f0", textAlign: "left", color: "#475569" }}>
                          <th style={{ padding: "10px 14px", fontWeight: 600 }}>Tài khoản Gmail</th>
                          <th style={{ padding: "10px 14px", fontWeight: 600 }}>Tên hiển thị / Liên kết</th>
                          <th style={{ padding: "10px 14px", fontWeight: 600 }}>Nguồn cấp</th>
                          <th style={{ padding: "10px 14px", fontWeight: 600 }}>Ngày cấp</th>
                          <th style={{ padding: "10px 14px", fontWeight: 600, textAlign: "right" }}>Thao tác</th>
                        </tr>
                      </thead>
                      <tbody>
                        {adminUsersList.map((a) => (
                          <tr key={a.email} style={{ borderBottom: "1px solid #f1f5f9" }}>
                            <td style={{ padding: "12px 14px" }}>
                              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                                <div style={{
                                  width: 28,
                                  height: 28,
                                  borderRadius: "50%",
                                  background: "#eff6ff",
                                  color: "#2563eb",
                                  display: "flex",
                                  alignItems: "center",
                                  justifyContent: "center",
                                  fontWeight: 700,
                                  fontSize: 12
                                }}>
                                  G
                                </div>
                                <div>
                                  <div style={{ fontWeight: 600, color: "#09090b" }}>{a.email}</div>
                                  <div style={{ display: "inline-block", background: "#dbeafe", color: "#1e40af", padding: "1px 6px", borderRadius: 4, fontSize: 11, fontWeight: 600, marginTop: 2 }}>
                                    Admin
                                  </div>
                                </div>
                              </div>
                            </td>
                            <td style={{ padding: "12px 14px", color: a.linked ? "#09090b" : "#94a3b8" }}>
                              {a.linked ? (
                                <span style={{ display: "inline-flex", alignItems: "center", gap: 4, color: "#15803d", fontWeight: 500 }}>
                                  <CheckIcon size={13} color="#15803d" />
                                  <span>{a.name || "Đã liên kết Google"}</span>
                                </span>
                              ) : (
                                <span>Chờ đăng nhập lần đầu</span>
                              )}
                            </td>
                            <td style={{ padding: "12px 14px", color: "#64748b" }}>
                              {a.is_env ? (
                                <span style={{ background: "#fef3c7", color: "#92400e", padding: "2px 8px", borderRadius: 4, fontSize: 11, fontWeight: 600 }}>
                                  Biến môi trường
                                </span>
                              ) : (
                                <span>{a.created_by || "Admin"}</span>
                              )}
                            </td>
                            <td style={{ padding: "12px 14px", color: "#64748b" }}>
                              {a.created_at ? new Date(a.created_at * 1000).toLocaleString("vi-VN") : "Cấu hình cố định"}
                            </td>
                            <td style={{ padding: "12px 14px", textAlign: "right" }}>
                              {a.is_env ? (
                                <span style={{ fontSize: 11, color: "#94a3b8" }} title="Quản trị viên cấu hình trong ADMIN_EMAILS không thể xóa qua giao diện">
                                  Cố định
                                </span>
                              ) : (
                                <button
                                  type="button"
                                  onClick={() => handleRemoveAdmin(a.email)}
                                  disabled={busy}
                                  style={{
                                    ...styles.btnSecondary,
                                    padding: "4px 10px",
                                    fontSize: 12,
                                    color: "#dc2626",
                                    borderColor: "#fca5a5",
                                    background: "#fff"
                                  }}
                                  title="Thu hồi quyền quản trị viên của email này"
                                >
                                  Thu hồi
                                </button>
                              )}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </section>

              {/* Card 3: Quick grant from existing Google participants */}
              {adminParticipantsList.length > 0 && (
                <section style={styles.card}>
                  <div style={{ marginBottom: 12 }}>
                    <h2 style={{ fontSize: 16, fontWeight: 700, margin: 0 }}>Gợi ý cấp Admin từ người tham gia Google gần đây</h2>
                    <div style={{ fontSize: 12, color: "#71717a", marginTop: 2 }}>
                      Nhấn "Cấp quyền" để nâng cấp tài khoản của người tham gia lên Quản trị viên
                    </div>
                  </div>
                  <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))", gap: 10 }}>
                    {adminParticipantsList
                      .filter((p) => p.email && p.email.includes("@"))
                      .slice(0, 8)
                      .map((p) => {
                        const alreadyAdmin = adminUsersList.some((a) => a.email.toLowerCase() === p.email.toLowerCase()) || Boolean(p.is_admin);
                        return (
                          <div
                            key={p.id}
                            style={{
                              padding: "10px 12px",
                              borderRadius: 6,
                              border: "1px solid #e2e8f0",
                              background: alreadyAdmin ? "#f8fafc" : "#ffffff",
                              display: "flex",
                              justifyContent: "space-between",
                              alignItems: "center",
                              gap: 8
                            }}
                          >
                            <div style={{ minWidth: 0, flex: 1 }}>
                              <div style={{ fontWeight: 600, fontSize: 13, color: "#09090b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {p.name || p.participant_code}
                              </div>
                              <div style={{ fontSize: 12, color: "#64748b", overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                                {p.email}
                              </div>
                            </div>
                            {alreadyAdmin ? (
                              <span style={{ fontSize: 11, background: "#dcfce7", color: "#166534", padding: "2px 8px", borderRadius: 4, fontWeight: 600 }}>
                                Đã là Admin
                              </span>
                            ) : (
                              <button
                                type="button"
                                onClick={() => handleAddAdmin(p.email)}
                                disabled={addingAdmin}
                                style={{
                                  ...styles.btnSecondary,
                                  padding: "4px 8px",
                                  fontSize: 12,
                                  color: "#2563eb",
                                  borderColor: "#93c5fd",
                                  background: "#eff6ff",
                                  whiteSpace: "nowrap"
                                }}
                              >
                                + Cấp quyền
                              </button>
                            )}
                          </div>
                        );
                      })}
                  </div>
                </section>
              )}
            </div>
          )}

          {/* SUBTAB 3: DATASET EXPORT */}
          {adminSubTab === "export" && (
            <section style={styles.card}>
              <h2 style={{ fontSize: 16, fontWeight: 700, margin: "0 0 8px" }}>Xuất bộ dữ liệu nghiên cứu</h2>
              <p style={{ color: "#52525b", fontSize: 13, lineHeight: 1.5, margin: "0 0 20px" }}>
                Tất cả các bản ghi thu âm hợp lệ và có sự đồng ý của người tham gia sẽ được đưa vào bộ dữ liệu xuất bản.
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
