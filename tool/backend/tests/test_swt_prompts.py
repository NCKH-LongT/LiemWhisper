"""Curated SWT corpus and safe upgrades of existing collection data."""
import json
from pathlib import Path


def test_curated_swt_corpus_has_fifteen_clean_prompts():
    backend = Path(__file__).resolve().parents[1]
    prompts = json.loads((backend / "app/swt_qa_prompts.json").read_text(encoding="utf-8"))
    script_prompts = json.loads((backend.parent / "scripts/swt_qa_prompts.json").read_text(encoding="utf-8"))
    assert prompts == script_prompts
    assert len(prompts) == 15
    assert len({item["id"] for item in prompts}) == 15
    assert len({item["category"] for item in prompts}) == 5
    for item in prompts:
        for field in ("question", "answer", "reading_script"):
            assert item[field].strip()
            assert ";" not in item[field]
        assert item["target_terms"]


def test_reseeding_preserves_recordings_and_only_retires_old_swt_prompts(tmp_path, monkeypatch):
    from test_collection import setup_test_app
    from app.database import db
    import uuid

    client = setup_test_app(tmp_path, monkeypatch)
    course = client.get("/api/v1/courses").json()[0]
    participant = client.post("/api/v1/participants", json={"consent": True}).json()
    headers = {"x-participant-token": participant["participant_token"]}
    before = client.get("/api/v1/tasks", params={"course_id": course["id"]}, headers=headers).json()
    retained = before[0]
    retired_id = str(uuid.uuid4())
    custom_course = str(uuid.uuid4())
    with db() as c:
        c.execute(
            "INSERT INTO prompts(id,course_id,text,language,target_terms,difficulty,category,published,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (retired_id, course["id"], "Câu hỏi cũ không còn được chọn", "vi-en", "[]", "normal", "", 1, 0),
        )
        c.execute("INSERT INTO courses(id,title,description,created_at) VALUES (?,?,?,?)", (custom_course, "Custom course", "", 0))
        c.execute(
            "INSERT INTO prompts(id,course_id,text,language,target_terms,difficulty,category,published,created_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (str(uuid.uuid4()), custom_course, "Do not modify custom questions", "vi", "[]", "normal", "", 1, 0),
        )
    recordings = []
    for prompt_id in (retained["id"], retired_id):
        result = client.post(
            "/api/v1/recordings", headers=headers,
            data={"prompt_id": prompt_id, "duration": "3.0"},
            files={"audio": ("clip.webm", b"\x1a\x45\xdf\xa3" + b"\0" * 200, "audio/webm")},
        )
        assert result.status_code == 200
        recordings.append(result.json()["recording_id"])
    response = client.post("/api/v1/courses/seed-default?force=true")
    assert response.status_code == 200
    after = client.get("/api/v1/tasks", params={"course_id": course["id"]}, headers=headers).json()
    assert len(after) == 15
    assert {p["id"] for p in after} == {p["id"] for p in before}
    with db() as c:
        retired = c.execute("SELECT published FROM prompts WHERE id=?", (retired_id,)).fetchone()
        stored = c.execute("SELECT COUNT(*) FROM recordings WHERE id IN (?,?)", tuple(recordings)).fetchone()
        custom = c.execute("SELECT COUNT(*) FROM prompts WHERE course_id=? AND published=1", (custom_course,)).fetchone()
        assert retired is not None and retired[0] == 0
        assert stored is not None and stored[0] == 2
        assert custom is not None and custom[0] == 1
    for recording_id in recordings:
        audio = client.get(f"/api/v1/recordings/{recording_id}/audio", headers=headers)
        assert audio.status_code == 200
        assert audio.content.startswith(b"\x1a\x45\xdf\xa3")
    repeated = client.post("/api/v1/courses/seed-default").json()
    assert repeated["diagnostic"]["status"] == "already_seeded"


def test_cli_prompt_styles_reuse_ids_without_creating_duplicates(tmp_path, monkeypatch):
    from test_collection import setup_test_app
    from app.database import db
    from app.prompt_seed import sync_swt_prompts

    client = setup_test_app(tmp_path, monkeypatch)
    course = client.get("/api/v1/courses").json()[0]
    with db() as c:
        original_ids = {row[0] for row in c.execute("SELECT id FROM prompts WHERE course_id=?", (course["id"],)).fetchall()}
    for style in ("answer_only", "qa", "script"):
        result = sync_swt_prompts(db, style=style)
        assert result["inserted"] == 0
        with db() as c:
            current = c.execute("SELECT id FROM prompts WHERE course_id=? AND published=1", (course["id"],)).fetchall()
            assert {row[0] for row in current} == original_ids
