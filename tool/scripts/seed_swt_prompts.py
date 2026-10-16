"""Seed Software Testing (SWT) Q&A recording prompts into LiemWhisper DB."""
import argparse
import json
import sys
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
    """Publish the curated SWT prompts and retire old prompts without deleting audio."""
    from app.prompt_seed import sync_swt_prompts

    init_db()
    result = sync_swt_prompts(db, JSON_PATH, style=style)
    print(json.dumps(result, ensure_ascii=False))

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
