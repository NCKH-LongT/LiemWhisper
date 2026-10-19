# Giao diện nghiên cứu LiemWhisper

- Design tokens và responsive: `app/globals.css`. Stone ấm, navy cho hành động chính; màu trạng thái chỉ dùng khi cần. Dark mode theo `prefers-color-scheme` của hệ thống.
- Thành phần dùng chung: `components/ui.tsx` gồm Button, Card, Badge, Select có điều khiển bàn phím, Progress, Toast, Skeleton và hộp thoại xác nhận dùng native dialog.
- Màn hình sinh viên, hoàn thành và điều hướng quản trị: `app/page.tsx`. Giữ các endpoint, dữ liệu gửi đi và quy tắc khóa thu âm sau hoàn thành.
- Thống kê: `components/AdminDashboardDuration.tsx`. Bốn KPI trung tính; lọc/sắp xếp như cũ; hiển thị 20 dòng mỗi lần, mở rộng nội dung; danh sách thẻ ở màn hình nhỏ.
- Drive: `components/AdminDrivePanel.tsx`. Phân cấp thao tác, sao chép mã thư mục, xác nhận trước dọn dẹp.
- Không thêm dependency. Các bảng quản lý khác giữ thao tác hiện có và dùng chung bảng màu.

Kiểm tra: 32 bài test hiện có; TypeScript; Next.js production build. Hai lỗi kiểu trong fixture kiểm thử được sửa, fixture Google được bổ sung mock cho hook hộp thoại.

Cần kiểm tra trực quan bổ sung trên viewport 440 × 956 và 1440 × 900, cùng các luồng Google/microphone/Drive thực tế. Công cụ browser của phiên làm việc không truy cập được localhost (timeout), nên chưa xác nhận các luồng này bằng trình duyệt. Không khẳng định đạt WCAG AA toàn bộ ứng dụng chỉ dựa trên build.
