# LiemWhisper — Danh sách công việc nghiên cứu và phát triển

> Trạng thái: các công việc được xem là đang lên kế hoạch, trừ khi đã được đánh dấu hoàn thành, có phần triển khai đã hợp nhất và có bản ghi xác minh. Ưu tiên: xây dựng nền tảng thu thập dữ liệu an toàn trước, thực hiện thí nghiệm truy hồi độc lập sau.

## Giai đoạn 0 — Quản trị và thiết lập dự án
- [x] Xác định phạm vi sản phẩm/nghiên cứu và cấu trúc thư mục trong README.
- [ ] Xác nhận việc thẩm định đạo đức của trường đại học hoặc hội đồng tương đương IRB trước khi tuyển sinh viên tham gia.
- [ ] Xác định quy trình đồng ý tham gia và rút lui (không áp dụng hình thức bất lợi về học tập khi từ chối).
- [ ] Xác định giấy phép bộ dữ liệu, cơ chế ẩn danh người nói, thời hạn lưu giữ, quy trình xóa và các vai trò truy cập.
- [ ] Thiết lập môi trường phát triển cục bộ, định dạng mã, kiểm tra mã tĩnh (lint), kiểm thử, cấu hình container và pipeline Jenkins.
- [ ] Bảo vệ thông tin bí mật và dữ liệu định danh cá nhân; ghi lại quy trình sao lưu.

## Giai đoạn 1 — Backend / Quản trị — Sản phẩm khả dụng tối thiểu (MVP)
- [x] Ứng dụng FastAPI, lược đồ SQLite (chế độ WAL) / sẵn sàng cho PostgreSQL, tài liệu Swagger và kiểm tra tình trạng dịch vụ.
- [x] Phân quyền theo vai trò (RBAC): Quản trị viên, Người duyệt, Sinh viên; xác thực, token phiên và các trường phục vụ kiểm toán.
- [x] Tạo, đọc, cập nhật, xóa (CRUD) học phần; nhập/tải lên hàng loạt văn bản mẫu đã được phê duyệt, kèm trích xuất thuật ngữ tự động.
- [x] Mẫu câu/phát ngôn cần đọc: ngôn ngữ, văn bản kỳ vọng, target_terms, độ khó, danh mục.
- [x] Tạo phân công đọc các mẫu cho từng người đã đồng ý tham gia, kèm theo dõi tiến độ.
- [x] Cấu hình khảo sát; lưu hồ sơ đồng ý tham gia với phiên bản chính sách và dấu thời gian, endpoint rút lui/xóa dữ liệu.
- [x] Tải lên bản ghi âm có tính lũy đẳng (gửi lại cùng yêu cầu không tạo bản ghi trùng), xác thực nhiều định dạng (WebM, MP4, WAV, OGG), giới hạn dung lượng tải lên.
- [x] API truyền phát âm thanh hỗ trợ yêu cầu theo dải byte (Range request), cho phép người duyệt và người tham gia nghe trực tiếp trong trình duyệt.
- [x] API gán nhãn dành cho người duyệt: phát âm thanh, chỉnh sửa bản chép lời đúng từng lời đã nói, trạng thái (phê duyệt/từ chối/thu âm lại), ghi chú.
- [x] Bảng điều khiển quản trị: tiến độ thu thập, độ bao phủ của từng mẫu đọc, hàng đợi duyệt, số phút ghi âm đã được phê duyệt.
- [x] Xuất danh mục dữ liệu (manifest) đã được phê duyệt và đủ điều kiện theo sự đồng ý của người tham gia (JSON, CSV), cùng tệp ZIP đầy đủ (âm thanh + các manifest).
- [x] Kiểm thử tự động: tải lên nhiều định dạng, âm thanh không hợp lệ, truyền phát, luồng duyệt, rút lui và xuất dữ liệu.

## Giai đoạn 2 — Thu âm trên web dành cho sinh viên — MVP
- [x] Các trang Next.js thích ứng với kích thước màn hình: lời mời/đăng nhập, đồng ý tham gia sau khi được cung cấp đầy đủ thông tin, khảo sát, hàng đợi thu âm theo từng thẻ.
- [x] Quyền truy cập micro trên trình duyệt, thu/dừng, hiển thị dạng sóng theo thời gian thực, nghe lại, thu âm lại và gửi.
- [x] Hiển thị chính xác văn bản mẫu do máy chủ cung cấp, làm nổi bật thuật ngữ chuyên môn và hướng dẫn thu âm.
- [x] Lưu trạng thái phân công trên máy chủ và localStorage, hiển thị rõ các lượt tải lên đang chờ/đã được xác nhận.
- [x] Xử lý trường hợp bị từ chối quyền micro, tải lại trình duyệt, tự động tiếp tục và âm thanh trên nhiều trình duyệt (Chrome/Edge WebM, Safari iOS MP4).
- [x] Hỗ trợ khả năng tiếp cận và thiết kế thích ứng thân thiện với thiết bị di động, màn hình chúc mừng hoàn thành.
- [x] Giới hạn việc thu thập cho người tham gia được cấp quyền và ngăn lộ nội dung mẫu đọc cho người không có quyền truy cập.

## Giai đoạn 3 — Chất lượng dữ liệu và gán nhãn
- [ ] Lược đồ manifest của bộ dữ liệu gồm người nói, âm thanh, mẫu đọc, bản chép lời, nhãn ngôn ngữ và các đoạn chứa thuật ngữ.
- [ ] Xác minh tần số lấy mẫu/codec/thời lượng của bản gốc; tạo bản WAV mono 16 kHz mà không ghi đè bản gốc.
- [ ] Kiểm tra chất lượng: méo do vượt ngưỡng (clipping), khoảng lặng, bản trùng lặp, phát ngôn bị cắt cụt, bản ghi âm có âm lượng thấp.
- [ ] Có ít nhất hai người gán nhãn độc lập cho một tập con, quy trình phân xử bất đồng và báo cáo mức độ đồng thuận.
- [ ] Chia tập dữ liệu theo người nói và thuật ngữ mục tiêu; tạo tập kiểm thử ngoài miền khi dữ liệu cho phép.
- [ ] Bản chép lời đã được con người xác minh không đồng nhất với văn bản mẫu kỳ vọng; đánh dấu các lượt đọc thiếu hoặc thay đổi nội dung.
- [ ] Chỉ công bố số liệu thống kê tổng hợp/đã ẩn danh, trừ khi có quyền rõ ràng cho phép công bố các mẫu dữ liệu.

## Giai đoạn 4 — Các phương pháp cơ sở cho nghiên cứu
- [ ] Cố định phiên bản mô hình/checkpoint và cấu hình thí nghiệm.
- [ ] Bộ mã hóa tiếng nói PhoWhisper giữ cố định trọng số + phép chiếu sau khi gộp đặc trưng (pooling).
- [ ] Bộ mã hóa văn bản đa ngôn ngữ + phép chiếu; chuẩn hóa vào không gian chung 256/512 chiều.
- [ ] Bộ mã hóa văn bản G2P/IPA làm phương pháp cơ sở và truy hồi chỉ dựa trên âm vị.
- [ ] InfoNCE đối xứng có xử lý các mẫu dương trùng lặp.
- [ ] Tìm kiếm vector bằng FAISS và truy hồi Top-K trên các thuật ngữ chuyên môn được nói riêng lẻ.
- [ ] So sánh với các phương pháp cơ sở: đối sánh từ vựng, phép chiếu chưa huấn luyện và các phương pháp truy hồi tiếng nói–văn bản hiện có.
- [ ] Đánh giá Recall@1, Recall@5, MRR, độ chính xác trên mẫu âm khó (hard negative), độ hiệu chuẩn và độ trễ.
- [ ] Báo cáo khoảng tin cậy có tính đến việc phân cụm theo người nói, kèm tập kiểm thử thuật ngữ chưa từng xuất hiện và không bị rò rỉ dữ liệu.

## Giai đoạn 5 — Phương pháp đề xuất có xét đến ngữ âm
- [ ] Giám sát theo âm vị bằng nhãn phát âm và các biến thể đã được xác minh độc lập.
- [ ] Sử dụng mẫu âm khó dựa trên khả năng nhầm lẫn về âm học (ví dụ: test case / test data).
- [ ] So sánh các bộ mã hóa chỉ dùng văn bản, chỉ dùng âm vị và kết hợp văn bản + âm vị.
- [ ] Thí nghiệm loại bỏ/thay đổi thành phần (ablation) đối với hàm mất mát ngữ âm, trọng số kết hợp, số chiều phép chiếu và bộ mã hóa giữ cố định trọng số so với điều chỉnh bằng LoRA.
- [ ] Bổ sung các đoạn tiếng nói **không chứa thuật ngữ trong bảng thuật ngữ** và báo cáo các trường hợp chèn nhầm do dương tính giả.
- [ ] Kiểm thử với bảng thuật ngữ của học phần mới mà không huấn luyện lại mô hình nhận dạng tiếng nói tự động (ASR).

## Giai đoạn 6 — Ứng dụng vào ASR ở bước sau (tùy chọn, sau khi có kết quả truy hồi)
- [ ] Xác định vị trí các đoạn âm thanh nghi vấn (căn chỉnh cưỡng bức/cửa sổ trượt).
- [ ] Truy hồi các ứng viên từ bảng thuật ngữ trích xuất từ sách.
- [ ] Xác minh ứng viên bằng âm thanh gốc; không tự động sửa chỉ dựa trên mức độ liên quan đến nội dung sách.
- [ ] So sánh đầu ra gốc của PhoWhisper, cơ chế từ khóa ưu tiên (hotwords), truy hồi ngữ nghĩa, truy hồi ngữ âm và phương pháp kết hợp được đề xuất.
- [ ] Đánh giá WER/CER, độ thu hồi thuật ngữ chuyên môn, các trường hợp chèn sai và hệ số thời gian thực.
- [ ] Lưu riêng bản chép lời gốc và bản đã chỉnh sửa, đặc biệt khi chấm thi.

## Giai đoạn 7 — Bài báo và khả năng tái lập
- [ ] Lập ma trận tổng quan tài liệu với trích dẫn nguồn sơ cấp và mô tả chính xác đóng góp của các công trình trước.
- [ ] Đăng ký trước các câu hỏi nghiên cứu (RQ), quy trình xây dựng bộ dữ liệu, cách chia tập, hàm mất mát và các chỉ số đánh giá chính.
- [ ] Cung cấp cấu hình có thể tái lập, giá trị seed cố định, checkpoint được cố định phiên bản và các tập lệnh.
- [ ] Báo cáo kết quả không đạt kỳ vọng, trường hợp thất bại, sự khác biệt giữa người nói và các vấn đề đạo đức.
- [ ] Soạn thảo các phần Giới thiệu / Công trình liên quan / Phương pháp / Thiết lập thí nghiệm / Kết quả / Hạn chế.
- [ ] Kiểm tra thông báo mời gửi bài (CFP)/phạm vi tạp chí phù hợp, tình trạng lập chỉ mục và phân hạng tứ phân vị theo năm công bố, lệ phí và hạn nộp.
- [ ] Không bao giờ báo cáo số liệu đánh giá bịa đặt hoặc làm lộ âm thanh/thông tin định danh cá nhân (PII) của người tham gia nghiên cứu.

## Các mốc nghiệm thu đề xuất
- **M1 Thí điểm thu thập:** người dùng thử đã đồng ý tham gia có thể gửi và xem lại bản ghi âm, với hệ thống lưu trữ có khả năng khôi phục.
- **M2 Bộ dữ liệu hợp lệ:** manifest đã được xác minh, giấy phép/sự đồng ý hợp lệ, gán nhãn nhất quán và các tập dữ liệu được chia không gây rò rỉ.
- **M3 Phương pháp truy hồi cơ sở:** tập lệnh huấn luyện chạy được trên một mẫu dữ liệu nhỏ và tạo ra kết quả Recall@K có thể tái lập.
- **M4 Phương pháp đề xuất:** các thí nghiệm ablation cho thấy liệu ngữ âm có cải thiện khả năng truy hồi đối với người nói/thuật ngữ chưa từng xuất hiện hay không.
- **M5 Bài báo:** các bảng kết quả khớp với cấu hình và đầu ra thí nghiệm đã lưu trữ.
