# Quy trình Quản trị Dữ liệu, Metadata & Đánh giá Whisper trong NCKH LiemWhisper

Tài liệu này tổng hợp giải pháp kỹ thuật và phương pháp luận nghiên cứu cho toàn bộ các khía cạnh:
1. Quy trình dán nhãn & làm sạch dữ liệu sau thu âm.
2. Quản lý địa chỉ IP, User-Agent & Đạo đức nghiên cứu (IRB/Ethics).
3. Danh mục Metadata chuẩn bài báo khoa học (Audio, Speaker, Acoustic, Linguistic).
4. Trang giới thiệu đề tài & Đồng thuận nghiên cứu (Briefing & Informed Consent).
5. Checkpoint báo cáo khảo sát (Survey Analytics).
6. Phương pháp luận so sánh & đánh giá mô hình Whisper (% nhận diện, WER, CER, Term Recall).
7. Kiến trúc tích hợp đăng nhập Google (Google OAuth 2.0).

---

## 1. Quy trình Dán nhãn & Làm sạch dữ liệu phục vụ NCKH

Để đưa ngữ liệu thu được từ công cụ vào huấn luyện và đánh giá mô hình (PhoWhisper, Speech-Text Contrastive Retrieval), quy trình gồm 4 giai đoạn chuẩn:

```
[ Thu âm thô ] ──► [ Kiểm định kỹ thuật tự động ] ──► [ Dán nhãn / Verbatim Transcript ] ──► [ Phân chia Split chuẩn NCKH ]
```

### Bước 1: Kiểm định kỹ thuật tự động (Automated Audio QC)
- **Lọc tín hiệu clipping (vỡ tiếng):** Loại bỏ bản ghi có biên độ chạm ngưỡng cực đại quá 5% tổng thời lượng.
- **Lọc im lặng (Silence / Low-volume):** Tự động loại bỏ file có RMS < -45 dBFS hoặc thời lượng thực tế < 2 giây.
- **Chuẩn hóa định dạng chuẩn ML:** Chuyển đổi toàn bộ audio sang **16-kHz mono WAV (PCM 16-bit)** mà vẫn lưu trữ file gốc WebM/MP4 để đối chiếu.

### Bước 2: Dán nhãn & Hiệu chỉnh văn bản thực phát âm (Verbatim Correction)
- Trong quá trình đọc, sinh viên có thể phát âm vấp, lặp từ, hoặc thay đổi nhẹ so với prompt text ban đầu.
- **Quy tắc vàng của NCKH:** *Transcript đánh giá phải phản ánh chính xác 100% lời nói thực tế của người đọc (Verbatim Transcript), không dùng prompt text lý thuyết để tính WER*.
- Người kiểm duyệt (Reviewer) sử dụng giao diện Admin Reviewer của LiemWhisper để nghe lại, duyệt (Approve / Reject / Rerecord) và gõ lại transcript thực tế nếu sinh viên đọc sai.

### Bước 3: Phân chia tập dữ liệu chống rò rỉ (Leakage-resistant Split)
- **Speaker-independent split:** Người nói trong tập Test **tuyệt đối không được xuất hiện** trong tập Train/Dev.
- **Unseen Term split:** Nhóm một số thuật ngữ kiểm thử (ví dụ: `decision table`, `cyclomatic complexity`) thành tập kiểm thử riêng để chứng minh mô hình có khả năng nhận dạng thuật ngữ mới chưa từng thấy lúc train.

---

## 2. Lưu địa chỉ IP, User-Agent & Bảo mật Danh tính

### Triển khai kỹ thuật:
- Hệ thống đã tích hợp tự động trích xuất IP từ header `x-forwarded-for` (hỗ trợ reverse proxy như Nginx, Render, Cloudflare, Vercel) hoặc socket client host.
- Ghi nhận thông tin User-Agent (trình duyệt, hệ điều hành: iOS, Android, Windows, macOS).
- Lưu trữ an toàn trong trường `survey` của bảng `participants` và cột `client_ip` của bảng `recordings`.

### Đạo đức nghiên cứu (Research Ethics / IRB):
- **Nguyên tắc ẩn danh (Pseudonymization):** Địa chỉ IP chỉ dùng cho mục đích audit kỹ thuật nội bộ (ngăn chặn spam bot, phát hiện một người tạo nhiều tài khoản giả).
- **Tuyệt đối không đưa IP hoặc email sinh viên vào Manifest public** của bài báo khoa học. File export chỉ chứa `participant_code` (mã ẩn danh như `P_A1B2C3`).

---

## 3. Danh mục Metadata chuẩn cho bài báo NCKH

Để bài báo có độ tin cậy học thuật cao (Reproducibility), metadata thu thập được phân thành 4 nhóm:

| Nhóm Metadata | Các trường thu thập | Mục đích khoa học |
| :--- | :--- | :--- |
| **Người nói (Speaker)** | Năm sinh (`birth_year`), Năm học (`academic_year`), Giọng vùng miền (`accent_region`), Tự đánh giá tiếng Anh (`english_level`) | Phân tích phương sai kết quả ASR theo lứa tuổi và giọng địa phương (Bắc/Trung/Nam). |
| **Âm học & Môi trường** | Loại mic (`microphone`), Độ ồn môi trường (`environment_noise`), Thiết bị thu âm | Đo lường độ bền vững (robustness) của mô hình trước tiếng ồn thực tế. |
| **Kỹ thuật âm thanh** | Format, sample rate, bitrate, duration, dung lượng (bytes), SHA-256 hash | Đảm bảo tính toàn vẹn dữ liệu, chống trùng lặp. |
| **Ngữ liệu & Gán nhãn** | Prompt text, Verbatim transcript, Danh sách từ khóa (`target_terms`), Category, Độ khó | Phục vụ tính điểm Recall thuật ngữ và phân loại theo module kiến thức. |

---

## 4. Trang thông tin (Briefing) & Informed Consent trước khi thu âm

Giao diện sinh viên đã được nâng cấp thẻ **Thông tin đề tài nghiên cứu (Briefing Card)** với 3 cam kết rõ ràng:
1. **Mục đích:** Thu âm phục vụ đề tài nghiên cứu khoa học về nhận dạng tiếng nói tiếng Anh chuyên ngành CNTT (SWT) xen lẫn tiếng Việt.
2. **Hướng dẫn người đọc:** Khẳng định đây **không phải bài thi kiểm tra kiến thức**, sinh viên chỉ cần đọc tự nhiên theo kịch bản câu hỏi & đáp có sẵn.
3. **Quyền tự nguyện & Rút lui (Right to Withdraw):** Không chấm điểm học tập; có nút **Rút lui (Withdraw)** để xóa toàn bộ dữ liệu âm thanh cá nhân bất kỳ lúc nào theo quy chuẩn GDPR/IRB.

---

## 5. Checkpoint báo cáo Survey (Survey Analytics)

Thông tin khảo sát nhân khẩu học được xuất kèm trong file manifest:
- **`GET /api/v1/admin/export/manifest.json`**: Trả về danh sách bản ghi kèm đầy đủ trường `survey` (năm sinh, năm học, môi trường, mic, accent, IP).
- **Thống kê bảng báo cáo:**
  - Tỷ lệ phân bố lứa tuổi: Sinh viên 2003, 2004, 2005...
  - Tỷ lệ giọng vùng miền: Miền Bắc, Miền Trung, Miền Nam.
  - Tỷ lệ thiết bị: Tai nghe có mic, AirPods/Bluetooth, Mic laptop, Mic rời.
  - Tỷ lệ tiếng ồn: Phòng yên tĩnh vs Có tiếng quạt/tạp âm.

---

## 6. Đánh giá Whisper & So sánh các mô hình (% nhận diện, WER, CER, Term Recall)

Để trả lời câu hỏi *"Chạy qua Whisper dịch được bao nhiêu % và so sánh với các Whisper khác"*, hệ thống cung cấp script đánh giá:
`research/src/liemwhisper/evaluate_whisper.py`

### 3 chỉ số đánh giá cốt lõi:

#### 1. Word Error Rate (WER) — Tỷ lệ lỗi cấp độ từ:
$$\text{WER} = \frac{S + D + I}{N} \times 100\%$$
*(Trong đó: $S$ là từ bị thay thế, $D$ là từ bị xóa, $I$ là từ bị chèn thêm, $N$ là tổng số từ của câu chuẩn).*

#### 2. Character Error Rate (CER) — Tỷ lệ lỗi cấp độ ký tự:
Đo lường độ chính xác ở cấp độ âm vị/chữ cái tiếng Việt (đặc biệt các dấu thanh tiếng Việt).

#### 3. Technical Term Recall (%) — Tỷ lệ nhận diện đúng từ khóa kỹ thuật:
Đây là **đóng góp khoa học then chốt** của đề tài LiemWhisper:
$$\text{Term Recall} = \frac{\text{Số thuật ngữ CNTT mô hình nhận diện chính xác}}{\text{Tổng số thuật ngữ tiếng Anh mục tiêu}} \times 100\%$$
*Ví dụ:* Với câu chứa thuật ngữ `["boundary value analysis", "test case"]`, nếu mô hình phiên âm ra *"bao đơ ri va lưu a na ly sít"* thì dù WER có thể thấp, nhưng Term Recall = 0%. Mô hình đề xuất của LiemWhisper sẽ nâng tỷ lệ này lên mức tối đa.

### Lệnh chạy so sánh benchmark:
```powershell
python research/src/liemwhisper/evaluate_whisper.py --manifest manifest.json --models openai/whisper-tiny openai/whisper-base vinai/phowhisper-base liemwhisper-proposed --output_csv whisper_benchmark.csv
```

---

## 7. Kiến trúc Tích hợp Đăng nhập Google (Google OAuth 2.0)

Để sinh viên đăng nhập trực tiếp bằng tài khoản Google (khuyên dùng email trường `@fpt.edu.vn`):

### Sơ đồ luồng xác thực:
```
[ Sinh viên ] ──(Click Đăng nhập Google)──► [ Google Accounts ]
      │                                             │
      ▼                                             ▼ (Trả về ID Token / JWT)
[ Web Client ] ────(Gửi ID Token)──────► [ FastAPI Backend ]
                                                    │
                                                    ▼ (Verify qua google-auth)
                                          [ Khóa domain @fpt.edu.vn ]
                                                    │
                                                    ▼
                                          [ Cấp Participant Token ]
```

### Các bước triển khai:
1. **Google Cloud Console:** Tạo OAuth 2.0 Client ID (Web Application), thêm Authorized JavaScript origins (`http://localhost:3000`, domain production).
2. **Backend (`tool/backend`):**
   - Cài đặt thư viện: `pip install google-auth requests`
   - Tạo endpoint: `POST /api/v1/auth/google`
   - Xác thực token:
     ```python
     from google.oauth2 import id_token
     from google.auth.transport import requests

     idinfo = id_token.verify_oauth2_token(token, requests.Request(), GOOGLE_CLIENT_ID)
     email = idinfo["email"]
     # Kiểm tra domain trường
     if not email.endswith("@fpt.edu.vn"):
         raise HTTPException(403, "Vui lòng sử dụng email sinh viên trường (@fpt.edu.vn)")
     ```
3. **Frontend (`tool/client`):**
   - Tích hợp `@react-oauth/google` hoặc Google Identity Services button (`accounts.google.com/gsi/client`).
   - Khi đăng nhập thành công, tự động điền `participant_code` thành mã số sinh viên trích xuất từ email (ví dụ: `se194007@fpt.edu.vn` -> `SE194007`).
