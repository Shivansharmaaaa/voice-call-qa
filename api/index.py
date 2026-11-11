"""Vercel serverless entry point: the same FastAPI app, without the static web build
(Vercel serves web/dist itself and routes /api/* here)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from callqa.api import create_app  # noqa: E402

app = create_app(web_dir=None)
