# Data Collection Web Platform (LiemWhisper)

Hệ thống web thu thập dữ liệu giọng nói tiếng Việt có chêm xen thuật ngữ kỹ thuật tiếng Anh (Code-switched Speech Collection Platform) phục vụ nghiên cứu khoa học đề tài LiemWhisper.

## Kiến trúc đã triển khai

- **Frontend (`web/client`):** Next.js 15 (React 19, TypeScript), responsive, hỗ trợ AudioContext live visualizer và MediaRecorder thích ứng đa nền tảng (Chrome/Edge: WebM/Opus, Safari/iOS: MP4/AAC).
- **Backend (`web/backend`):** FastAPI + SQLite (WAL mode, mở rộng PostgreSQL), HTTP Range-request audio streaming (206 Partial Content), mã hóa SHA-256 checksum, pipeline kiểm duyệt và export ZIP.
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
- **Đăng nhập:** Bằng Khóa Quản trị bảo mật (`ADMIN_API_KEY`, mặc định môi trường dev: `liemwhisper-admin-secret-2026`).
- **Dashboard Quản trị:**
  1. **📊 Thống kê:** Tổng số môn học, câu hỏi, người tham gia, số bản thu, số giờ âm thanh đã duyệt.
  2. **📚 Quản lý Môn & Câu:** Tạo môn học mới, Nhập câu hỏi hàng loạt (Bulk Import) tự động bóc tách từ khóa.
  3. **🎧 Studio Kiểm duyệt Ghi âm:** Nghe trực tiếp qua streaming audio, nghe tua, sửa verbatim transcript thực tế, duyệt (`approved`), từ chối (`rejected`), hoặc yêu cầu thu lại (`rerecord`).
  4. **💾 Xuất Dữ liệu:** Xuất Manifest JSON, CSV và tải trọn gói ZIP (tất cả audio + metadata) sẵn sàng huấn luyện AI.

## Hướng dẫn Khởi chạy Local

### Backend (FastAPI - Port 8000)
```bash
python -m uvicorn app.main:app --app-dir web/backend --host 127.0.0.1 --port 8000 --reload
```
- Swagger Docs: `http://localhost:8000/docs`
- Healthcheck: `http://localhost:8000/health`

### Frontend (Next.js - Port 3000)
```bash
cd web/client
npm install
npm run build
npm start
```
- Web Portal: `http://localhost:3000`

### Chạy bằng Docker Compose
```bash
docker-compose up --build -d
```
