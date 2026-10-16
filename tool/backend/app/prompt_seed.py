"""Synchronize the default SWT corpus without deleting recorded prompts."""
import json
import time
import uuid
from pathlib import Path

COURSE_TITLE = "Kiểm thử phần mềm (Software Testing - SWT)"


def sync_swt_prompts(connection_factory, json_path=None, force=False, style="script"):
    json_file = Path(json_path) if json_path else Path(__file__).with_name("swt_qa_prompts.json")
    items = json.loads(json_file.read_text(encoding="utf-8"))
    diagnostic = {"json_file": str(json_file), "prompts_count": len(items)}
    now = int(time.time())
    with connection_factory() as c:
        course = c.execute(
            "SELECT id FROM courses WHERE title=? OR title LIKE ? ORDER BY created_at ASC, id ASC LIMIT 1",
            (COURSE_TITLE, "%Software Testing%"),
        ).fetchone()
        if course:
            course_id = course[0]
        else:
            course_id = str(uuid.uuid4())
            c.execute(
                "INSERT INTO courses(id,title,description,created_at) VALUES (?,?,?,?)",
                (course_id, COURSE_TITLE, "15 câu hỏi và câu đọc thu âm thuật ngữ kiểm thử phần mềm", now),
            )
            diagnostic["created_course_id"] = course_id
        diagnostic["course_id"] = course_id
        existing = c.execute(
            "SELECT id,text,target_terms,category,published FROM prompts WHERE course_id=? ORDER BY created_at ASC,id ASC",
            (course_id,),
        ).fetchall()
        selected = set()
        inserted = 0
        changed = False
        for index, item in enumerate(items):
            question = item.get("question", "").strip().replace(";", ",")
            answer = (item.get("reading_script") or item.get("answer", "")).strip().replace(";", ",")
            if style == "qa":
                text = f"Hỏi: {question} Đáp: {item['answer']}"
            elif style == "answer_only":
                text = item["answer"]
            else:
                text = f"Câu hỏi: {question}\n\nTrả lời: {answer}" if question and answer else answer or question
            text = text.replace(";", ",")
            terms = json.dumps(item.get("target_terms", []), ensure_ascii=False)
            category = item.get("category", "")
            stable_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"liemwhisper:{course_id}:{item['id']}"))
            match = next((row for row in existing if row["id"] not in selected and (
                row["id"] == stable_id
                or row["text"].replace(";", ",") == item.get("answer", "").replace(";", ",")
                or row["text"].replace(";", ",") == text
                or row["text"].startswith(f"Câu hỏi: {question}\n\nTrả lời:")
                or row["text"].startswith(f"Hỏi: {question} Đáp:")
                or row["text"].replace(";", ",") == answer
            )), None)
            if match:
                prompt_id = match["id"]
                if force or match["text"] != text or match["target_terms"] != terms or match["category"] != category or match["published"] != 1:
                    c.execute(
                        "UPDATE prompts SET text=?,target_terms=?,category=?,published=1,created_at=? WHERE id=?",
                        (text, terms, category, now + index, prompt_id),
                    )
                    changed = True
            else:
                prompt_id = stable_id
                c.execute(
                    "INSERT INTO prompts(id,course_id,text,language,target_terms,difficulty,category,published,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
                    (prompt_id, course_id, text, "vi-en", terms, "normal", category, 1, now + index),
                )
                inserted += 1
                changed = True
            selected.add(prompt_id)
        for row in existing:
            if row["id"] not in selected and row["published"]:
                # Keep the row and all recording foreign keys for review/export.
                c.execute("UPDATE prompts SET published=0 WHERE id=?", (row["id"],))
                changed = True
        diagnostic.update(status="seeded" if changed else "already_seeded", inserted=inserted, existing_prompts=len(selected))
    return diagnostic
