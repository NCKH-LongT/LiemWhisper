"""Initial backend scaffold. In-memory examples only: NOT safe for participant data."""
from fastapi import FastAPI
from pydantic import BaseModel, Field

app = FastAPI(
    title="LiemWhisper Collection API",
    version="0.1.0",
    description="Development scaffold. Storage, authentication and consent enforcement are not implemented.",
)


class PromptPreview(BaseModel):
    id: str = Field(min_length=1)
    course_id: str = Field(min_length=1)
    text: str = Field(min_length=1)
    language: str = "vi-en"


@app.get("/health")
def health():
    return {"status": "ok", "mode": "scaffold", "storage_ready": False}


@app.get("/api/v1/capabilities")
def capabilities():
    return {
        "recording_upload_enabled": False,
        "google_drive_enabled": False,
        "authentication_enabled": False,
        "research_export_enabled": False,
        "message": "Do not submit personal or audio data to this scaffold.",
    }


@app.post("/api/v1/prompts/preview", response_model=PromptPreview)
def preview_prompt(prompt: PromptPreview):
    """Validates a proposed prompt; DOES NOT persist or publish it."""
    return prompt
