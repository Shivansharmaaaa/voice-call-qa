"""Measure the checker against the planted labels: precision and recall per finding type.

Run: python -m callqa.evaluate
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

from .engine import score_call
from .spec import load_dir
from .synth import generate

ROOT = Path(__file__).resolve().parent.parent


def evaluate(samples, specs) -> dict:
    tp, fp, fn = defaultdict(int), defaultdict(int), defaultdict(int)
    must_not_flag = {"restart": [0, 0], "caller_asked": [0, 0], "compliance": [0, 0], "hangup": [0, 0]}
    for s in samples:
        rep = score_call(s.call, specs[s.call.agent_id])
        found = {f"{f.check}:{f.code}" for f in rep.findings if f.severity == "fail"}
        truth = set(s.labels)
        for key in found | truth:
            if key in found and key in truth:
                tp[key] += 1
            elif key in found:
                fp[key] += 1
            else:
                fn[key] += 1
        planted = " ".join(s.planted)
        for name, marker, bad in [("restart", "restart_after_interrupt", "repeats:repeat"),
                                  ("caller_asked", "caller_asked_repeat", "repeats:repeat"),
                                  ("compliance", "compliance_repeat", "repeats:repeat"),
                                  ("hangup", "user_hangup", "early_exit:early_exit")]:
            if marker in planted:
                must_not_flag[name][0] += 1
                if bad in found and bad not in truth:
                    must_not_flag[name][1] += 1
    rows = {}
    for key in sorted(set(tp) | set(fp) | set(fn)):
        p = tp[key] / (tp[key] + fp[key]) if tp[key] + fp[key] else 0.0
        r = tp[key] / (tp[key] + fn[key]) if tp[key] + fn[key] else 0.0
        rows[key] = {"tp": tp[key], "fp": fp[key], "fn": fn[key], "precision": round(p, 3), "recall": round(r, 3)}
    return {"calls": len(samples), "per_finding": rows,
            "must_not_flag": {k: {"planted": v[0], "wrongly_flagged": v[1]} for k, v in must_not_flag.items()}}


def main() -> None:
    specs = load_dir(ROOT / "agents")
    result = evaluate(generate(), specs)
    print(f"{result['calls']} synthetic calls\n")
    print(f"{'finding':34} {'TP':>4} {'FP':>4} {'FN':>4} {'precision':>10} {'recall':>8}")
    for key, r in result["per_finding"].items():
        print(f"{key:34} {r['tp']:>4} {r['fp']:>4} {r['fn']:>4} {r['precision']:>10.2f} {r['recall']:>8.2f}")
    print("\nPlanted cases that must NOT be flagged:")
    for k, v in result["must_not_flag"].items():
        print(f"  {k:14} planted {v['planted']:>3}, wrongly flagged {v['wrongly_flagged']}")
    (ROOT / "docs").mkdir(exist_ok=True)
    (ROOT / "docs" / "benchmark.json").write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
