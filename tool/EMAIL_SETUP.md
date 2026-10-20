# Thư cảm ơn qua Gmail

Mặc định `EMAIL_PROVIDER=gmail_api`. Thư được gửi qua HTTPS bằng tài khoản Google
đã liên kết Drive của quản trị viên. Không dùng tài khoản Google của người tham gia.
Render Free chặn SMTP, nên không dùng SMTP Gmail trên gói này.

## Thiết lập một lần

1. Mở Google Cloud Console, chọn đúng project chứa OAuth client đang dùng cho Drive.
2. Vào APIs & Services → Library → Gmail API → Enable.
3. Trong Google Auth Platform → Data Access, thêm scope
   `https://www.googleapis.com/auth/gmail.send`.
4. Triển khai backend mới trên Render và frontend mới trên Vercel.
5. Đăng nhập quản trị LiemWhisper, chọn **Liên kết lại Google Drive**,
   dùng đúng tài khoản đang lưu dữ liệu và đồng ý quyền gửi email.
6. Mục **Thư cảm ơn** hiển thị tài khoản gửi và trạng thái từng thư.
   Khi đã sửa cấu hình, chọn **Thử gửi lại** cho những thư thất bại.

Nếu ứng dụng OAuth còn ở chế độ Testing, tài khoản gửi phải có trong Test users.
Tuân theo yêu cầu xác minh của Google trước khi mở ứng dụng cho người dùng ngoài.
Không dán refresh token, client secret hay mật khẩu vào giao diện hoặc Git.

## Trạng thái và tránh trùng

Hoàn thành phiên và tạo hàng đợi thư được lưu cùng một giao dịch database.
Worker kiểm tra hàng đợi mỗi 10 giây khi server đang chạy, độc lập với đồng bộ Drive.
Claim nguyên tử ngăn nhiều worker gửi cùng một thư.
Render Free có thể ngủ khi không hoạt động; thư pending tiếp tục khi server thức lại.

- `pending` / `sending`: chờ gửi / đang gửi.
- `sent`: dịch vụ gửi thư đã chấp nhận; không bảo đảm thư vào inbox thay vì Spam.
- `failed`: gửi thất bại đã xác định; quản trị viên có thể thử lại.
- `unknown`: mất kết nối hoặc worker dừng giữa chừng; có thể thư đã gửi.
  Kiểm tra mục Sent của Gmail. Không tự gửi lại trạng thái này để tránh trùng.
- `untracked`: phiên hoàn thành trước khi có theo dõi; không tự động gửi lại.

Mỗi người tham gia có một bản ghi giao thư. Không tự gửi hàng loạt cho các phiên cũ.
Kiểm thử dùng HTTP giả lập, không gửi thư đến người tham gia.

Tài liệu: [Gmail messages.send](https://developers.google.com/workspace/gmail/api/reference/rest/v1/users.messages/send),
[Giới hạn Render Free](https://render.com/docs/free).
