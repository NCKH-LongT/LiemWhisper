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
