"""SQL integration tests use disposable SQLite and explicit FAKE Drive only."""
import importlib
import io
import sys
import zipfile

from fastapi.testclient import TestClient

ADMIN = {"x-admin-key": "test-only-admin-secret"}
BODY = b"\x1a\x45\xdf\xa3" + bytes(range(256)) * 3


def setup(tmp_path, monkeypatch, mode="sql"):
    monkeypatch.setenv("DATA_ROOT", str(tmp_path))
    monkeypatch.setenv("STORAGE_BACKEND", mode)
    monkeypatch.setenv("ADMIN_API_KEY", "test-only-admin-secret")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    sys.modules.pop("app.main", None)
    main = importlib.import_module("app.main")
    client = TestClient(main.app)
    course = client.post("/api/v1/admin/courses", headers=ADMIN, json={"title": "SQL storage"}).json()["id"]
    prompt = client.post(f"/api/v1/admin/courses/{course}/prompts/bulk", headers=ADMIN, json={"prompts": ["Read this sentence"]}).json()["prompts"][0]["id"]
    signup = client.post("/api/v1/participants", json={"consent": True}).json()
    token = {"x-participant-token": signup["participant_token"]}
    return main, client, course, prompt, token


def upload(client, prompt, token):
    return client.post("/api/v1/recordings", headers=token, data={"prompt_id": prompt, "duration": 2}, files={"audio": ("test.webm", BODY, "audio/webm")})


def test_full_sql_audio_range_export(tmp_path, monkeypatch):
    main, client, course, prompt, token = setup(tmp_path, monkeypatch)
    response = upload(client, prompt, token)
    assert response.status_code == 200, response.text
    rid = response.json()["recording_id"]
    with main.db() as c:
        assert bytes(c.execute("SELECT body FROM recording_audio WHERE recording_id=?", (rid,)).fetchone()[0]) == BODY
    assert list((tmp_path / "audio").iterdir()) == []
    url = f"/api/v1/recordings/{rid}/audio"
    assert client.get(url, headers=token).content == BODY
    partial = client.get(url, headers={**token, "range": "bytes=10-29"})
    assert partial.status_code == 206
    assert partial.content == BODY[10:30]
    assert partial.headers["content-range"] == f"bytes 10-29/{len(BODY)}"
    assert client.get(url, headers={**token, "range": "bytes=-8"}).content == BODY[-8:]
    assert client.get(url, headers={**token, "range": "bytes=9999-"}).status_code == 416
    client.post(f"/api/v1/admin/recordings/{rid}/review", headers=ADMIN, json={"status": "approved"})
    archive = client.get("/api/v1/admin/export/archive.zip", headers=ADMIN)
    assert archive.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive.content)) as z:
        assert z.read(f"audio/{rid}.webm") == BODY
