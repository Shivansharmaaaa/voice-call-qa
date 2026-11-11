"""Write the synthetic calls to data/ and a static HTML snapshot of the dashboard to docs/.

Run: python scripts/demo.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from callqa.api import Demo, render_dashboard  # noqa: E402
from callqa.summary import summarize  # noqa: E402
from callqa.synth import save  # noqa: E402


def main() -> None:
    demo = Demo(ROOT / "agents")
    (ROOT / "data").mkdir(exist_ok=True)
    save(demo.samples, ROOT / "data" / "synthetic_calls.jsonl")
    summaries = [summarize(spec, [c for c in demo.calls.values() if c["agent_id"] == spec.id])
                 for spec in demo.specs.values()]
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "index.html").write_text(render_dashboard(summaries), encoding="utf-8")
    for s in summaries:
        print(s["name"], "| calls", s["calls"], "| mean score", s["mean_score"], "| fail rates", s["fail_rate_by_check"])


if __name__ == "__main__":
    main()
