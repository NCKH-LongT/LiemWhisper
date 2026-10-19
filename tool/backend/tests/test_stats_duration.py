import uuid
from test_collection import setup_test_app
from app.database import db

def test_admin_stats_only_returns_published_prompts_and_has_question_numbers(tmp_path, monkeypatch):
    client = setup_test_app(tmp_path, monkeypatch)
    key = {"x-admin-key": "test-only-admin-secret"}

    # 1. Get the seeded course
    course = client.get("/api/v1/courses").json()[0]
    course_id = course["id"]

    # 2. Add an unpublished retired prompt
    retired_id = str(uuid.uuid4())
    with db() as c:
        c.execute(
            """INSERT INTO prompts (id, course_id, text, language, target_terms, difficulty, category, published, created_at)
               VALUES (?, ?, ?, 'vi-en', '[]', 'normal', 'Testing Techniques', 0, 999999999)""",
            (retired_id, course_id, "Câu hỏi đã nghỉ hưu không xuất bản")
        )

    # 3. Add a recording for the first published prompt
    participant = client.post("/api/v1/participants", json={"consent": True, "participant_code": "SV_TEST"}).json()
    part_token = participant["participant_token"]
    tasks = client.get(f"/api/v1/tasks?course_id={course_id}", headers={"x-participant-token": part_token}).json()
    prompt1_id = tasks[0]["id"]

    res = client.post(
        "/api/v1/recordings",
        headers={"x-participant-token": part_token},
        data={"prompt_id": prompt1_id, "duration": "5.5"},
        files={"audio": ("sample.webm", b"\x1a\x45\xdf\xa3" + b"\0" * 300, "audio/webm")}
    )
    assert res.status_code == 200

    # 4. Fetch admin stats
    stats = client.get("/api/v1/admin/stats", headers=key).json()
    assert "prompt_duration_stats" in stats
    prompt_stats = stats["prompt_duration_stats"]

    # Must only contain the 15 published prompts, not the retired prompt!
    assert len(prompt_stats) == 15
    assert not any(p["prompt_id"] == retired_id for p in prompt_stats)

    # All prompts must have question_number starting from 1 to 15 in order
    q_nums = [p["question_number"] for p in prompt_stats]
    assert q_nums == list(range(1, 16))

    # First prompt must have 1 recording with duration 5.5
    p1 = next(p for p in prompt_stats if p["prompt_id"] == prompt1_id)
    assert p1["recordings_count"] == 1
    assert p1["total_duration_seconds"] == 5.5
    assert p1["avg_duration_seconds"] == 5.5

    # 5. Fetch admin list prompts
    prompts_list = client.get(f"/api/v1/admin/prompts?course_id={course_id}", headers=key).json()
    assert len(prompts_list) == 15
    assert not any(p["id"] == retired_id for p in prompts_list)
    assert [p["question_number"] for p in prompts_list] == list(range(1, 16))
