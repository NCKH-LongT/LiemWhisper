# Triển khai hệ thống: Vercel + Render (PostgreSQL + Google Drive cá nhân)

## Kiến trúc lưu trữ dữ liệu kép

Theo yêu cầu lưu trữ đầy đủ ở cả SQL và Cloud Drive:
- **Vercel**: Chạy Frontend Next.js (`tool/client`), giao diện responsive cho điện thoại và máy tính.
- **Render Web Service**: Chạy Backend FastAPI (`tool/backend`).
- **Render PostgreSQL Database**: Lưu trữ dữ liệu có cấu trúc và **toàn bộ file âm thanh nhị phân (BYTEA)** trong bảng `recording_audio`.
- **Google Drive cá nhân**: Tự động đồng bộ bản sao đầy đủ của từng file âm thanh qua hàng đợi bền vững (durable outbox worker) và xác thực toàn vẹn bằng checksum SHA-256 sau khi tải lên.
- **Bảo mật**: Admin đăng nhập bằng phiên session 8h có rate-limiting chống dò mật khẩu; học viên đăng nhập bằng mã truy cập bí mật; Google refresh token được mã hóa bằng Fernet (`TOKEN_ENCRYPTION_KEY`).

Blueprint nằm tại: `tool/render.yaml`. Cấu hình Vercel nằm tại: `tool/client/vercel.json`.

---

## 1. Chuẩn bị Google Cloud OAuth (Drive cá nhân)

1. Mở [Google Cloud Console](https://console.cloud.google.com/) bằng tài khoản Google cá nhân muốn lưu file.
2. Tạo Project mới: `LiemWhisper`.
3. Vào **APIs & Services → Library**, tìm **Google Drive API** và bấm **Enable**.
4. Vào **Google Auth Platform**:
   - Chọn User Type: **External**.
   - Điền App name: `LiemWhisper`, email hỗ trợ và email liên hệ của bạn.
   - Tại mục **Audience → Test users**, thêm chính địa chỉ email Google của bạn.
   - Tại mục **Data Access → Scopes**, chọn: `https://www.googleapis.com/auth/drive.file`.
5. Chưa tạo OAuth Client ngay; bạn sẽ tạo sau khi có URL chính thức của Backend Render ở Bước 2.

---

## 2. Deploy Backend & PostgreSQL trên Render

1. Đăng nhập [Render Dashboard](https://dashboard.render.com/).
2. Chọn **New → Blueprint** → kết nối repository `NCKH-LongT/LiemWhisper`.
3. Chọn nhánh `main` (hoặc `dev`), Blueprint Path: **`tool/render.yaml`**.
4. Render sẽ hiển thị danh sách tài nguyên tạo mới:
   - **PostgreSQL Database** (`liemwhisper-db`, Region: Singapore, Plan: Starter).
   - **Web Service** (`liemwhisper-api`, Region: Singapore, Plan: Starter).
5. Render sẽ yêu cầu nhập các biến môi trường chưa có giá trị cố định (`sync: false`):
   - `TOKEN_ENCRYPTION_KEY`: Sinh khóa bảo mật 32-byte Fernet bằng lệnh terminal:
     ```bash
     python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
     ```
   - `GOOGLE_CLIENT_ID` & `GOOGLE_CLIENT_SECRET`: Tạm để trống hoặc điền tạm, sẽ cập nhật ở Bước 3.
   - `GOOGLE_REDIRECT_URI`: Sẽ điền theo domain Render ở Bước 3.
   - `WEB_PUBLIC_URL`: Tạm đặt `https://frontend-pending.vercel.app`, sẽ sửa thành domain Vercel thật sau khi deploy frontend.
6. Xác nhận tạo tài nguyên và đợi Render build và deploy xong.
7. Ghi lại URL HTTPS của Backend Render, ví dụ: `https://liemwhisper-api.onrender.com`.

---

## 3. Tạo OAuth Client trên Google và liên kết với Render

1. Quay lại Google Cloud Console → **APIs & Services → Credentials**.
2. Bấm **Create Credentials → OAuth client ID**:
   - Application type: **Web application**.
   - Name: `LiemWhisper Backend`.
   - **Authorized redirect URIs**: Điền chính xác URL callback của Render:
     ```text
     https://liemwhisper-api.onrender.com/api/v1/admin/drive/callback
     ```
     *(Thay `liemwhisper-api.onrender.com` bằng domain thật của bạn, không có dấu gạch chéo ở cuối)*.
3. Bấm **Create** → Copy **Client ID** và **Client Secret**.
4. Quay lại Render Dashboard → Web Service `liemwhisper-api` → **Environment**:
   - Cập nhật `GOOGLE_CLIENT_ID` = Client ID vừa copy.
   - Cập nhật `GOOGLE_CLIENT_SECRET` = Client Secret vừa copy.
   - Cập nhật `GOOGLE_REDIRECT_URI` = `https://liemwhisper-api.onrender.com/api/v1/admin/drive/callback`.
5. Render sẽ tự động lưu và restart backend.

---

## 4. Deploy Frontend trên Vercel

1. Đăng nhập [Vercel](https://vercel.com/) → **Add New → Project**.
2. Import repository `NCKH-LongT/LiemWhisper`.
3. Cấu hình dự án:
   - Framework Preset: **Next.js**.
   - Root Directory: Bấm Edit và chọn **`tool/client`**.
   - Build & Development Settings: Giữ mặc định (`npm ci`, `npm run build`).
4. Thêm biến môi trường Production:
   - `NEXT_PUBLIC_API_URL` = `https://liemwhisper-api.onrender.com` *(URL Backend Render thật từ Bước 2)*.
5. Bấm **Deploy**.
6. Sau khi deploy xong, ghi lại domain chính thức của Vercel (ví dụ `https://liemwhisper.vercel.app`).
7. Quay lại Render Dashboard → `liemwhisper-api` → **Environment**:
   - Sửa `WEB_PUBLIC_URL` = `https://liemwhisper.vercel.app` để cho phép CORS.

---

## 5. Kích hoạt liên kết Google Drive trong Trang Quản trị

1. Mở trang web Vercel vừa deploy trong trình duyệt.
2. Chuyển sang tab **Quản trị viên**:
   - Nhập mật khẩu quản trị (`ADMIN_API_KEY` được sinh tự động trên Render Dashboard trong tab Environment).
   - Đăng nhập vào Admin Dashboard.
3. Trong tab **Thống kê / Tổng quan**, tìm mục **Trạng thái lưu trữ Google Drive**:
   - Nhấn **Kết nối Google Drive**.
   - Trình duyệt sẽ chuyển hướng sang trang đăng nhập Google.
   - Đăng nhập đúng tài khoản Google cá nhân của bạn, kiểm tra quyền `drive.file` và nhấn **Allow (Cho phép)**.
   - Google sẽ redirect về callback và báo **Kết nối Google Drive thành công**.
4. Quay lại trang Quản trị, trạng thái sẽ hiển thị: **Đã kết nối**, kèm ID thư mục riêng tư `LiemWhisper Recordings`.
5. Từ thời điểm này, mọi bản ghi do sinh viên gửi lên sẽ được lưu đầy đủ vào PostgreSQL và tự động đồng bộ bản sao sang Google Drive của bạn.

---

## 6. Nạp câu hỏi nghiên cứu mẫu (Seed Prompts)

Sau khi PostgreSQL hoạt động, mở **Shell** của Web Service trên Render Dashboard và chạy:

```bash
cd tool && PYTHONPATH=backend python scripts/seed_prompts.py
```

Hoặc vào trang Admin → tab **Quản lý câu hỏi** để nhập trực tiếp danh sách câu hỏi theo môn học.
