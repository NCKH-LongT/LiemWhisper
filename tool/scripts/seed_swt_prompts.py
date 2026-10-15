"""Seed Software Testing (SWT) Q&A recording prompts into LiemWhisper DB."""
import argparse
import json
import os
import sys
import time
import uuid
from pathlib import Path

# Force UTF-8 on Windows console
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(backend_dir))


from app.database import db, init_db

JSON_PATH = Path(__file__).resolve().parent / "swt_qa_prompts.json"

def seed(style: str = "script"):
    """Seed SWT QA prompts.
    
    style:
      - 'script': Natural conversational spoken script (ideal for 10-15s audio recording).
      - 'qa': 'Hỏi: {question} - Đáp: {answer}' format.
      - 'answer_only': Short technical answer.
    """
    init_db()
    with open(JSON_PATH, "r", encoding="utf-8") as f:
        prompts_data = json.load(f)

    now = int(time.time())

    with db() as c:
        # Check if course exists
        row = c.execute("SELECT id FROM courses WHERE title LIKE '%Software Testing%' LIMIT 1").fetchone()
        if row:
            course_id = row[0]
            print(f"Using existing course ID: {course_id}")
        else:
            course_id = str(uuid.uuid4())
            c.execute(
                "INSERT INTO courses(id, title, description, created_at) VALUES (?,?,?,?)",
                (
                    course_id,
                    "Kiểm thử phần mềm (Software Testing - SWT)",
                    "Bộ câu hỏi và câu trả lời thu âm thuật ngữ chuyên ngành kiểm thử phần mềm",
                    now,
                ),
            )
            print(f"Created course: Kiểm thử phần mềm (ID: {course_id})")

        inserted = 0
        for item in prompts_data:
            if style == "qa":
                text = f"Hỏi: {item['question']} Đáp: {item['answer']}"
            elif style == "answer_only":
                text = item["answer"]
            else:
                q = item.get("question", "").strip()
                ans = (item.get("reading_script") or item.get("answer", "")).strip()
                if q and ans:
                    text = f"Câu hỏi: {q}\n\nTrả lời: {ans}"
                else:
                    text = ans or q

            # Avoid duplicates
            if c.execute("SELECT 1 FROM prompts WHERE course_id=? AND text=?", (course_id, text)).fetchone():
                continue

            pid = str(uuid.uuid4())
            target_terms = json.dumps(item["target_terms"], ensure_ascii=False)
            category = item.get("category", "Software Testing")
            
            c.execute(
                """INSERT INTO prompts(id, course_id, text, language, target_terms, difficulty, category, published, created_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (pid, course_id, text, "vi-en", target_terms, "normal", category, 1, now),
            )
            inserted += 1

        print(f"Successfully seeded {inserted} SWT prompts (style='{style}') into course {course_id}!")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Seed SWT prompts into LiemWhisper")
    parser.add_argument(
        "--style",
        choices=["script", "qa", "answer_only"],
        default="script",
        help="Prompt text style: 'script' (spoken utterance), 'qa' (Hỏi/Đáp), 'answer_only'",
    )
    args = parser.parse_args()
    seed(style=args.style)
