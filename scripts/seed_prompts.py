"""Seed sample Software Testing course and code-switched technical prompts into LiemWhisper DB."""
import json
import os
import re
import sqlite3
import sys
import time
import uuid
from pathlib import Path

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent / "web" / "backend"
sys.path.insert(0, str(backend_dir))

from app.main import init_db, DB

SAMPLE_PROMPTS = [
    "Trong sprint này, đội phát triển cần bổ sung unit test cho các service xử lý thanh toán.",
    "Khi có bản build mới, tester phải chạy regression testing để đảm bảo tính năng cũ không bị lỗi.",
    "Phương pháp boundary value analysis giúp tìm ra bug tại các giá trị biên của input.",
    "Chúng ta áp dụng equivalence partitioning để giảm bớt số lượng test case cần thực thi.",
    "Mock object được sử dụng để giả lập database khi chạy integration test.",
    "Tài liệu requirement specification nêu rõ hệ thống phải hỗ trợ tối thiểu một nghìn concurrent users.",
    "Trước khi release sản phẩm, đội QA sẽ thực hiện smoke test trên môi trường staging.",
    "Test suite này bị fail do một assertion kiểm tra status code trả về năm trăm.",
    "Code coverage hiện tại đạt tám mươi phần trăm nhưng vẫn bỏ sót nhiều edge case quan trọng.",
    "Mô hình test driven development yêu cầu viết test trước khi implement source code.",
    "Công cụ static code analysis cảnh báo có memory leak tiềm ẩn trong vòng lặp.",
    "Kiểm thử black box testing tập trung vào input và output mà không quan tâm cấu trúc code bên trong.",
    "White box testing yêu cầu tester phải đọc hiểu source code và kiểm tra độ bao phủ nhánh.",
    "Sau khi fix bug, developer cần verify lại và viết reproduction steps rõ ràng.",
    "Tính năng này cần test performance và load testing trước giờ cao điểm.",
    "Mỗi pull request phải vượt qua pipeline CI CD trước khi merge vào branch main.",
    "End to end testing giúp kiểm tra toàn bộ user flow từ giao diện web xuống cơ sở dữ liệu.",
    "Hệ thống logging và monitoring giúp phát hiện exception nhanh chóng trên production.",
    "Đội ngũ bảo mật đã tiến hành penetration testing để tìm kiếm lỗ hổng SQL injection.",
    "Test plan chi tiết bao gồm scope, schedule, rủi ro và tiêu chuẩn acceptance criteria."
]

def extract_english_terms(text: str) -> list[str]:
    pattern = r"\b[A-Za-z][A-Za-z0-9_\-]*(?:\s+[A-Za-z][A-Za-z0-9_\-]+)*\b"
    candidates = re.findall(pattern, text)
    stopwords = {"va", "la", "cac", "nhung", "trong", "khi", "cho", "duoc", "co", "khong", "thi", "de", "mot", "den", "voi"}
    terms = []
    for c in candidates:
        word = c.strip()
        if len(word) >= 2 and word.lower() not in stopwords:
            terms.append(word)
    seen = set()
    return [t for t in terms if not (t.lower() in seen or seen.add(t.lower()))]

def seed():
    init_db()
    conn = sqlite3.connect(DB)
    conn.execute("PRAGMA foreign_keys=ON")
    now = int(time.time())

    # Check if course exists
    cursor = conn.cursor()
    cursor.execute("SELECT id FROM courses WHERE title LIKE '%Software Testing%' LIMIT 1")
    row = cursor.fetchone()
    if row:
        course_id = row[0]
        print(f"Using existing course ID: {course_id}")
    else:
        course_id = str(uuid.uuid4())
        conn.execute(
            "INSERT INTO courses(id, title, description, created_at) VALUES (?,?,?,?)",
            (course_id, "Kiểm thử phần mềm (Software Testing)", "Thu thập thuật ngữ tiếng Anh chêm xen trong kiểm thử phần mềm", now)
        )
        print(f"Created course: Kiểm thử phần mềm (ID: {course_id})")

    inserted = 0
    for text in SAMPLE_PROMPTS:
        # Check duplicate prompt in this course
        cursor.execute("SELECT 1 FROM prompts WHERE course_id=? AND text=?", (course_id, text))
        if cursor.fetchone():
            continue
        pid = str(uuid.uuid4())
        terms = extract_english_terms(text)
        conn.execute(
            """INSERT INTO prompts(id, course_id, text, language, target_terms, difficulty, category, published, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (pid, course_id, text, "vi-en", json.dumps(terms, ensure_ascii=False), "normal", "Software Testing", 1, now)
        )
        inserted += 1

    conn.commit()
    conn.close()
    print(f"Successfully seeded {inserted} prompts! Total published prompts ready for recording.")

if __name__ == "__main__":
    seed()
