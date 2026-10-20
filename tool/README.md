# Data Collection Web Platform (LiemWhisper)

Hệ thống web thu thập dữ liệu giọng nói tiếng Việt có chêm xen thuật ngữ kỹ thuật tiếng Anh (Code-switched Speech Collection Platform) phục vụ nghiên cứu khoa học đề tài LiemWhisper.

## Kiến trúc đã triển khai

- **Frontend (`tool/client`):** Next.js 15 (React 19, TypeScript), responsive, hỗ trợ AudioContext live visualizer và MediaRecorder thích ứng đa nền tảng (Chrome/Edge: WebM/Opus, Safari/iOS: MP4/AAC).
- **Backend (`tool/backend`):** FastAPI + SQLite (WAL mode, mở rộng PostgreSQL), HTTP Range-request audio streaming (206 Partial Content), mã hóa SHA-256 checksum, pipeline kiểm duyệt và export ZIP.
- **Dữ liệu cục bộ (`private-data/`):** Lưu trữ file âm thanh và file SQLite độc lập, an toàn, hỗ trợ Docker volume.

## Phân quyền & Vai trò (Role-Based Access)

### 1. Vai trò Người Thu Âm / Sinh Viên (Student / Participant)
- **Đăng nhập nhanh:** Bằng Mã sinh viên (VD: `SE194007`) hoặc Participant Token đã cấp.
- **Đăng ký mới:** Cam kết đồng thuận nghiên cứu (Consent v1.0), điền khảo sát ngắn về thiết bị & trình độ.
- **Studio Thu Âm:** 
  - Giao diện Card-by-Card trực quan, highlight từ khóa tiếng Anh.
  - Sóng âm thời gian thực (Waveform Visualizer), đồng hồ đếm ngược (0 - 45s).
  - Tự động nhảy tới câu chưa thu âm, nghe lại và thu lại trước khi gửi.
  - Tách biệt hoàn toàn, **không nhìn thấy bất kỳ chức năng quản trị nào**.

### 2. Vai trò Quản Trị Viên (Admin)
- **Đăng nhập linh hoạt:**
  1. Đăng nhập bằng tài khoản Google (Gmail) đã được phân quyền quản trị (không cần mật khẩu riêng).
  2. Đăng nhập bằng Khóa Quản trị bảo mật (`ADMIN_API_KEY`, mặc định môi trường dev: `liemwhisper-admin-secret-2026`).
- **Dashboard Quản trị:**
  1. **📊 Thống kê:** Tổng số môn học, câu hỏi, người tham gia, số bản thu, số giờ âm thanh đã thu thập và số lượng Admin.
  2. **📚 Quản lý Môn & Câu:** Tạo môn học mới, Nhập câu hỏi hàng loạt (Bulk Import) tự động bóc tách từ khóa.
  3. **🛡️ Cấp quyền Admin (Gmail):** Nhập địa chỉ Gmail để cấp quyền quản trị, theo dõi danh sách Admin đang hoạt động, thu hồi quyền, hoặc cấp nhanh từ danh sách người tham gia Google.
  4. **💾 Xuất Dữ liệu:** Xuất Manifest JSON, CSV và tải trọn gói ZIP (tất cả audio + metadata) sẵn sàng huấn luyện AI.
- **Quản lý Admin qua lệnh Terminal (CLI):**
  ```bash
  python tool/scripts/manage_admins.py list             # Xem danh sách Admin
  python tool/scripts/manage_admins.py add user@gmail.com    # Cấp quyền Admin
  python tool/scripts/manage_admins.py remove user@gmail.com # Thu hồi quyền
  ```

## Phạm vi thư mục

Mã nguồn, Docker Compose, cấu hình mẫu và script nạp câu hỏi nằm trong `tool/`. Các lệnh bên dưới bắt đầu từ thư mục gốc repository, mỗi phần chạy trong một terminal riêng.

Dữ liệu đang có được giữ nguyên ở `private-data/` tại gốc repository để không làm hỏng đường dẫn âm thanh đã lưu trong SQLite. Thư mục `web/private-data/` cũ cũng được giữ nguyên, không xóa hay ghi đè. `research/`, `paper/`, `docs/` và `todo.md` là tài liệu/nghiên cứu chung, không chuyển vào tool.

## Deploy Vercel + Render

Xem [DEPLOYMENT.md](DEPLOYMENT.md) để cấu hình frontend Vercel và backend Render có persistent disk. Blueprint nằm tại `tool/render.yaml`; cấu hình Vercel tại `tool/client/vercel.json`. Render Starter + disk có phí. Chỉ triển khai thử nghiệm cho đến khi hoàn thành các yêu cầu bảo mật trong hướng dẫn.

## Hướng dẫn Khởi chạy

### 1. Khởi chạy bằng Docker Compose (Khuyên dùng)
```bash
cd tool
docker-compose up --build -d
```

### 2. Khởi chạy thủ công từng phần

#### Backend (FastAPI - Port 8000)
```bash
cd tool/backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
- Swagger API Docs: `http://localhost:8000/docs`
- Healthcheck: `http://localhost:8000/health`

#### Frontend (Next.js - Port 3000)
```bash
cd tool/client
npm install
npm run build
npm start
```
- Web Portal: `http://localhost:3000`

#### Nạp dữ liệu mẫu ban đầu (20 câu Kiểm thử phần mềm):
```bash
PYTHONPATH=tool/backend python tool/scripts/seed_prompts.py
```
# Cloudflare Turnstile

1. Open Cloudflare Dashboard → Turnstile → Add widget, select Managed,
   and add the frontend hostname (without scheme or path).
2. Frontend (Vercel environment or `client/.env.local`):
   set `NEXT_PUBLIC_TURNSTILE_SITE_KEY` to the widget's public Site key.
3. Backend (Render environment or the environment used to launch FastAPI):
   set `TURNSTILE_ENABLED=true`, `TURNSTILE_SECRET_KEY` to the private Secret key,
   and `TURNSTILE_ALLOWED_HOSTNAMES` to comma-separated frontend hostnames.
   Never put the Secret key in a `NEXT_PUBLIC_` variable.
4. Rebuild/redeploy the frontend and restart/redeploy the backend.
   Docker Compose reads these variables from `tool/.env`; rebuild the client.

Turnstile protects Google login, admin login, legacy student login, and legacy
participant signup. Existing sessions and Google onboarding continue to use
their session tokens. New login attempts reset the challenge, since verification
tokens are single-use. Without configuration CAPTCHA is disabled for local
development; setting `TURNSTILE_ENABLED=true` without a secret rejects logins.
Setting a secret also enables backend verification.

Check deployment by submitting login without a CAPTCHA token (must fail),
then completing the widget and signing in. Test expired/reused tokens and
retry after invalid credentials. Use Cloudflare's testing keys only in a test
environment: https://developers.cloudflare.com/turnstile/troubleshooting/testing/

## Google Drive organization and duplicate recovery

- Each participant keeps one persistent `drive_folder_id`; each recording keeps
  one persistent `drive_file_id`. Retries and re-recordings reuse those IDs.
- Participant folders retain readable `student-code - name` labels. Audio names
  contain the question number and recording ID; `Danh_sach_ban_thu.csv` provides
  participant, course/question context and direct Drive links.
- Drive sync and cleanup are serialized across threads/processes using a
  PostgreSQL transaction advisory lock, or an OS file lock for local SQLite.
- Restart all backend workers when deploying this change so no old worker keeps
  using the previous synchronization logic.
- After deployment, use the admin Drive cleanup button to consolidate verified
  recordings. Same-name files are moved to Trash only when their downloaded
  SHA-256 matches the canonical database recording and the canonical Drive file.
  Unknown files, different takes, ambiguous participant names and failed moves
  are preserved. Redundant folders are trashed only after a complete listing
  confirms they are empty. No recordings are deleted from SQL by cleanup.
- Cleanup cannot infer ownership from question numbers alone. Items preserved
  for manual inspection may remain in older duplicate folders.
- Cleanup starts a background job and returns HTTP 202 immediately. The admin
  page polls `/api/v1/admin/drive/cleanup-status` with its session header and shows
  the current phase and recording count. Repeated clicks reuse the active job.
  Progress survives page reloads; a job without progress for five minutes is
  marked interrupted so it can be retried safely after a backend restart.
- Routine sync no longer rescans every previously synced file. Cleanup skips
  downloading audio already in its canonical folder when no duplicate name is
  present. Duplicate candidates still require full content verification.
