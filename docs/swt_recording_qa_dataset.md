# Bộ câu hỏi & Câu trả lời thu âm môn Kiểm thử phần mềm (SWT / Software Testing)

> **Mục đích sử dụng:** Tài liệu này được thiết kế dành riêng cho **công cụ thu thập dữ liệu âm thanh và nhận dạng tiếng nói (LiemWhisper)**. 
> Vì đây là **công cụ thu âm giọng nói kỹ thuật** (Voice Dataset Collection) chứ **không phải bài kiểm tra trình độ**, mọi câu hỏi đều có sẵn câu trả lời chuẩn xác và **câu đọc mẫu (Reading Script)** để sinh viên/người tham gia chỉ cần nhìn màn hình và đọc lưu loát, tự nhiên.

---

## 1. Hướng dẫn dành cho người thu âm
- **Tốc độ đọc:** Đọc với tốc độ vừa phải, tự nhiên như khi trao đổi kỹ thuật hàng ngày.
- **Phát âm từ tiếng Anh (Code-switched terms):** Đọc rõ ràng các thuật ngữ chuyên ngành (ví dụ: *unit test, regression testing, boundary value analysis, mock object, pipeline...*).
- **Thời lượng mỗi câu:** Từ **8 đến 15 giây** (khoảng 20–35 từ), có khoảng dừng tự nhiên để không bị hụt hơi.
- **Có 2 hình thức đọc tùy theo cài đặt của giảng viên/nghiên cứu viên:**
  - **Hình thức 1 (Khuyên dùng cho ASR):** Đọc trực tiếp câu phát biểu hoàn chỉnh trong mục **Lời thoại đọc thu âm**.
  - **Hình thức 2 (Hỏi - Đáp đối thoại):** Đọc cả câu: *"Hỏi: [Câu hỏi]? - Đáp: [Câu trả lời]"*.

---

## 2. Danh sách 40 câu hỏi & lời thoại đọc thu âm

### Module 1: Khái niệm cốt lõi & Nguyên lý kiểm thử (Fundamentals)

#### Câu 01: Phân biệt Error, Defect và Failure
- **Câu hỏi:** Phân biệt Error, Defect và Failure trong kiểm thử phần mềm?
- **Câu trả lời:** Error là sai sót của con người khi lập trình, Defect là khiếm khuyết trong mã nguồn, còn Failure là sự cố hệ thống hoạt động sai thực tế so với kỳ vọng.
- **Lời thoại đọc thu âm:** *"Error là sai sót do lập trình viên tạo ra, defect là lỗi nằm trong source code, còn failure xảy ra khi hệ thống chạy sai trong thực tế."*
- **Thuật ngữ trọng tâm:** `error`, `defect`, `source code`, `failure`

#### Câu 02: Verification và Validation
- **Câu hỏi:** Verification và Validation khác nhau như thế nào?
- **Câu trả lời:** Verification kiểm tra sản phẩm có được xây dựng đúng theo quy trình và tài liệu đặc tả hay không, còn Validation xác nhận sản phẩm có đáp ứng đúng nhu cầu thực tế của khách hàng.
- **Lời thoại đọc thu âm:** *"Verification kiểm tra xem chúng ta có xây dựng phần mềm đúng đặc tả hay không, còn validation xác nhận sản phẩm có đáp ứng đúng nhu cầu của khách hàng."*
- **Thuật ngữ trọng tâm:** `verification`, `validation`

#### Câu 03: Quality Assurance (QA) và Quality Control (QC)
- **Câu hỏi:** Sự khác biệt giữa Quality Assurance và Quality Control là gì?
- **Câu trả lời:** QA tập trung vào việc cải tiến quy trình để ngăn ngừa lỗi phát sinh, còn QC tập trung vào việc kiểm tra trực tiếp sản phẩm để phát hiện lỗi.
- **Lời thoại đọc thu âm:** *"Quality Assurance viết tắt là QA tập trung vào cải tiến quy trình để ngăn ngừa lỗi, còn Quality Control là QC tập trung kiểm tra trực tiếp sản phẩm."*
- **Thuật ngữ trọng tâm:** `Quality Assurance`, `QA`, `Quality Control`, `QC`

#### Câu 04: Nguyên lý Defect Clustering
- **Câu hỏi:** Nguyên lý Defect Clustering trong kiểm thử có ý nghĩa gì?
- **Câu trả lời:** Defect Clustering chỉ ra rằng phần lớn số lượng lỗi thường tập trung vào một số ít module có nghiệp vụ phức tạp hoặc bị thay đổi nhiều nhất.
- **Lời thoại đọc thu âm:** *"Theo nguyên lý defect clustering, phần lớn số lượng bug thường chỉ tập trung vào một số module phức tạp nhất trong hệ thống."*
- **Thuật ngữ trọng tâm:** `defect clustering`, `bug`, `module`

#### Câu 05: Hiện tượng Pesticide Paradox
- **Câu hỏi:** Hiện tượng Pesticide Paradox trong kiểm thử là gì?
- **Câu trả lời:** Nếu lặp đi lặp lại cùng một bộ test case cũ thì sẽ không tìm thêm được lỗi mới, đòi hỏi tester phải định kỳ cập nhật và viết thêm test case.
- **Lời thoại đọc thu âm:** *"Hiệu ứng pesticide paradox cho thấy nếu chỉ chạy lặp lại test case cũ thì không tìm ra bug mới, đòi hỏi tester phải viết thêm kịch bản mới."*
- **Thuật ngữ trọng tâm:** `pesticide paradox`, `test case`, `bug`, `tester`

---

### Module 2: Các cấp độ kiểm thử (Testing Levels)

#### Câu 06: Unit Test
- **Câu hỏi:** Unit test là gì và do ai thực hiện?
- **Câu trả lời:** Unit test là kiểm thử mức đơn vị nhỏ nhất như function hoặc class trong mã nguồn, do chính developer thực thi bằng các test framework.
- **Lời thoại đọc thu âm:** *"Unit test là bước kiểm thử các hàm và method riêng lẻ, do developer viết bằng test framework để phát hiện lỗi sớm khi lập trình."*
- **Thuật ngữ trọng tâm:** `unit test`, `developer`, `test framework`

#### Câu 07: Mock Object và Stub
- **Câu hỏi:** Mock object và Stub được sử dụng để làm gì khi viết unit test?
- **Câu trả lời:** Mock object và Stub là các đối tượng giả lập dùng để thay thế cơ sở dữ liệu hoặc external API khi chạy kiểm thử độc lập.
- **Lời thoại đọc thu âm:** *"Lập trình viên sử dụng mock object và stub để giả lập database hoặc API bên thứ ba khi chạy unit test độc lập."*
- **Thuật ngữ trọng tâm:** `mock object`, `stub`, `database`, `API`, `unit test`

#### Câu 08: Integration Test
- **Câu hỏi:** Integration test là gì và có những chiến lược nào?
- **Câu trả lời:** Integration test kiểm tra sự giao tiếp và tích hợp dữ liệu giữa các module, với các chiến lược phổ biến gồm Big Bang, Top-down và Bottom-up.
- **Lời thoại đọc thu âm:** *"Integration test kiểm tra sự tương tác và truyền dữ liệu giữa các module theo chiến lược top down, bottom up hoặc big bang."*
- **Thuật ngữ trọng tâm:** `integration test`, `module`, `top down`, `bottom up`, `big bang`

#### Câu 09: System Test
- **Câu hỏi:** System testing đánh giá những khía cạnh nào của phần mềm?
- **Câu trả lời:** System testing đánh giá toàn diện hệ thống hoàn chỉnh sau khi tích hợp, bao gồm cả functional testing và non-functional testing trên môi trường staging.
- **Lời thoại đọc thu âm:** *"System testing đánh giá toàn diện hệ thống hoàn chỉnh trên môi trường staging, bao gồm cả functional testing và non functional testing."*
- **Thuật ngữ trọng tâm:** `system testing`, `staging`, `functional testing`, `non functional testing`

#### Câu 10: User Acceptance Testing (UAT)
- **Câu hỏi:** User Acceptance Testing hay UAT là gì?
- **Câu trả lời:** UAT là kiểm thử chấp nhận người dùng do khách hàng hoặc end-user thực hiện để quyết định phần mềm đã sẵn sàng triển khai chính thức hay chưa.
- **Lời thoại đọc thu âm:** *"User acceptance testing viết tắt là UAT do khách hàng thực hiện để xác nhận sản phẩm đã sẵn sàng release lên môi trường production."*
- **Thuật ngữ trọng tâm:** `user acceptance testing`, `UAT`, `release`, `production`

#### Câu 11: End-to-End (E2E) Test
- **Câu hỏi:** End-to-End testing kiểm tra luồng hoạt động như thế nào?
- **Câu trả lời:** E2E testing kiểm tra toàn bộ luồng nghiệp vụ hoàn chỉnh từ giao diện frontend xuống backend service và cơ sở dữ liệu.
- **Lời thoại đọc thu âm:** *"End to end testing kiểm tra toàn bộ trải nghiệm người dùng từ giao diện frontend, qua backend service đến cơ sở dữ liệu."*
- **Thuật ngữ trọng tâm:** `end to end testing`, `frontend`, `backend service`

---

### Module 3: Các loại kiểm thử (Testing Types)

#### Câu 12: Smoke Test và Sanity Test
- **Câu hỏi:** Smoke test khác Sanity test ở điểm nào?
- **Câu trả lời:** Smoke test kiểm tra nhanh các tính năng chính xem bản build có ổn định không, còn Sanity test xác minh sâu vào tính năng vừa được fix bug.
- **Lời thoại đọc thu âm:** *"Smoke test kiểm tra độ ổn định của bản build mới trước khi bàn giao cho QA, còn sanity test tập trung xác minh tính năng vừa fix bug."*
- **Thuật ngữ trọng tâm:** `smoke test`, `build`, `QA`, `sanity test`, `fix bug`

#### Câu 13: Regression Testing
- **Câu hỏi:** Regression testing là gì và tại sao bắt buộc phải thực hiện?
- **Câu trả lời:** Regression testing là kiểm thử hồi quy nhằm đảm bảo việc sửa lỗi hoặc cập nhật tính năng mới không làm hỏng các chức năng cũ đang chạy ổn định.
- **Lời thoại đọc thu âm:** *"Đội ngũ QA cần chạy regression testing tự động để đảm bảo việc update code mới không làm hỏng các tính năng cũ đang chạy ổn định."*
- **Thuật ngữ trọng tâm:** `QA`, `regression testing`, `update code`

#### Câu 14: Load Testing và Stress Testing
- **Câu hỏi:** Load testing và Stress testing khác nhau như thế nào?
- **Câu trả lời:** Load testing kiểm tra hệ thống dưới mức tải dự kiến, còn Stress testing ép tải vượt quá ngưỡng tối đa để xem khả năng chịu lỗi và phục hồi.
- **Lời thoại đọc thu âm:** *"Load testing kiểm tra hệ thống dưới mức tải dự kiến, trong khi stress testing ép tải vượt ngưỡng giới hạn để đánh giá khả năng crash và phục hồi."*
- **Thuật ngữ trọng tâm:** `load testing`, `stress testing`, `crash`

#### Câu 15: Security & Penetration Testing
- **Câu hỏi:** Security testing và Penetration testing có vai trò gì?
- **Câu trả lời:** Giúp rà soát và thâm nhập thử nghiệm nhằm phát hiện các lỗ hổng bảo mật như SQL Injection hay Cross-Site Scripting trước khi bị tấn công.
- **Lời thoại đọc thu âm:** *"Chuyên gia bảo mật thực hiện penetration testing để tìm kiếm lỗ hổng SQL injection và cross site scripting trước khi bàn giao phần mềm."*
- **Thuật ngữ trọng tâm:** `penetration testing`, `SQL injection`, `cross site scripting`

#### Câu 16: Black-box vs White-box Testing
- **Câu hỏi:** Khái niệm Black-box testing và White-box testing là gì?
- **Câu trả lời:** Black-box testing kiểm thử chức năng dựa trên input và output mà không biết mã nguồn, còn White-box testing dựa trên cấu trúc logic và source code bên trong.
- **Lời thoại đọc thu âm:** *"Black box testing chỉ kiểm tra input và output của ứng dụng, còn white box testing đòi hỏi tester phải phân tích cấu trúc source code."*
- **Thuật ngữ trọng tâm:** `black box testing`, `input`, `output`, `white box testing`, `tester`, `source code`

#### Câu 17: Gray-box Testing
- **Câu hỏi:** Gray-box testing là gì và áp dụng trong trường hợp nào?
- **Câu trả lời:** Gray-box testing kết hợp giữa hộp đen và hộp trắng; tester có hiểu biết một phần về database schema và cấu trúc hệ thống để thiết kế test case tối ưu hơn.
- **Lời thoại đọc thu âm:** *"Trong gray box testing, tester dựa vào kiến thức về database schema và cấu trúc hệ thống để thiết kế các kịch bản kiểm thử hiệu quả hơn."*
- **Thuật ngữ trọng tâm:** `gray box testing`, `tester`, `database schema`

---

### Module 4: Kỹ thuật kiểm thử hộp đen (Black-box Techniques)

#### Câu 18: Equivalence Partitioning
- **Câu hỏi:** Kỹ thuật Equivalence Partitioning hoạt động như thế nào?
- **Câu trả lời:** Chia miền dữ liệu đầu vào thành các phân vùng tương đương hợp lệ và không hợp lệ, mỗi phân vùng chỉ cần chọn một giá trị đại diện để test.
- **Lời thoại đọc thu âm:** *"Kỹ thuật equivalence partitioning chia dữ liệu đầu vào thành các phân vùng tương đương hợp lệ và không hợp lệ để giảm thiểu số lượng test case."*
- **Thuật ngữ trọng tâm:** `equivalence partitioning`, `test case`

#### Câu 19: Boundary Value Analysis
- **Câu hỏi:** Boundary Value Analysis chọn các giá trị nào để kiểm thử?
- **Câu trả lời:** Chọn các giá trị tại biên nhỏ nhất, biên lớn nhất, ngay dưới biên và ngay trên biên vì lỗi thường tập trung tại các phép so sánh biên.
- **Lời thoại đọc thu âm:** *"Boundary value analysis tập trung kiểm thử tại giá trị biên nhỏ nhất, biên lớn nhất và các giá trị ngay sát cạnh biên."*
- **Thuật ngữ trọng tâm:** `boundary value analysis`

#### Câu 20: Decision Table Testing
- **Câu hỏi:** Khi nào nên áp dụng Decision Table testing?
- **Câu trả lời:** Áp dụng khi hệ thống có nhiều điều kiện logic đầu vào kết hợp với nhau tạo ra các hành động xử lý khác nhau.
- **Lời thoại đọc thu âm:** *"Phương pháp decision table testing lập bảng quyết định giúp bao phủ toàn bộ các tổ hợp điều kiện logic phức tạp của nghiệp vụ."*
- **Thuật ngữ trọng tâm:** `decision table testing`

#### Câu 21: State Transition Testing
- **Câu hỏi:** State Transition Testing kiểm tra khía cạnh nào của hệ thống?
- **Câu trả lời:** Kiểm tra cách hệ thống chuyển đổi giữa các trạng thái khác nhau khi nhận các sự kiện hoặc thao tác kích hoạt từ người dùng.
- **Lời thoại đọc thu âm:** *"State transition testing kiểm tra sự chuyển đổi trạng thái của hệ thống khi có các event hoặc thao tác người dùng tác động vào."*
- **Thuật ngữ trọng tâm:** `state transition testing`, `event`

#### Câu 22: Use Case Testing
- **Câu hỏi:** Use Case Testing mang lại lợi ích gì cho tester?
- **Câu trả lời:** Giúp xây dựng kịch bản kiểm thử bám sát vào hành vi và luồng tương tác thực tế của người dùng với hệ thống.
- **Lời thoại đọc thu âm:** *"Use case testing giúp tester xây dựng các ca kiểm thử bám sát kịch bản tương tác thực tế của user với hệ thống."*
- **Thuật ngữ trọng tâm:** `use case testing`, `tester`, `user`

---

### Module 5: Kỹ thuật kiểm thử hộp trắng (White-box Techniques)

#### Câu 23: Statement Coverage
- **Câu hỏi:** Statement Coverage là gì và có đảm bảo tìm hết lỗi không?
- **Câu trả lời:** Đo lường tỷ lệ phần trăm số dòng lệnh được thực thi; dù đạt 100% statement coverage vẫn có thể bỏ sót lỗi logic ở các nhánh điều kiện.
- **Lời thoại đọc thu âm:** *"Statement coverage đo lường phần trăm các dòng code được chạy qua, nhưng đạt một trăm phần trăm vẫn không đảm bảo bắt hết lỗi logic."*
- **Thuật ngữ trọng tâm:** `statement coverage`, `code`

#### Câu 24: Branch Coverage
- **Câu hỏi:** Branch Coverage khác gì so với Statement Coverage?
- **Câu trả lời:** Branch Coverage yêu cầu mọi nhánh rẽ đúng và sai của mọi câu lệnh điều kiện đều phải được kiểm tra ít nhất một lần, nghiêm ngặt hơn Statement Coverage.
- **Lời thoại đọc thu âm:** *"Branch coverage yêu cầu kiểm tra mọi nhánh rẽ true và false của câu lệnh điều kiện, mang lại độ bao phủ cao hơn statement coverage."*
- **Thuật ngữ trọng tâm:** `branch coverage`, `true`, `false`, `statement coverage`

#### Câu 25: Cyclomatic Complexity
- **Câu hỏi:** Cyclomatic Complexity là gì và cách ứng dụng?
- **Câu trả lời:** Là thước đo định lượng độ phức tạp logic của source code, giúp ước lượng số lượng test case độc lập tối thiểu cần viết.
- **Lời thoại đọc thu âm:** *"Độ phức tạp cyclomatic complexity giúp ước lượng số lượng kịch bản test case tối thiểu cần viết để bao quát toàn bộ nhánh rẽ."*
- **Thuật ngữ trọng tâm:** `cyclomatic complexity`, `test case`

#### Câu 26: Static Code Analysis
- **Câu hỏi:** Static Code Analysis mang lại lợi ích gì trong dự án?
- **Câu trả lời:** Quét mã nguồn tự động mà không cần chạy chương trình, giúp phát hiện sớm code smell, vi phạm chuẩn coding và rò rỉ bộ nhớ.
- **Lời thoại đọc thu âm:** *"Công cụ static code analysis cảnh báo sớm các lỗi tiềm ẩn, vi phạm coding standard và nguy cơ rò rỉ bộ nhớ trước khi build sản phẩm."*
- **Thuật ngữ trọng tâm:** `static code analysis`, `coding standard`, `build`

#### Câu 27: Code Review
- **Câu hỏi:** Code Review đóng vai trò gì trong việc nâng cao chất lượng?
- **Câu trả lời:** Developer kiểm tra chéo mã nguồn của nhau trước khi merge pull request để phát hiện lỗi sớm và đảm bảo chuẩn coding convention.
- **Lời thoại đọc thu âm:** *"Quá trình code review trước khi merge pull request giúp tối ưu thuật toán, phát hiện bug sớm và đảm bảo tuân thủ coding convention."*
- **Thuật ngữ trọng tâm:** `code review`, `pull request`, `bug`, `coding convention`

---

### Module 6: STLC & Quản lý Bug (Defect Management)

#### Câu 28: Các giai đoạn của STLC
- **Câu hỏi:** Quy trình STLC gồm các giai đoạn cốt lõi nào?
- **Câu trả lời:** STLC gồm: Phân tích yêu cầu, lập kế hoạch kiểm thử, thiết kế test case, thiết lập môi trường, thực thi kiểm thử và đóng chu kỳ test.
- **Lời thoại đọc thu âm:** *"Quy trình STLC bao gồm phân tích requirement, lập test plan, thiết kế test case, dựng môi trường, thực thi kiểm thử và tổng kết test cycle."*
- **Thuật ngữ trọng tâm:** `STLC`, `requirement`, `test plan`, `test case`, `test cycle`

#### Câu 29: Bug Severity vs Bug Priority
- **Câu hỏi:** Phân biệt Severity và Priority của một lỗi phần mềm?
- **Câu trả lời:** Severity phản ánh mức độ ảnh hưởng kỹ thuật lên hệ thống, còn Priority xác định mức độ khẩn cấp cần developer khắc phục theo yêu cầu nghiệp vụ.
- **Lời thoại đọc thu âm:** *"Bug severity phản ánh mức độ ảnh hưởng kỹ thuật lên hệ thống, còn bug priority xác định mức độ khẩn cấp cần fix theo nghiệp vụ kinh doanh."*
- **Thuật ngữ trọng tâm:** `bug severity`, `bug priority`, `fix`

#### Câu 30: Vòng đời của Bug (Defect Life Cycle)
- **Câu hỏi:** Vòng đời của một Bug trong Defect Life Cycle gồm những trạng thái nào?
- **Câu trả lời:** Bug bắt đầu từ New, được Assigned cho developer sửa thành Fixed, sau đó tester Retest và chuyển sang Closed hoặc Reopened.
- **Lời thoại đọc thu âm:** *"Một bug bắt đầu từ trạng thái new, được assigned cho developer sửa thành fixed, sau đó tester retest và chuyển sang closed hoặc reopened."*
- **Thuật ngữ trọng tâm:** `bug`, `new`, `assigned`, `developer`, `fixed`, `tester`, `retest`, `closed`, `reopened`

#### Câu 31: Nội dung tài liệu Test Plan
- **Câu hỏi:** Tài liệu Test Plan bao gồm những nội dung quan trọng nào?
- **Câu trả lời:** Test Plan xác định phạm vi kiểm thử, mục tiêu chất lượng, lịch trình, phân bổ nhân sự, môi trường test và tiêu chí dừng kiểm thử.
- **Lời thoại đọc thu âm:** *"Tài liệu test plan xác định phạm vi scope kiểm thử, timeline thực hiện, phân bổ resource và các tiêu chí chấp nhận chất lượng."*
- **Thuật ngữ trọng tâm:** `test plan`, `scope`, `timeline`, `resource`

#### Câu 32: Requirements Traceability Matrix (RTM)
- **Câu hỏi:** Requirements Traceability Matrix hay RTM có mục đích gì?
- **Câu trả lời:** RTM đối chiếu từng yêu cầu nghiệp vụ với các test case tương ứng để đảm bảo toàn bộ tính năng đều được kiểm thử đầy đủ.
- **Lời thoại đọc thu âm:** *"Bảng requirements traceability matrix giúp kiểm soát và đảm bảo một trăm phần trăm yêu cầu nghiệp vụ đều có test case kiểm thử tương ứng."*
- **Thuật ngữ trọng tâm:** `requirements traceability matrix`, `test case`

#### Câu 33: Cấu trúc của một Bug Report chuẩn
- **Câu hỏi:** Một Bug Report chuẩn cần chứa những thông tin gì?
- **Câu trả lời:** Cần có tiêu đề rõ ràng, các bước tái hiện (reproduction steps), kết quả thực tế, kết quả mong đợi, độ nghiêm trọng và file log đính kèm.
- **Lời thoại đọc thu âm:** *"Một bug report hoàn chỉnh cần ghi rõ reproduction steps, expected result, actual result, mức độ severity và log lỗi đính kèm."*
- **Thuật ngữ trọng tâm:** `bug report`, `reproduction steps`, `expected result`, `actual result`, `severity`, `log`

---

### Module 7: Automation, CI/CD & Agile Testing

#### Câu 34: Khi nào nên chọn Automation Testing?
- **Câu hỏi:** Khi nào nên ưu tiên Automation Testing hơn Manual Testing?
- **Câu trả lời:** Nên dùng Automation Testing cho các bài kiểm tra lặp đi lặp lại nhiều lần như Regression test, kiểm thử hiệu năng hoặc các luồng nghiệp vụ phức tạp.
- **Lời thoại đọc thu âm:** *"Đội dự án nên áp dụng automation testing cho các kịch bản regression test định kỳ để tiết kiệm chi phí và thời gian so với manual testing."*
- **Thuật ngữ trọng tâm:** `automation testing`, `regression test`, `manual testing`

#### Câu 35: Page Object Model trong Selenium
- **Câu hỏi:** Mô hình Page Object Model trong Selenium mang lại ưu điểm gì?
- **Câu trả lời:** Đóng gói giao diện từng trang web thành class riêng biệt, giúp code test dễ bảo trì, tái sử dụng và ít bị ảnh hưởng khi giao diện thay đổi.
- **Lời thoại đọc thu âm:** *"Mô hình Page Object Model giúp cấu trúc mã nguồn automation test rõ ràng, dễ bảo trì và hạn chế sửa code khi giao diện UI thay đổi."*
- **Thuật ngữ trọng tâm:** `Page Object Model`, `automation test`, `UI`

#### Câu 36: Pipeline CI/CD và Kiểm thử tự động
- **Câu hỏi:** Pipeline CI/CD hỗ trợ quá trình kiểm thử phần mềm như thế nào?
- **Câu trả lời:** CI/CD pipeline tự động build và chạy toàn bộ unit test, integration test mỗi khi có pull request mới để phát hiện lỗi xung đột tức thì.
- **Lời thoại đọc thu âm:** *"Hệ thống CI CD tự động chạy các bài unit test và integration test ngay khi có pull request mới để đảm bảo tính toàn vẹn của mã nguồn."*
- **Thuật ngữ trọng tâm:** `CI CD`, `unit test`, `integration test`, `pull request`

#### Câu 37: Quy trình Test-Driven Development (TDD)
- **Câu hỏi:** Quy trình phát triển Test-Driven Development diễn ra như thế nào?
- **Câu trả lời:** TDD tuân theo chu trình Red-Green-Refactor: viết test case fail trước, viết code vừa đủ để test pass, rồi tiến hành refactor tối ưu mã nguồn.
- **Lời thoại đọc thu âm:** *"Quy trình test driven development tuân thủ chu trình Red Green Refactor nhằm nâng cao độ bao phủ kiểm thử và chất lượng thiết kế mã nguồn."*
- **Thuật ngữ trọng tâm:** `test driven development`, `Red Green Refactor`

#### Câu 38: Behavior-Driven Development (BDD)
- **Câu hỏi:** Behavior-Driven Development sử dụng cú pháp gì để mô tả kịch bản?
- **Câu trả lời:** BDD sử dụng cú pháp Given-When-Then trong ngôn ngữ Gherkin để mô tả hành vi người dùng, giúp BA, developer và QA hiểu chung một ngôn ngữ.
- **Lời thoại đọc thu âm:** *"Phương pháp BDD sử dụng cấu trúc Given When Then để tạo kịch bản kiểm thử dễ hiểu cho cả business analyst, developer và QA."*
- **Thuật ngữ trọng tâm:** `BDD`, `Given When Then`, `business analyst`, `developer`, `QA`

#### Câu 39: Exploratory Testing
- **Câu hỏi:** Exploratory Testing có điểm gì khác biệt so với kiểm thử theo kịch bản?
- **Câu trả lời:** Kiểm thử thăm dò không dùng kịch bản định sẵn, dựa vào kinh nghiệm và sự sáng tạo của tester để tìm ra các lỗi biên hoặc lỗi luồng phức tạp.
- **Lời thoại đọc thu âm:** *"Exploratory testing cho phép tester tự do thao tác khám phá ứng dụng để phát hiện các lỗi bất ngờ mà test case thông thường bỏ sót."*
- **Thuật ngữ trọng tâm:** `exploratory testing`, `tester`, `test case`

#### Câu 40: API Testing
- **Câu hỏi:** Kiểm thử API testing thường xác minh những thông tin cốt lõi nào?
- **Câu trả lời:** API testing kiểm tra HTTP status code, thời gian phản hồi response time và cấu trúc dữ liệu JSON trả về từ các endpoint.
- **Lời thoại đọc thu âm:** *"Khi thực hiện API testing, chúng ta cần xác thực HTTP status code, thời gian response time và cấu trúc dữ liệu JSON trả về từ endpoint."*
- **Thuật ngữ trọng tâm:** `API testing`, `HTTP status code`, `response time`, `JSON`, `endpoint`

---

## 3. Cách nạp dữ liệu vào công cụ LiemWhisper

### Cách 1: Chạy lệnh Seed tự động (Khuyên dùng)
Chạy lệnh sau từ thư mục gốc của project:
```powershell
python tool/scripts/seed_swt_prompts.py --style script
```
Các tùy chọn `--style`:
- `--style script` *(Mặc định)*: Nạp câu thoại đọc tự nhiên (chuẩn 10–15s cho bài toán Speech-to-Text).
- `--style qa`: Nạp cả câu hỏi và câu trả lời: `"Hỏi: [Câu hỏi]? Đáp: [Câu trả lời]"`.
- `--style answer_only`: Chỉ nạp câu trả lời chuyên môn ngắn gọn.

### Cách 2: Sử dụng file JSON
File dữ liệu chuẩn cấu trúc JSON đã được tạo tại:
`tool/scripts/swt_qa_prompts.json`

Bạn có thể import trực tiếp qua API:
```bash
POST /api/v1/admin/courses/{course_id}/prompts/bulk
```
