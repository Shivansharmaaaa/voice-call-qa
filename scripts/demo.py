"""Load the synthetic calls through the API into a fresh database and write a static dashboard.

Run: python scripts/demo.py   -> data/synthetic_calls.jsonl, docs/index.html
"""
from __future__ import annotations

import sys
from dataclasses import asdict
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from callqa.api import create_app, render_dashboard  # noqa: E402
from callqa.synth import generate, save  # noqa: E402


def main() -> None:
    db = ROOT / "data" / "demo.db"
    db.parent.mkdir(exist_ok=True)
    db.unlink(missing_ok=True)
    samples = generate()
    save(samples, ROOT / "data" / "synthetic_calls.jsonl")
    client = TestClient(create_app(f"sqlite:///{db}"))
    for s in samples:
        r = client.post("/calls", json=asdict(s.call))
        r.raise_for_status()
    summaries = [client.get(f"/agents/{a['id']}/summary").json() for a in client.get("/agents").json()]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "index.html").write_text(render_dashboard(summaries), encoding="utf-8")
    for s in summaries:
        print(s["name"], "| calls", s["calls"], "| mean score", s["mean_score"], "| fail rates", s["fail_rate_by_check"])


if __name__ == "__main__":
    main()
